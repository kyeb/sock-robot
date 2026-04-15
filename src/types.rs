pub struct ImuReading {
    pub accel: [f32; 3],
    pub gyro: [f32; 3],
    pub temp: f32,
}

pub struct SensorSnapshot {
    pub t_ms: u32,
    pub dt: f32,
    pub imu: ImuReading,
    pub enc1: i32,
    pub enc2: i32,
}

pub struct RobotState {
    pub pitch: f32,
    pub pitch_rate: f32,
    pub wheel_vel: f32,
    pub yaw_rate: f32,
    pub dt: f32,
}

pub struct ControlReference {
    pub target_vel: f32,
    pub enabled: bool,
}

pub struct MotorCommand {
    pub left: f32,
    pub right: f32,
}

pub enum Command {
    Stop,
    PidOn,
    PidOff,
    SetKp(f32),
    SetKi(f32),
    SetKd(f32),
    SetTarget(f32),
    SetVelKp(f32),
    SetVelKi(f32),
}
