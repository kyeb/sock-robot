use crate::controller::BalanceController;
use crate::types::{Command, RobotState, SensorSnapshot};
use esp_idf_svc::sys;

pub fn uart_read_byte() -> Option<u8> {
    let mut byte = 0u8;
    let read = unsafe { sys::uart_read_bytes(0, &mut byte as *mut u8 as *mut _, 1, 1) };
    if read == 1 {
        Some(byte)
    } else {
        None
    }
}

pub fn parse_command(line: &str) -> Option<Command> {
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
        "TVEL" => Some(Command::SetTargetVel(val.clamp(-5.0, 5.0))),
        "TYAW" => Some(Command::SetTargetYawRate(val.clamp(-5.0, 5.0))),
        "VKP" => Some(Command::SetVelKp(val.clamp(0.0, 50.0))),
        "VKI" => Some(Command::SetVelKi(val.clamp(0.0, 200.0))),
        "VKD" => Some(Command::SetVelKd(val.clamp(0.0, 50.0))),
        "PKP" => Some(Command::SetPosKp(val.clamp(0.0, 10.0))),
        "PKD" => Some(Command::SetPosKd(val.clamp(0.0, 10.0))),
        "YKP" => Some(Command::SetYawKp(val.clamp(0.0, 10.0))),
        "PBIAS" => Some(Command::SetPitchBias(val.clamp(-5.0, 5.0))),
        "VILIM" => Some(Command::SetVelIntLimit(val.clamp(0.1, 20.0))),
        _ => None,
    }
}

pub fn emit_telemetry(
    state: &RobotState,
    snap: &SensorSnapshot,
    ctrl: &BalanceController,
    vel1: f32,
    vel2: f32,
) {
    let accel_pitch = -((snap.imu.accel[0] as f64)
        .atan2(snap.imu.accel[2] as f64)
        .to_degrees() as f32);
    let roll = -((snap.imu.accel[1] as f64)
        .atan2(snap.imu.accel[2] as f64)
        .to_degrees() as f32);
    println!(
        "{{\"t\":{},\"ax\":{:.3},\"ay\":{:.3},\"az\":{:.3},\"gx\":{:.3},\"gy\":{:.3},\"gz\":{:.3},\"temp\":{:.1},\"roll\":{:.1},\"pitch\":{:.1},\"ap\":{:.1},\"yr\":{:.1},\"pid\":{:.1},\"p\":{:.1},\"i\":{:.2},\"d\":{:.1},\"pid_on\":{},\"e1\":{},\"e2\":{},\"v1\":{:.1},\"v2\":{:.1},\"tp\":{:.2},\"op\":{:.2},\"wp\":{:.2},\"pc\":{:.3},\"yc\":{:.2}}}",
        snap.t_ms,
        snap.imu.accel[0], snap.imu.accel[1], snap.imu.accel[2],
        snap.imu.gyro[0], snap.imu.gyro[1], snap.imu.gyro[2],
        snap.imu.temp,
        roll, state.pitch, accel_pitch, state.yaw_rate,
        ctrl.effort, ctrl.inner_p, ctrl.outer_i, ctrl.inner_d,
        ctrl.enabled,
        snap.enc1, snap.enc2,
        vel1, vel2,
        ctrl.target_pitch, ctrl.outer_p,
        state.wheel_pos, ctrl.pos_correction, ctrl.yaw_correction,
    );
}
