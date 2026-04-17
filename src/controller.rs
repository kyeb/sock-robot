use crate::types::{ControlReference, MotorCommand, RobotState};
use log::info;

pub struct BalanceController {
    // Inner loop (200Hz): angle P+D
    pub angle_kp: f32,
    pub angle_kd: f32,

    // Outer loop (~50Hz): velocity PID
    pub vel_kp: f32,
    pub vel_ki: f32,
    pub vel_kd: f32,
    vel_integral: f32,
    pub vel_integral_limit: f32,
    prev_vel_error: f32,

    // Position hold: P on wheel_pos -> target_vel offset
    pub pos_kp: f32,
    pub pos_kd: f32,
    home_pos: f32,

    // Yaw correction: P on encoder divergence -> differential effort
    pub yaw_kp: f32,
    home_yaw: f32,

    pub pitch_bias: f32,

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
    pub pos_correction: f32,
    pub yaw_correction: f32,
}

impl BalanceController {
    pub fn new() -> Self {
        Self {
            angle_kp: 10.0,
            angle_kd: 0.4,

            vel_kp: 0.05,
            vel_ki: 0.0,
            vel_kd: 0.0,
            vel_integral: 0.0,
            vel_integral_limit: 4.0,
            prev_vel_error: 0.0,

            pos_kp: 0.3,
            pos_kd: 0.2,
            home_pos: 0.0,

            yaw_kp: 0.5,
            home_yaw: 0.0,

            // Tuned by iterating: set PBIAS at runtime, toggle PID off/on with
            // 50-200ms gaps, and measure startup drift (dwp). When PBIAS matches the
            // robot's physical balance angle, the integrator starts near zero and the
            // robot doesn't drift on PID restart. Found by observing that the integrator
            // was always saturated compensating for the CoG offset — this moves that
            // constant offset out of the integrator and into a fixed bias, freeing the
            // integrator for dynamic corrections.
            pitch_bias: 1.35,

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
            pos_correction: 0.0,
            yaw_correction: 0.0,
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

        // Safety: disable if tipped over
        if !state.pitch.is_finite() || state.pitch.abs() > 30.0 {
            self.enabled = false;
            self.reset();
            info!("SAFETY: controller disabled (tilt={:.1}deg)", state.pitch);
            return MotorCommand {
                left: 0.0,
                right: 0.0,
            };
        }

        // Outer loop: velocity error -> target pitch (runs at reduced rate)
        self.outer_dt_accum += state.dt;
        self.outer_loop_counter += 1;
        if self.outer_loop_counter >= self.outer_loop_divisor {
            let outer_dt = self.outer_dt_accum;
            self.outer_loop_counter = 0;
            self.outer_dt_accum = 0.0;

            // Slide pose setpoints at commanded rates (Twist-style v/ω interface).
            // home_pos/home_yaw track the command so position/heading hold does
            // not fight commanded motion, and becomes stationkeeping when the
            // command is zero. While a command is active, clamp the setpoint
            // distance from the actual position so reversing direction responds
            // immediately; when the command is zero we skip the clamp so the
            // position loop pulls the robot all the way back to its anchor.
            self.home_pos += reference.target_vel * outer_dt;
            self.home_yaw += reference.target_yaw_rate * outer_dt;
            const POS_LEAD_MAX: f32 = 1.0; // rad
            const YAW_LEAD_MAX: f32 = 1.0; // rad (encoder-derived)
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

            // Position hold: PD on position error
            // P drives toward home, D damps approach to prevent overshoot
            let pos_error = self.home_pos - state.wheel_pos;
            self.pos_correction = self.pos_kp * pos_error - self.pos_kd * state.wheel_vel;

            // Velocity loop: P sees full error (including position correction),
            // but integrator only tracks the base velocity error (excluding position
            // correction) so position hold doesn't wind up the integrator.
            let base_vel_error = reference.target_vel - state.wheel_vel;
            let full_vel_error = base_vel_error + self.pos_correction;
            self.vel_integral += base_vel_error * outer_dt;
            self.vel_integral = self
                .vel_integral
                .clamp(-self.vel_integral_limit, self.vel_integral_limit);

            self.outer_p = self.vel_kp * full_vel_error;
            self.outer_i = self.vel_ki * self.vel_integral;
            let outer_d = if outer_dt > 0.0 {
                self.vel_kd * (full_vel_error - self.prev_vel_error) / outer_dt
            } else {
                0.0
            };
            self.prev_vel_error = full_vel_error;
            self.target_pitch = (self.outer_p + self.outer_i + outer_d).clamp(-15.0, 15.0);
        }

        // Inner loop: pitch error -> motor effort (every cycle, 200Hz)
        let pitch_error = (state.pitch - self.pitch_bias) - self.target_pitch;
        self.inner_p = self.angle_kp * pitch_error;
        self.inner_d = self.angle_kd * state.pitch_rate;
        self.effort = (self.inner_p + self.inner_d).clamp(-100.0, 100.0);

        // Yaw correction: encoder divergence drives differential effort back toward home_yaw
        // Clamped to ±10% effort so it can't overwhelm balance
        let yaw_error = state.yaw_pos - self.home_yaw;
        self.yaw_correction = (self.yaw_kp * yaw_error).clamp(-10.0, 10.0);

        MotorCommand {
            left: (self.effort - self.yaw_correction).clamp(-100.0, 100.0),
            right: (self.effort + self.yaw_correction).clamp(-100.0, 100.0),
        }
    }

    pub fn set_home(&mut self, pos: f32, yaw: f32) {
        self.home_pos = pos;
        self.home_yaw = yaw;
    }

    pub fn reset(&mut self) {
        self.vel_integral = 0.0;
        self.prev_vel_error = 0.0;
        self.target_pitch = 0.0;
        self.outer_loop_counter = 0;
        self.outer_dt_accum = 0.0;
        self.inner_p = 0.0;
        self.inner_d = 0.0;
        self.outer_p = 0.0;
        self.outer_i = 0.0;
        self.effort = 0.0;
        self.pos_correction = 0.0;
        self.yaw_correction = 0.0;
    }
}
