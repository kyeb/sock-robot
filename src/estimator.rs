use crate::types::{ImuReading, RobotState, SensorSnapshot};

// 64 CPR (already includes quadrature) × 50:1 gearbox = 3,200 counts per output shaft rev
const COUNTS_PER_REV: f32 = 3_200.0;
const COMP_ALPHA: f32 = 0.98;
const VEL_FILTER_ALPHA: f32 = 0.8;
const GYRO_FILTER_ALPHA: f32 = 0.85;

fn accel_angle(ax: f32, az: f32) -> f32 {
    -((ax as f64).atan2(az as f64).to_degrees() as f32)
}

pub struct Estimator {
    angle: f32,
    filtered_pitch_rate: f32,
    prev_enc1: i32,
    prev_enc2: i32,
    pub filtered_vel1: f32,
    pub filtered_vel2: f32,
    wheel_pos: f32,
    yaw_pos: f32,
}

impl Estimator {
    pub fn new() -> Self {
        Self {
            angle: 0.0,
            filtered_pitch_rate: 0.0,
            prev_enc1: 0,
            prev_enc2: 0,
            filtered_vel1: 0.0,
            filtered_vel2: 0.0,
            wheel_pos: 0.0,
            yaw_pos: 0.0,
        }
    }

    pub fn init_angle(&mut self, reading: &ImuReading) {
        self.angle = accel_angle(reading.accel[0], reading.accel[2]);
    }

    pub fn wheel_pos(&self) -> f32 {
        self.wheel_pos
    }

    pub fn yaw_pos(&self) -> f32 {
        self.yaw_pos
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
        self.filtered_vel1 =
            VEL_FILTER_ALPHA * self.filtered_vel1 + (1.0 - VEL_FILTER_ALPHA) * raw_vel1;
        self.filtered_vel2 =
            VEL_FILTER_ALPHA * self.filtered_vel2 + (1.0 - VEL_FILTER_ALPHA) * raw_vel2;

        // Position from encoder counts directly (not integrated velocity — no lag or drift)
        let avg_counts = (snap.enc1 + snap.enc2) as f32 / 2.0;
        self.wheel_pos = (avg_counts / COUNTS_PER_REV) * std::f32::consts::TAU;

        // Yaw from encoder divergence: (e1 - e2) in radians
        let diff_counts = (snap.enc1 - snap.enc2) as f32;
        self.yaw_pos = (diff_counts / COUNTS_PER_REV) * std::f32::consts::TAU;

        let yaw_rate = snap.imu.gyro[2].to_degrees();

        self.filtered_pitch_rate =
            GYRO_FILTER_ALPHA * self.filtered_pitch_rate + (1.0 - GYRO_FILTER_ALPHA) * gyro_rate;

        RobotState {
            pitch: self.angle,
            pitch_rate: self.filtered_pitch_rate,
            wheel_vel: (self.filtered_vel1 + self.filtered_vel2) / 2.0,
            wheel_pos: self.wheel_pos,
            yaw_pos: self.yaw_pos,
            yaw_rate,
            dt,
        }
    }
}
