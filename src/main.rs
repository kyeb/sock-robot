mod comms;
mod controller;
mod encoder;
mod estimator;
mod imu;
mod motors;
mod types;

use controller::Controller;
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
        // TX ring buffer of 4096 so telemetry writes with 0 timeout never
        // block the control loop — if the host stops draining, lines drop
        // instead of stalling the 200Hz loop.
        sys::uart_driver_install(0, 1024, 4096, 0, std::ptr::null_mut(), 0);
    }

    // Motors
    let timer1 = LedcTimerDriver::new(
        peripherals.ledc.timer0,
        &TimerConfig::default().frequency(1.kHz().into()),
    )
    .unwrap();
    let pwm1 =
        LedcDriver::new(peripherals.ledc.channel0, &timer1, peripherals.pins.gpio16).unwrap();
    let dir1 = PinDriver::output(peripherals.pins.gpio17).unwrap();

    let timer2 = LedcTimerDriver::new(
        peripherals.ledc.timer1,
        &TimerConfig::default().frequency(1.kHz().into()),
    )
    .unwrap();
    let pwm2 =
        LedcDriver::new(peripherals.ledc.channel1, &timer2, peripherals.pins.gpio18).unwrap();
    let dir2 = PinDriver::output(peripherals.pins.gpio19).unwrap();

    let mut motors = Motors::new(pwm1, dir1, pwm2, dir2);

    // Encoders
    let enc1 = Encoder::new(
        peripherals.pcnt0,
        peripherals.pins.gpio23,
        peripherals.pins.gpio4,
    );
    let enc2 = Encoder::new(
        peripherals.pcnt1,
        peripherals.pins.gpio25,
        peripherals.pins.gpio26,
    );

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
    let mut ctrl = Controller::new();
    let mut reference = ControlReference {
        target_vel: 0.0,
        target_yaw_rate: 0.0,
        enabled: false,
    };

    info!("sock-robot ready. Commands: STOP, ENABLE, DISABLE, K1/K2/K3/K4/KYAW/THEQ/TVEL/TYAW/EFFORT <val>");

    let mut buf = [0u8; 128];
    let mut pos = 0usize;
    let mut buf_overflow = false;
    let mut last_imu_ms = millis();
    let mut last_print_ms = millis();
    let mut inner_loop_count: u32 = 0;

    // Manual effort override for motor identification. Active only when the
    // controller is off. Watchdog: auto-clears 500ms after the last EFFORT
    // command so a host crash doesn't leave motors spinning.
    let mut manual_effort: Option<(f32, f32)> = None;
    let mut manual_effort_ms: u32 = 0;
    const MANUAL_EFFORT_TIMEOUT_MS: u32 = 500;

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
                                manual_effort = None;
                                motors.stop();
                                info!("STOP");
                            }
                            Some(Command::Enable) => {
                                manual_effort = None;
                                ctrl.reset();
                                ctrl.set_home(estimator.wheel_pos(), estimator.yaw_pos());
                                ctrl.enabled = true;
                                reference.enabled = true;
                                info!("CTRL ON: k1={:.2} k2={:.2} k3={:.2} k4={:.2} kyaw={:.2} theq={:.2}",
                                    ctrl.k_pitch, ctrl.k_pitch_rate, ctrl.k_pos, ctrl.k_vel, ctrl.k_yaw, ctrl.theta_eq);
                            }
                            Some(Command::Disable) => {
                                ctrl.enabled = false;
                                ctrl.reset();
                                reference.enabled = false;
                                manual_effort = None;
                                motors.stop();
                                info!("CTRL OFF");
                            }
                            Some(Command::SetEffort(l, r)) => {
                                if ctrl.enabled {
                                    info!("EFFORT ignored: controller is on");
                                } else {
                                    manual_effort = Some((l, r));
                                    manual_effort_ms = millis();
                                    info!("EFFORT L={:.1} R={:.1}", l, r);
                                }
                            }
                            Some(Command::SetKPitch(v)) => {
                                ctrl.k_pitch = v;
                                info!("K1={:.2}", v);
                            }
                            Some(Command::SetKPitchRate(v)) => {
                                ctrl.k_pitch_rate = v;
                                info!("K2={:.2}", v);
                            }
                            Some(Command::SetKPos(v)) => {
                                ctrl.k_pos = v;
                                info!("K3={:.2}", v);
                            }
                            Some(Command::SetKVel(v)) => {
                                ctrl.k_vel = v;
                                info!("K4={:.2}", v);
                            }
                            Some(Command::SetKYaw(v)) => {
                                ctrl.k_yaw = v;
                                info!("KYAW={:.2}", v);
                            }
                            Some(Command::SetThetaEq(v)) => {
                                ctrl.theta_eq = v;
                                info!("THEQ={:.2}", v);
                            }
                            Some(Command::SetTargetVel(v)) => {
                                reference.target_vel = v;
                                info!("TVEL={:.2}", v);
                            }
                            Some(Command::SetTargetYawRate(v)) => {
                                reference.target_yaw_rate = v;
                                info!("TYAW={:.2}", v);
                            }
                            None => {
                                info!("ERR: unknown: {line}");
                            }
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

                // Manual effort watchdog
                if manual_effort.is_some()
                    && now.wrapping_sub(manual_effort_ms) > MANUAL_EFFORT_TIMEOUT_MS
                {
                    manual_effort = None;
                    info!("EFFORT timeout → stop");
                }

                let cmd = if !ctrl.enabled {
                    if let Some((l, r)) = manual_effort {
                        MotorCommand { left: l, right: r }
                    } else {
                        ctrl.update(&state, &reference)
                    }
                } else {
                    ctrl.update(&state, &reference)
                };

                let applied_left = cmd.left;
                let applied_right = cmd.right;

                // Always apply command — if controller disabled and no manual
                // effort, the controller returns zero
                motors.apply(cmd);
                inner_loop_count += 1;

                // 50Hz telemetry
                if now.wrapping_sub(last_print_ms) >= 20 {
                    let elapsed_s = now.wrapping_sub(last_print_ms) as f32 / 1000.0;
                    let loop_hz = if elapsed_s > 0.0 {
                        inner_loop_count as f32 / elapsed_s
                    } else {
                        0.0
                    };
                    inner_loop_count = 0;
                    last_print_ms = now;
                    comms::emit_telemetry(
                        &state,
                        &snapshot,
                        &ctrl,
                        estimator.filtered_vel1,
                        estimator.filtered_vel2,
                        loop_hz,
                        applied_left,
                        applied_right,
                    );
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
