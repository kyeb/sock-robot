use crate::types::{ImuReading, RobotState, SensorSnapshot};

// 64 CPR (already includes quadrature) × 50:1 gearbox = 3,200 counts per output shaft rev
const COUNTS_PER_REV: f32 = 3_200.0;
const COMP_ALPHA: f32 = 0.98;
const VEL_FILTER_ALPHA: f32 = 0.8;

fn accel_angle(ax: f32, az: f32) -> f32 {
    -((ax as f64).atan2(az as f64).to_degrees() as f32)
}

pub struct Estimator {
    angle: f32,
    prev_enc1: i32,
    prev_enc2: i32,
    pub filtered_vel1: f32,
    pub filtered_vel2: f32,
}

impl Estimator {
    pub fn new() -> Self {
        Self {
            angle: 0.0,
            prev_enc1: 0,
            prev_enc2: 0,
            filtered_vel1: 0.0,
            filtered_vel2: 0.0,
        }
    }

    pub fn init_angle(&mut self, reading: &ImuReading) {
        self.angle = accel_angle(reading.accel[0], reading.accel[2]);
    }

    pub fn init_encoders(&mut self, enc1: i32, enc2: i32) {
        self.prev_enc1 = enc1;
        self.prev_enc2 = enc2;
    }

    pub fn update(&mut self, snap: &SensorSnapshot) -> RobotState {
        let dt = snap.dt;

        // Complementary filter for pitch
        let gyro_rate = snap.imu.gyro[1].to_degrees();
        let accel_ang = accel_angle(snap.imu.accel[0], snap.imu.accel[2]);
        self.angle = COMP_ALPHA * (self.angle + gyro_rate * dt) + (1.0 - COMP_ALPHA) * accel_ang;

        // Encoder deltas -> wheel velocity
        let d1 = snap.enc1 - self.prev_enc1;
        let d2 = snap.enc2 - self.prev_enc2;
        self.prev_enc1 = snap.enc1;
        self.prev_enc2 = snap.enc2;

        let raw_vel1 = (d1 as f32 / COUNTS_PER_REV) * std::f32::consts::TAU / dt;
        let raw_vel2 = (d2 as f32 / COUNTS_PER_REV) * std::f32::consts::TAU / dt;

        // EMA low-pass filter on wheel velocity
        self.filtered_vel1 = VEL_FILTER_ALPHA * self.filtered_vel1 + (1.0 - VEL_FILTER_ALPHA) * raw_vel1;
        self.filtered_vel2 = VEL_FILTER_ALPHA * self.filtered_vel2 + (1.0 - VEL_FILTER_ALPHA) * raw_vel2;

        let yaw_rate = snap.imu.gyro[2].to_degrees();

        RobotState {
            pitch: self.angle,
            pitch_rate: gyro_rate,
            wheel_vel: (self.filtered_vel1 + self.filtered_vel2) / 2.0,
            yaw_rate,
            dt,
        }
    }
}
