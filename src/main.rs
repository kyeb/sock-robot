use esp_idf_svc::hal::gpio::PinDriver;
use esp_idf_svc::hal::i2c::{I2cConfig, I2cDriver};
use esp_idf_svc::hal::ledc::{config::TimerConfig, LedcDriver, LedcTimerDriver};
use esp_idf_svc::hal::prelude::*;
use esp_idf_svc::sys;
use log::info;
use lsm6dso::{AccelerometerOutput, GyroscopeFullScale, GyroscopeOutput, Lsm6dso};
use std::thread;
use std::time::Duration;

struct PidController {
    kp: f32,
    ki: f32,
    kd: f32,
    target: f32,
    integral: f32,
    prev_error: f32,
    enabled: bool,
    output: f32,
    p_term: f32,
    i_term: f32,
    d_term: f32,
}

impl PidController {
    fn new(kp: f32, ki: f32, kd: f32, target: f32) -> Self {
        Self {
            kp,
            ki,
            kd,
            target,
            integral: 0.0,
            prev_error: 0.0,
            enabled: false,
            output: 0.0,
            p_term: 0.0,
            i_term: 0.0,
            d_term: 0.0,
        }
    }

    fn update(&mut self, pitch: f32, pitch_rate: f32, dt: f32) -> f32 {
        if !self.enabled || dt <= 0.0 {
            self.integral = 0.0;
            self.prev_error = 0.0;
            self.output = 0.0;
            return 0.0;
        }

        let error = pitch - self.target;

        self.integral += error * dt;
        self.integral = self.integral.clamp(-5.0, 5.0);

        self.prev_error = error;

        self.p_term = self.kp * error;
        self.i_term = self.ki * self.integral;
        self.d_term = self.kd * pitch_rate;
        self.output = self.p_term + self.i_term + self.d_term;

        if !self.output.is_finite() {
            self.enabled = false;
            self.reset();
            return 0.0;
        }

        self.output = self.output.clamp(-60.0, 60.0);
        self.output
    }

    fn reset(&mut self) {
        self.integral = 0.0;
        self.prev_error = 0.0;
        self.output = 0.0;
        self.p_term = 0.0;
        self.i_term = 0.0;
        self.d_term = 0.0;
    }
}

fn parse_command(line: &str) -> Option<Command> {
    let line = line.trim();
    if line.eq_ignore_ascii_case("STOP") {
        return Some(Command::Stop);
    }
    if line.eq_ignore_ascii_case("PID_ON") {
        return Some(Command::PidOn);
    }
    if line.eq_ignore_ascii_case("PID_OFF") {
        return Some(Command::PidOff);
    }
    let parts: Vec<&str> = line.splitn(2, ' ').collect();
    if parts.len() != 2 {
        return None;
    }
    let val: f32 = parts[1].parse().ok()?;
    if !val.is_finite() {
        return None;
    }
    match parts[0].to_ascii_uppercase().as_str() {
        "KP" => Some(Command::SetKp(val.clamp(0.0, 50.0))),
        "KI" => Some(Command::SetKi(val.clamp(0.0, 200.0))),
        "KD" => Some(Command::SetKd(val.clamp(0.0, 50.0))),
        "TARGET" => Some(Command::SetTarget(val.clamp(-15.0, 15.0))),
        _ => None,
    }
}

enum Command {
    Stop,
    PidOn,
    PidOff,
    SetKp(f32),
    SetKi(f32),
    SetKd(f32),
    SetTarget(f32),
}

const MAX_MOTOR_PCT: i32 = 60;

fn set_motor(
    pwm: &mut LedcDriver<'_>,
    dir: &mut PinDriver<'_, impl esp_idf_svc::hal::gpio::OutputPin, esp_idf_svc::hal::gpio::Output>,
    speed: i32,
    max_duty: u32,
    inverted: bool,
) {
    let speed = speed.clamp(-MAX_MOTOR_PCT, MAX_MOTOR_PCT);
    let forward = if inverted { speed <= 0 } else { speed >= 0 };
    if forward {
        dir.set_low().unwrap();
    } else {
        dir.set_high().unwrap();
    }
    let duty = (speed.unsigned_abs() as u32) * max_duty / 100;
    pwm.set_duty(duty).unwrap();
}

