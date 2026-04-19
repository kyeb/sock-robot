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
    // Multi-arg: EFFORT L R or EFFORT V (V applied to both)
    let ws_parts: Vec<&str> = line.split_whitespace().collect();
    if ws_parts.len() >= 2 && ws_parts[0].eq_ignore_ascii_case("EFFORT") {
        let l: f32 = ws_parts[1].parse().ok()?;
        if !l.is_finite() {
            return None;
        }
        let r: f32 = if ws_parts.len() >= 3 {
            let r: f32 = ws_parts[2].parse().ok()?;
            if !r.is_finite() {
                return None;
            }
            r
        } else {
            l
        };
        return Some(Command::SetEffort(
            l.clamp(-100.0, 100.0),
            r.clamp(-100.0, 100.0),
        ));
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

struct JsonLine {
    buf: heapless::String<512>,
    first: bool,
}

impl JsonLine {
    fn new() -> Self {
        let mut s = Self {
            buf: heapless::String::new(),
            first: true,
        };
        let _ = s.buf.push('{');
        s
    }

    fn sep(&mut self) {
        if !self.first {
            let _ = self.buf.push(',');
        }
        self.first = false;
    }

    fn num(&mut self, k: &str, v: impl core::fmt::Display) -> &mut Self {
        use core::fmt::Write;
        self.sep();
        let _ = write!(self.buf, "\"{}\":{}", k, v);
        self
    }

    fn flt(&mut self, k: &str, v: f32, prec: usize) -> &mut Self {
        use core::fmt::Write;
        self.sep();
        let _ = write!(self.buf, "\"{}\":{:.*}", k, prec, v);
        self
    }

    fn flag(&mut self, k: &str, v: bool) -> &mut Self {
        self.num(k, v as u8)
    }

    /// Non-blocking send: drop the line if the TX ring is full so the
    /// control loop is never stalled on UART I/O.
    fn emit(&mut self) {
        let _ = self.buf.push('}');
        let _ = self.buf.push('\n');
        unsafe {
            let mut free: usize = 0;
            sys::uart_get_tx_buffer_free_size(0, &mut free);
            if free >= self.buf.len() {
                sys::uart_write_bytes(0, self.buf.as_ptr() as *const _, self.buf.len());
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub fn emit_telemetry(
    state: &RobotState,
    snap: &SensorSnapshot,
    ctrl: &BalanceController,
    vel1: f32,
    vel2: f32,
    loop_hz: f32,
    applied_left: f32,
    applied_right: f32,
) {
    let accel_pitch = -((snap.imu.accel[0] as f64)
        .atan2(snap.imu.accel[2] as f64)
        .to_degrees() as f32);
    let roll = -((snap.imu.accel[1] as f64)
        .atan2(snap.imu.accel[2] as f64)
        .to_degrees() as f32);

    JsonLine::new()
        .num("t", snap.t_ms)
        .flt("ax", snap.imu.accel[0], 3)
        .flt("ay", snap.imu.accel[1], 3)
        .flt("az", snap.imu.accel[2], 3)
        .flt("gx", snap.imu.gyro[0], 3)
        .flt("gy", snap.imu.gyro[1], 3)
        .flt("gz", snap.imu.gyro[2], 3)
        .flt("temp", snap.imu.temp, 1)
        .flt("roll", roll, 1)
        .flt("pitch", state.pitch, 1)
        .flt("ap", accel_pitch, 1)
        .flt("yr", state.yaw_rate, 1)
        .flt("pid", ctrl.effort, 1)
        .flt("p", ctrl.inner_p, 1)
        .flt("i", ctrl.outer_i, 2)
        .flt("d", ctrl.inner_d, 1)
        .flag("pid_on", ctrl.enabled)
        .num("e1", snap.enc1)
        .num("e2", snap.enc2)
        .flt("v1", vel1, 1)
        .flt("v2", vel2, 1)
        .flt("tp", ctrl.target_pitch, 2)
        .flt("op", ctrl.outer_p, 2)
        .flt("wp", state.wheel_pos, 2)
        .flt("pc", ctrl.pos_correction, 3)
        .flt("yc", ctrl.yaw_correction, 2)
        .flt("lhz", loop_hz, 1)
        .flt("al", applied_left, 1)
        .flt("ar", applied_right, 1)
        .emit();
}
