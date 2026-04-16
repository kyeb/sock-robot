use crate::types::ImuReading;
use esp_idf_svc::hal::i2c::I2cDriver;
use log::info;
use lsm6dso::{AccelerometerOutput, GyroscopeFullScale, GyroscopeOutput, Lsm6dso};
use std::thread;
use std::time::Duration;

pub struct Imu<'d> {
    dev: Lsm6dso<I2cDriver<'d>>,
    gyro_bias_y: f32,
    gyro_bias_z: f32,
}

impl<'d> Imu<'d> {
    pub fn new(i2c: I2cDriver<'d>, addr: u8) -> Self {
        let mut dev = Lsm6dso::new(i2c, addr);
        dev.check().expect("LSM6DSO not found on I2C bus");
        dev.set_accelerometer_output(AccelerometerOutput::Rate416)
            .unwrap();
        dev.set_gyroscope_output(GyroscopeOutput::Rate416).unwrap();
        dev.set_gyroscope_scale(GyroscopeFullScale::Dps500).unwrap();
        Self {
            dev,
            gyro_bias_y: 0.0,
            gyro_bias_z: 0.0,
        }
    }

    pub fn calibrate_bias(&mut self, samples: usize) {
        info!("Calibrating gyro...");
        let mut sum_y: f32 = 0.0;
        let mut sum_z: f32 = 0.0;
        let mut valid = 0usize;
        for _ in 0..samples {
            thread::sleep(Duration::from_millis(5));
            if let Ok(data) = self.dev.read_all() {
                sum_y += data.gyro_y;
                sum_z += data.gyro_z;
                valid += 1;
            }
        }
        if valid > 0 {
            self.gyro_bias_y = sum_y / valid as f32;
            self.gyro_bias_z = sum_z / valid as f32;
        }
        info!(
            "Gyro bias: Y={:.4} Z={:.4} rad/s ({}/{} samples)",
            self.gyro_bias_y, self.gyro_bias_z, valid, samples
        );
    }

    pub fn read(&mut self) -> Option<ImuReading> {
        self.dev.read_all().ok().map(|data| ImuReading {
            accel: [data.accel_x, data.accel_y, data.accel_z],
            gyro: [
                data.gyro_x,
                data.gyro_y - self.gyro_bias_y,
                data.gyro_z - self.gyro_bias_z,
            ],
            temp: data.temp,
        })
    }
}
