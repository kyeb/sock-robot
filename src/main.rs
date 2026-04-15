mod comms;
mod controller;
mod encoder;
mod estimator;
mod imu;
mod motors;
mod types;

use controller::BalanceController;
use encoder::Encoder;
use esp_idf_svc::hal::gpio::PinDriver;
use esp_idf_svc::hal::i2c::{I2cConfig, I2cDriver};
use esp_idf_svc::hal::ledc::{config::TimerConfig, LedcDriver, LedcTimerDriver};
use esp_idf_svc::hal::prelude::*;
use esp_idf_svc::sys;
use log::info;
use motors::Motors;
use std::thread;
use std::time::Duration;
use types::*;

fn millis() -> u32 {
    unsafe { (sys::esp_timer_get_time() / 1000) as u32 }
}

fn main() {
    esp_idf_svc::sys::link_patches();
    esp_idf_svc::log::EspLogger::initialize_default();

    let peripherals = Peripherals::take().unwrap();

    unsafe {
        sys::uart_driver_install(0, 1024, 0, 0, std::ptr::null_mut(), 0);
    }

    // Motors
    let timer1 = LedcTimerDriver::new(
        peripherals.ledc.timer0,
        &TimerConfig::default().frequency(1.kHz().into()),
    )
    .unwrap();
    let pwm1 = LedcDriver::new(peripherals.ledc.channel0, &timer1, peripherals.pins.gpio16).unwrap();
    let dir1 = PinDriver::output(peripherals.pins.gpio17).unwrap();

    let timer2 = LedcTimerDriver::new(
        peripherals.ledc.timer1,
        &TimerConfig::default().frequency(1.kHz().into()),
    )
    .unwrap();
    let pwm2 = LedcDriver::new(peripherals.ledc.channel1, &timer2, peripherals.pins.gpio18).unwrap();
    let dir2 = PinDriver::output(peripherals.pins.gpio19).unwrap();

    let mut motors = Motors::new(pwm1, dir1, pwm2, dir2);

    // Encoders
    let enc1 = Encoder::new(peripherals.pcnt0, peripherals.pins.gpio23, peripherals.pins.gpio4);
    let enc2 = Encoder::new(peripherals.pcnt1, peripherals.pins.gpio25, peripherals.pins.gpio26);

    // IMU
    let i2c = I2cDriver::new(
        peripherals.i2c0,
        peripherals.pins.gpio21,
        peripherals.pins.gpio22,
        &I2cConfig::new().baudrate(400.kHz().into()),
    )
    .unwrap();

    let mut imu = imu::Imu::new(i2c, 0x6B);
    imu.calibrate_bias(200);

    // Estimator
    let mut estimator = estimator::Estimator::new();
    if let Some(reading) = imu.read() {
        estimator.init_angle(&reading);
    }
    estimator.init_encoders(enc1.count(), -enc2.count());

    // Controller
    let mut ctrl = BalanceController::new();
    let mut reference = ControlReference {
        target_vel: 0.0,
        enabled: false,
    };

    info!("sock-robot ready. Commands: STOP, PID_ON, PID_OFF, KP/KD/VKP/VKI/PKP/YKP/TARGET <val>");

    let mut buf = [0u8; 128];
    let mut pos = 0usize;
    let mut buf_overflow = false;
    let mut last_imu_ms = millis();
    let mut last_print_ms = millis();

    loop {
        // Handle serial commands (non-blocking)
        if let Some(byte) = comms::uart_read_byte() {
            if byte == b'\n' || byte == b'\r' {
                if pos > 0 && !buf_overflow {
                    if let Ok(line) = core::str::from_utf8(&buf[..pos]) {
                        match comms::parse_command(line) {
                            Some(Command::Stop) => {
                                ctrl.enabled = false;
                                ctrl.reset();
                                reference.enabled = false;
                                motors.stop();
                                info!("STOP");
                            }
                            Some(Command::PidOn) => {
                                ctrl.reset();
                                ctrl.set_home(estimator.wheel_pos(), estimator.yaw_pos());
                                ctrl.enabled = true;
                                reference.enabled = true;
                                info!("PID ON: angle_kp={:.2} angle_kd={:.2} vel_kp={:.2} vel_ki={:.2} pos_kp={:.2} yaw_kp={:.2}",
                                    ctrl.angle_kp, ctrl.angle_kd, ctrl.vel_kp, ctrl.vel_ki, ctrl.pos_kp, ctrl.yaw_kp);
                            }
                            Some(Command::PidOff) => {
                                ctrl.enabled = false;
                                ctrl.reset();
                                reference.enabled = false;
                                motors.stop();
                                info!("PID OFF");
                            }
                            Some(Command::SetKp(v)) => { ctrl.angle_kp = v; info!("KP={:.2}", v); }
                            Some(Command::SetKi(v)) => { info!("KI ignored in cascaded mode (use VKI). val={:.2}", v); }
                            Some(Command::SetKd(v)) => { ctrl.angle_kd = v; info!("KD={:.2}", v); }
                            Some(Command::SetTarget(v)) => { reference.target_vel = v; info!("TARGET_VEL={:.1}", v); }
                            Some(Command::SetVelKp(v)) => { ctrl.vel_kp = v; info!("VKP={:.2}", v); }
                            Some(Command::SetVelKi(v)) => { ctrl.vel_ki = v; ctrl.reset(); info!("VKI={:.2}", v); }
                            Some(Command::SetPosKp(v)) => { ctrl.pos_kp = v; info!("PKP={:.2}", v); }
                            Some(Command::SetYawKp(v)) => { ctrl.yaw_kp = v; info!("YKP={:.2}", v); }
                            Some(Command::SetPitchBias(v)) => { ctrl.pitch_bias = v; info!("PBIAS={:.2}", v); }
                            Some(Command::SetVelIntLimit(v)) => { ctrl.vel_integral_limit = v; info!("VILIM={:.2}", v); }
                            None => { info!("ERR: unknown: {line}"); }
                        }
                    }
                }
                pos = 0;
                buf_overflow = false;
            } else if pos < buf.len() - 1 {
                buf[pos] = byte;
                pos += 1;
            } else {
                buf_overflow = true;
            }
        }

        let now = millis();

        // 200Hz control loop
        if now.wrapping_sub(last_imu_ms) >= 5 {
            let dt = now.wrapping_sub(last_imu_ms) as f32 / 1000.0;
            last_imu_ms = now;

            let e1 = enc1.count();
            let e2 = -enc2.count();

            if let Some(reading) = imu.read() {
                let snapshot = SensorSnapshot {
                    t_ms: now,
                    dt,
                    imu: reading,
                    enc1: e1,
                    enc2: e2,
                };

                let state = estimator.update(&snapshot);
                let cmd = ctrl.update(&state, &reference);

                // Always apply command — if controller disabled, it returns zero
                motors.apply(cmd);

                // 50Hz telemetry
                if now.wrapping_sub(last_print_ms) >= 20 {
                    last_print_ms = now;
                    comms::emit_telemetry(&state, &snapshot, &ctrl, estimator.filtered_vel1, estimator.filtered_vel2);
                }
            } else {
                // IMU read failure: fail safe
                ctrl.enabled = false;
                ctrl.reset();
                motors.stop();
            }
        }

        thread::sleep(Duration::from_micros(500));
    }
}
