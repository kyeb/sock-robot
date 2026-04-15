use crate::types::MotorCommand;
use esp_idf_svc::hal::gpio::{Output, OutputPin, PinDriver};
use esp_idf_svc::hal::ledc::LedcDriver;

const MAX_EFFORT_PCT: f32 = 60.0;

pub struct Motors<'d, P1: OutputPin, P2: OutputPin> {
    pwm1: LedcDriver<'d>,
    dir1: PinDriver<'d, P1, Output>,
    pwm2: LedcDriver<'d>,
    dir2: PinDriver<'d, P2, Output>,
    max_duty: u32,
}

impl<'d, P1: OutputPin, P2: OutputPin> Motors<'d, P1, P2> {
    pub fn new(
        pwm1: LedcDriver<'d>,
        dir1: PinDriver<'d, P1, Output>,
        pwm2: LedcDriver<'d>,
        dir2: PinDriver<'d, P2, Output>,
    ) -> Self {
        let max_duty = pwm1.get_max_duty();
        Self { pwm1, dir1, pwm2, dir2, max_duty }
    }

    pub fn apply(&mut self, cmd: MotorCommand) {
        let left = cmd.left.clamp(-MAX_EFFORT_PCT, MAX_EFFORT_PCT);
        let right = cmd.right.clamp(-MAX_EFFORT_PCT, MAX_EFFORT_PCT);

        // Motor 1: not inverted
        if left >= 0.0 {
            self.dir1.set_low().unwrap();
        } else {
            self.dir1.set_high().unwrap();
        }
        let duty1 = (left.abs() as u32) * self.max_duty / 100;
        self.pwm1.set_duty(duty1).unwrap();

        // Motor 2: inverted (mounted opposite)
        if right <= 0.0 {
            self.dir2.set_low().unwrap();
        } else {
            self.dir2.set_high().unwrap();
        }
        let duty2 = (right.abs() as u32) * self.max_duty / 100;
        self.pwm2.set_duty(duty2).unwrap();
    }

    pub fn stop(&mut self) {
        self.pwm1.set_duty(0).unwrap();
        self.pwm2.set_duty(0).unwrap();
    }
}
