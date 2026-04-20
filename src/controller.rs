use crate::types::{ControlReference, MotorCommand, RobotState};
use log::info;

// State vector ordering (K1..K4 map to these in order):
//   x = [pitch - θ_eq, pitch_rate, pos - home, vel - tvel]
// Control law: effort = K · x (all gains positive, stable body)
pub struct Controller {
    pub k_pitch: f32,      // K1
    pub k_pitch_rate: f32, // K2
    pub k_pos: f32,        // K3
    pub k_vel: f32,        // K4

    // Yaw: separate decoupled SISO P loop on encoder-derived heading
    pub k_yaw: f32,
    pub k_pos_int: f32, // K5: gain on integrated position error

    // Equilibrium pitch angle (deg). Subtracted so x_pitch=0 at true balance.
    pub theta_eq: f32,

    pub enabled: bool,
    home_pos: f32,
    home_yaw: f32,
    pos_integral: f32,

    // Per-term effort contributions (telemetry only)
    pub u_pitch: f32,
    pub u_pitch_rate: f32,
    pub u_pos: f32,
    pub u_vel: f32,
    pub u_pos_int: f32,
    pub u_yaw: f32,
    pub effort: f32,
}

impl Controller {
    pub fn new() -> Self {
        Self {
            k_pitch: 9.5,
            k_pitch_rate: 0.8,
            k_pos: 2.0,
            k_vel: 8.7,
            k_yaw: 0.5,
            k_pos_int: 5.0,
            theta_eq: 1.22,
            enabled: false,
            home_pos: 0.0,
            home_yaw: 0.0,
            pos_integral: 0.0,
            u_pitch: 0.0,
            u_pitch_rate: 0.0,
            u_pos: 0.0,
            u_vel: 0.0,
            u_pos_int: 0.0,
            u_yaw: 0.0,
            effort: 0.0,
        }
    }

    pub fn update(&mut self, state: &RobotState, reference: &ControlReference) -> MotorCommand {
        if !reference.enabled || !self.enabled {
            self.reset();
            return MotorCommand {
                left: 0.0,
                right: 0.0,
            };
        }

        if !state.pitch.is_finite() || state.pitch.abs() > 30.0 {
            self.enabled = false;
            self.reset();
            info!("SAFETY: controller disabled (tilt={:.1}deg)", state.pitch);
            return MotorCommand {
                left: 0.0,
                right: 0.0,
            };
        }

        // Slide pose setpoints at commanded rates. When tvel=0 this is
        // stationkeeping; when active, clamp so reversals respond immediately.
        self.home_pos += reference.target_vel * state.dt;
        self.home_yaw += reference.target_yaw_rate * state.dt;
        const POS_LEAD_MAX: f32 = 1.0;
        const YAW_LEAD_MAX: f32 = 1.0;
        if reference.target_vel != 0.0 {
            self.home_pos = self.home_pos.clamp(
                state.wheel_pos - POS_LEAD_MAX,
                state.wheel_pos + POS_LEAD_MAX,
            );
        }
        if reference.target_yaw_rate != 0.0 {
            self.home_yaw = self
                .home_yaw
                .clamp(state.yaw_pos - YAW_LEAD_MAX, state.yaw_pos + YAW_LEAD_MAX);
        }

        let x_pitch = state.pitch - self.theta_eq;
        let x_pitch_rate = state.pitch_rate;
        let x_pos = state.wheel_pos - self.home_pos;
        let x_vel = state.wheel_vel - reference.target_vel;

        self.u_pitch = self.k_pitch * x_pitch;
        self.u_pitch_rate = self.k_pitch_rate * x_pitch_rate;
        self.u_pos = self.k_pos * x_pos;
        self.u_vel = self.k_vel * x_vel;
        self.u_pos_int = self.k_pos_int * self.pos_integral;

        let u_total = self.u_pitch + self.u_pitch_rate + self.u_pos + self.u_vel + self.u_pos_int;

        // Conditional integration: only integrate when not saturated,
        // or when the error would reduce saturation.
        if u_total.abs() < 100.0 || (u_total.signum() != x_pos.signum()) {
            self.pos_integral += x_pos * state.dt;
        }

        self.effort = u_total.clamp(-100.0, 100.0);

        let yaw_error = state.yaw_pos - self.home_yaw;
        self.u_yaw = (self.k_yaw * yaw_error).clamp(-10.0, 10.0);

        MotorCommand {
            left: (self.effort - self.u_yaw).clamp(-100.0, 100.0),
            right: (self.effort + self.u_yaw).clamp(-100.0, 100.0),
        }
    }

    pub fn set_home(&mut self, pos: f32, yaw: f32) {
        self.home_pos = pos;
        self.home_yaw = yaw;
    }

    pub fn reset(&mut self) {
        self.pos_integral = 0.0;
        self.u_pitch = 0.0;
        self.u_pitch_rate = 0.0;
        self.u_pos = 0.0;
        self.u_vel = 0.0;
        self.u_pos_int = 0.0;
        self.u_yaw = 0.0;
        self.effort = 0.0;
    }
}
