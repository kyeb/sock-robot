use crate::types::{ControlReference, MotorCommand, RobotState};
use log::info;

pub struct BalanceController {
    // Inner loop (200Hz): angle P+D
    pub angle_kp: f32,
    pub angle_kd: f32,

    // Outer loop (~50Hz): velocity PI
    pub vel_kp: f32,
    pub vel_ki: f32,
    vel_integral: f32,
    vel_integral_limit: f32,

    // Outer loop timing
    outer_loop_counter: u32,
    outer_loop_divisor: u32,
    outer_dt_accum: f32,

    // State
    pub target_pitch: f32,
    pub enabled: bool,

    // Telemetry
    pub inner_p: f32,
    pub inner_d: f32,
    pub outer_p: f32,
    pub outer_i: f32,
    pub effort: f32,
}

impl BalanceController {
    pub fn new() -> Self {
        Self {
            angle_kp: 15.0,
            angle_kd: 0.35,

            vel_kp: 0.3,
            vel_ki: 0.6,
            vel_integral: 0.0,
            vel_integral_limit: 5.0,

            // Run outer loop every 4th cycle: 200Hz / 4 = 50Hz
            outer_loop_counter: 0,
            outer_loop_divisor: 4,
            outer_dt_accum: 0.0,

            target_pitch: 0.0,
            enabled: false,

            inner_p: 0.0,
            inner_d: 0.0,
            outer_p: 0.0,
            outer_i: 0.0,
            effort: 0.0,
        }
    }

    pub fn update(&mut self, state: &RobotState, reference: &ControlReference) -> MotorCommand {
        if !reference.enabled || !self.enabled {
            self.reset();
            return MotorCommand { left: 0.0, right: 0.0 };
        }

        // Safety: disable if tipped over
        if !state.pitch.is_finite() || state.pitch.abs() > 30.0 {
            self.enabled = false;
            self.reset();
            info!("SAFETY: controller disabled (tilt={:.1}deg)", state.pitch);
            return MotorCommand { left: 0.0, right: 0.0 };
        }

        // Outer loop: velocity error -> target pitch (runs at reduced rate)
        self.outer_dt_accum += state.dt;
        self.outer_loop_counter += 1;
        if self.outer_loop_counter >= self.outer_loop_divisor {
            let outer_dt = self.outer_dt_accum;
            self.outer_loop_counter = 0;
            self.outer_dt_accum = 0.0;

            let vel_error = reference.target_vel - state.wheel_vel;
            self.vel_integral += vel_error * outer_dt;
            self.vel_integral = self.vel_integral.clamp(-self.vel_integral_limit, self.vel_integral_limit);

            self.outer_p = self.vel_kp * vel_error;
            self.outer_i = self.vel_ki * self.vel_integral;
            self.target_pitch = (self.outer_p + self.outer_i).clamp(-15.0, 15.0);
        }

        // Inner loop: pitch error -> motor effort (every cycle, 200Hz)
        let pitch_error = state.pitch - self.target_pitch;
        self.inner_p = self.angle_kp * pitch_error;
        self.inner_d = self.angle_kd * state.pitch_rate;
        self.effort = (self.inner_p + self.inner_d).clamp(-100.0, 100.0);

        MotorCommand { left: self.effort, right: self.effort }
    }

    pub fn reset(&mut self) {
        self.vel_integral = 0.0;
        self.target_pitch = 0.0;
        self.outer_loop_counter = 0;
        self.outer_dt_accum = 0.0;
        self.inner_p = 0.0;
        self.inner_d = 0.0;
        self.outer_p = 0.0;
        self.outer_i = 0.0;
        self.effort = 0.0;
    }
}
