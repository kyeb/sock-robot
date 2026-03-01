use ahrs::{Ahrs, Madgwick};
use esp_idf_svc::hal::gpio::PinDriver;
use esp_idf_svc::hal::i2c::{I2cConfig, I2cDriver};
use esp_idf_svc::hal::ledc::{config::TimerConfig, LedcDriver, LedcTimerDriver};
use esp_idf_svc::hal::prelude::*;
use esp_idf_svc::sys;
use log::info;
use lsm6dso::{AccelerometerOutput, GyroscopeOutput, Lsm6dso};
use nalgebra::Vector3;
use std::thread;
use std::time::Duration;

fn parse_command(line: &str) -> Option<Command> {
    let line = line.trim();
    if line.eq_ignore_ascii_case("STOP") {
        return Some(Command::Stop);
    }
    let parts: Vec<&str> = line.splitn(2, ' ').collect();
    if parts.len() != 2 {
        return None;
    }
    let speed: i32 = parts[1].parse().ok()?;
    let speed = speed.clamp(-100, 100);
    match parts[0].to_ascii_uppercase().as_str() {
        "M1" => Some(Command::Motor1(speed)),
        "M2" => Some(Command::Motor2(speed)),
        _ => None,
    }
}

enum Command {
    Motor1(i32),
    Motor2(i32),
    Stop,
}

fn set_motor(
    pwm: &mut LedcDriver<'_>,
    dir: &mut PinDriver<'_, impl esp_idf_svc::hal::gpio::OutputPin, esp_idf_svc::hal::gpio::Output>,
    speed: i32,
    max_duty: u32,
    inverted: bool,
) {
    let forward = if inverted { speed <= 0 } else { speed >= 0 };
    if forward {
        dir.set_low().unwrap();
    } else {
        dir.set_high().unwrap();
    }
    let duty = (speed.unsigned_abs() as u32) * max_duty / 100;
    pwm.set_duty(duty).unwrap();
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
    imu.set_accelerometer_output(AccelerometerOutput::Rate104)
        .unwrap();
    imu.set_gyroscope_output(GyroscopeOutput::Rate104)
        .unwrap();

    // AHRS filter: Madgwick with 50Hz sample rate, beta=0.1
    let mut ahrs = Madgwick::new(0.02, 0.1);

    info!("sock-robot ready. Commands: M1 <-100..100>, M2 <-100..100>, STOP");

    let mut buf = [0u8; 128];
    let mut pos = 0usize;
    let mut last_imu_ms = millis();

    loop {
        // Handle serial commands (non-blocking)
        if let Some(byte) = uart_read_byte() {
            if byte == b'\n' || byte == b'\r' {
                if pos > 0 {
                    if let Ok(line) = core::str::from_utf8(&buf[..pos]) {
                        match parse_command(line) {
                            Some(Command::Motor1(speed)) => {
                                set_motor(&mut pwm1, &mut dir1, speed, max_duty, false);
                                info!("M1: {speed}");
                            }
                            Some(Command::Motor2(speed)) => {
                                set_motor(&mut pwm2, &mut dir2, speed, max_duty, true);
                                info!("M2: {speed}");
                            }
                            Some(Command::Stop) => {
                                pwm1.set_duty(0).unwrap();
                                pwm2.set_duty(0).unwrap();
                                info!("STOP");
                            }
                            None => {
                                info!("ERR: unknown: {line}");
                            }
                        }
                    }
                    pos = 0;
                }
            } else if pos < buf.len() - 1 {
                buf[pos] = byte;
                pos += 1;
            }
        }

        // Read IMU at ~50Hz (every 20ms)
        let now = millis();
        if now.wrapping_sub(last_imu_ms) >= 20 {
            last_imu_ms = now;
            if let Ok(data) = imu.read_all() {
                // Feed accel+gyro into AHRS filter
                let gyro = Vector3::new(
                    data.gyro_x as f64,
                    data.gyro_y as f64,
                    data.gyro_z as f64,
                );
                let accel = Vector3::new(
                    data.accel_x as f64,
                    data.accel_y as f64,
                    data.accel_z as f64,
                );

                // Compute euler angles from AHRS quaternion
                let (roll, pitch, yaw): (f64, f64, f64) = if ahrs.update_imu(&gyro, &accel).is_ok() {
                    let q = ahrs.quat;
                    let (r, p, y) = q.euler_angles();
                    (r.to_degrees(), p.to_degrees(), y.to_degrees())
                } else {
                    (0.0, 0.0, 0.0)
                };

                // Print as JSON line — println goes to UART0 directly
                println!(
                    "{{\"t\":{},\"ax\":{:.3},\"ay\":{:.3},\"az\":{:.3},\"gx\":{:.3},\"gy\":{:.3},\"gz\":{:.3},\"temp\":{:.1},\"roll\":{:.1},\"pitch\":{:.1},\"yaw\":{:.1}}}",
                    now, data.accel_x, data.accel_y, data.accel_z,
                    data.gyro_x, data.gyro_y, data.gyro_z, data.temp,
                    roll, pitch, yaw
                );
            }
        }

        // Small sleep to avoid busy-spinning when no UART data
        thread::sleep(Duration::from_millis(1));
    }
}
