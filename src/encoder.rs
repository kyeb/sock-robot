use esp_idf_svc::hal::gpio::{AnyInputPin, InputPin};
use esp_idf_svc::hal::pcnt::*;
use esp_idf_svc::hal::peripheral::Peripheral;
use std::cmp::min;
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::Arc;

const PCNT_HIGH_LIMIT: i16 = 100;
const PCNT_LOW_LIMIT: i16 = -100;

pub struct Encoder<'d> {
    unit: PcntDriver<'d>,
    accum: Arc<AtomicI32>,
}

impl<'d> Encoder<'d> {
    pub fn new<PCNT: Pcnt>(
        pcnt: impl Peripheral<P = PCNT> + 'd,
        pin_a: impl Peripheral<P = impl InputPin> + 'd,
        pin_b: impl Peripheral<P = impl InputPin> + 'd,
    ) -> Self {
        let mut unit = PcntDriver::new(
            pcnt,
            Some(pin_a),
            Some(pin_b),
            Option::<AnyInputPin>::None,
            Option::<AnyInputPin>::None,
        )
        .unwrap();

        unit.channel_config(
            PcntChannel::Channel0,
            PinIndex::Pin0,
            PinIndex::Pin1,
            &PcntChannelConfig {
                lctrl_mode: PcntControlMode::Reverse,
                hctrl_mode: PcntControlMode::Keep,
                pos_mode: PcntCountMode::Decrement,
                neg_mode: PcntCountMode::Increment,
                counter_h_lim: PCNT_HIGH_LIMIT,
                counter_l_lim: PCNT_LOW_LIMIT,
            },
        )
        .unwrap();

        unit.channel_config(
            PcntChannel::Channel1,
            PinIndex::Pin1,
            PinIndex::Pin0,
            &PcntChannelConfig {
                lctrl_mode: PcntControlMode::Reverse,
                hctrl_mode: PcntControlMode::Keep,
                pos_mode: PcntCountMode::Increment,
                neg_mode: PcntCountMode::Decrement,
                counter_h_lim: PCNT_HIGH_LIMIT,
                counter_l_lim: PCNT_LOW_LIMIT,
            },
        )
        .unwrap();

        unit.set_filter_value(min(10 * 80, 1023)).unwrap();
        unit.filter_enable().unwrap();

        let accum = Arc::new(AtomicI32::new(0));
        unsafe {
            let accum_clone = accum.clone();
            unit.subscribe(move |status| {
                let status = PcntEventType::from_repr_truncated(status);
                if status.contains(PcntEvent::HighLimit) {
                    accum_clone.fetch_add(PCNT_HIGH_LIMIT as i32, Ordering::SeqCst);
                }
                if status.contains(PcntEvent::LowLimit) {
                    accum_clone.fetch_add(PCNT_LOW_LIMIT as i32, Ordering::SeqCst);
                }
            })
            .unwrap();
        }
        unit.event_enable(PcntEvent::HighLimit).unwrap();
        unit.event_enable(PcntEvent::LowLimit).unwrap();
        unit.counter_pause().unwrap();
        unit.counter_clear().unwrap();
        unit.counter_resume().unwrap();

        Self { unit, accum }
    }

    pub fn count(&self) -> i32 {
        self.accum.load(Ordering::Relaxed) + self.unit.get_counter_value().unwrap_or(0) as i32
    }
}
