use esp_idf_svc::hal::gpio::PinDriver;
use esp_idf_svc::hal::ledc::{config::TimerConfig, LedcDriver, LedcTimerDriver};
use esp_idf_svc::hal::prelude::*;
use esp_idf_svc::sys;
use log::info;
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
            10, // 10 tick timeout
        )
    };
    if read == 1 {
        Some(byte)
    } else {
        None
    }
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
    info!("sock-robot ready. Commands: M1 <-100..100>, M2 <-100..100>, STOP");

    let mut buf = [0u8; 128];
    let mut pos = 0usize;

    loop {
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
        } else {
            thread::sleep(Duration::from_millis(10));
        }
    }
}