fn stop_motors(pwm1: &mut LedcDriver<'_>, pwm2: &mut LedcDriver<'_>) {
    pwm1.set_duty(0).unwrap();
    pwm2.set_duty(0).unwrap();
}

/// Read a byte from UART0 using raw ESP-IDF uart_read_bytes
fn uart_read_byte() -> Option<u8> {
    let mut byte = 0u8;
    let read = unsafe {
        sys::uart_read_bytes(
            0, // UART0
            &mut byte as *mut u8 as *mut _,
            1,
            1, // 1 tick timeout (~10ms at 100Hz tick rate)
        )
    };
    if read == 1 {
        Some(byte)
    } else {
        None
    }
}

/// Get milliseconds since boot
fn millis() -> u32 {
    unsafe { (sys::esp_timer_get_time() / 1000) as u32 }
}

fn main() {
    esp_idf_svc::sys::link_patches();
    esp_idf_svc::log::EspLogger::initialize_default();

    let peripherals = Peripherals::take().unwrap();

    // Install UART0 driver (needed for uart_read_bytes)
    unsafe {
        sys::uart_driver_install(0, 1024, 0, 0, std::ptr::null_mut(), 0);
    }

    // Motor 1: PWM on GPIO16, DIR on GPIO17
    let timer1 = LedcTimerDriver::new(
        peripherals.ledc.timer0,
        &TimerConfig::default().frequency(1.kHz().into()),
    )
    .unwrap();
    let mut pwm1 =
        LedcDriver::new(peripherals.ledc.channel0, &timer1, peripherals.pins.gpio16).unwrap();
    let mut dir1 = PinDriver::output(peripherals.pins.gpio17).unwrap();

    // Motor 2: PWM on GPIO18, DIR on GPIO19
    let timer2 = LedcTimerDriver::new(
        peripherals.ledc.timer1,
        &TimerConfig::default().frequency(1.kHz().into()),
    )
    .unwrap();
    let mut pwm2 =
        LedcDriver::new(peripherals.ledc.channel1, &timer2, peripherals.pins.gpio18).unwrap();
    let mut dir2 = PinDriver::output(peripherals.pins.gpio19).unwrap();

    let max_duty = pwm1.get_max_duty();

    // IMU: I2C on GPIO21 (SDA), GPIO22 (SCL)
    let i2c = I2cDriver::new(
        peripherals.i2c0,
        peripherals.pins.gpio21, // SDA
        peripherals.pins.gpio22, // SCL
        &I2cConfig::new().baudrate(400.kHz().into()),
    )
    .unwrap();

    let mut imu = Lsm6dso::new(i2c, 0x6B);
    imu.check().expect("LSM6DSO not found on I2C bus");
    imu.set_accelerometer_output(AccelerometerOutput::Rate416)
        .unwrap();
    imu.set_gyroscope_output(GyroscopeOutput::Rate416)
        .unwrap();
    imu.set_gyroscope_scale(GyroscopeFullScale::Dps500)
        .unwrap();

    // Calibrate gyro bias at startup (robot must be stationary)
    info!("Calibrating gyro...");
    let mut gyro_bias_y: f32 = 0.0;
    let mut gyro_bias_z: f32 = 0.0;
    let cal_samples = 200;
    for _ in 0..cal_samples {
        thread::sleep(Duration::from_millis(5));
        if let Ok(data) = imu.read_all() {
            gyro_bias_y += data.gyro_y;
            gyro_bias_z += data.gyro_z;
        }
    }
    gyro_bias_y /= cal_samples as f32;
    gyro_bias_z /= cal_samples as f32;
    info!("Gyro bias: Y={:.4} Z={:.4} rad/s", gyro_bias_y, gyro_bias_z);

    // Complementary filter state
    let accel_angle = |ax: f32, az: f32| -> f32 {
        -((ax as f64).atan2(az as f64).to_degrees() as f32)
    };
    // Initialize angle from accelerometer
    let init_data = imu.read_all().unwrap();
    let mut angle: f32 = accel_angle(init_data.accel_x, init_data.accel_z);
    let comp_alpha: f32 = 0.98;

    // PID controller
    let mut pid = PidController::new(15.0, 40.0, 0.55, 0.0);

    info!("sock-robot ready. Commands: STOP, PID_ON, PID_OFF, KP/KI/KD/TARGET <val>");

    let mut buf = [0u8; 128];
    let mut pos = 0usize;
    let mut buf_overflow = false;
    let mut last_imu_ms = millis();
    let mut last_print_ms = millis();

    loop {
        // Handle serial commands (non-blocking)
        if let Some(byte) = uart_read_byte() {
            if byte == b'\n' || byte == b'\r' {
                if pos > 0 && !buf_overflow {
                    if let Ok(line) = core::str::from_utf8(&buf[..pos]) {
                        match parse_command(line) {
                            Some(Command::Stop) => {
                                pid.enabled = false;
                                pid.reset();
                                stop_motors(&mut pwm1, &mut pwm2);
                                info!("STOP");
                            }
                            Some(Command::PidOn) => {
                                pid.reset();
                                pid.enabled = true;
                                info!("PID ON: Kp={:.2} Ki={:.2} Kd={:.2} target={:.1}", pid.kp, pid.ki, pid.kd, pid.target);
                            }
                            Some(Command::PidOff) => {
                                pid.enabled = false;
                                pid.reset();
                                stop_motors(&mut pwm1, &mut pwm2);
                                info!("PID OFF");
                            }
                            Some(Command::SetKp(v)) => { pid.kp = v; info!("KP={:.2}", v); }
                            Some(Command::SetKi(v)) => { pid.ki = v; pid.integral = 0.0; info!("KI={:.2}", v); }
                            Some(Command::SetKd(v)) => { pid.kd = v; info!("KD={:.2}", v); }
                            Some(Command::SetTarget(v)) => { pid.target = v; info!("TARGET={:.1}", v); }
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

        // Read IMU at ~200Hz (every 5ms)
        if now.wrapping_sub(last_imu_ms) >= 5 {
            let dt = now.wrapping_sub(last_imu_ms) as f32 / 1000.0;
            last_imu_ms = now;
            if let Ok(data) = imu.read_all() {
                // Complementary filter: fast gyro integration + slow accel correction
                let gyro_rate = (data.gyro_y - gyro_bias_y).to_degrees();
                let accel_ang = accel_angle(data.accel_x, data.accel_z);
                angle = comp_alpha * (angle + gyro_rate * dt) + (1.0 - comp_alpha) * accel_ang;

                let pitch = angle;
                let roll = accel_angle(data.accel_y, data.accel_z);

                // Safety: disable PID if robot has fallen over
                if !pitch.is_finite() || pitch.abs() > 30.0 {
                    if pid.enabled {
                        pid.enabled = false;
                        pid.reset();
                        stop_motors(&mut pwm1, &mut pwm2);
                        info!("SAFETY: PID disabled (tilt={:.1}°)", pitch);
                    }
                }

                // Run PID controller (D term uses gyro rate directly)
                let motor_output = pid.update(pitch, gyro_rate, dt);
                let yaw_rate = (data.gyro_z - gyro_bias_z).to_degrees();
                if pid.enabled {
                    let speed = motor_output as i32;
                    set_motor(&mut pwm1, &mut dir1, speed, max_duty, false);
                    set_motor(&mut pwm2, &mut dir2, speed, max_duty, true);
                }

                // Print as JSON line at ~50Hz (every 20ms) to avoid saturating UART
                if now.wrapping_sub(last_print_ms) >= 20 {
                    last_print_ms = now;
                    let accel_pitch = accel_angle(data.accel_x, data.accel_z);
                    println!(
                        "{{\"t\":{},\"ax\":{:.3},\"ay\":{:.3},\"az\":{:.3},\"gx\":{:.3},\"gy\":{:.3},\"gz\":{:.3},\"temp\":{:.1},\"roll\":{:.1},\"pitch\":{:.1},\"ap\":{:.1},\"yr\":{:.1},\"pid\":{:.1},\"p\":{:.1},\"i\":{:.2},\"d\":{:.1},\"pid_on\":{}}}",
                        now, data.accel_x, data.accel_y, data.accel_z,
                        data.gyro_x, data.gyro_y, data.gyro_z, data.temp,
                        roll, pitch, accel_pitch, yaw_rate,
                        pid.output, pid.p_term, pid.i_term, pid.d_term, pid.enabled
                    );
                }
            }
        }

        // Small sleep to yield CPU — short enough for 200Hz loop
        thread::sleep(Duration::from_micros(500));
    }
}
