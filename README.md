# sock-robot

Segway-style self-balancing two-wheel robot. ESP32 + Rust firmware, React dashboard for live telemetry and PID tuning.

## Hardware

- **MCU:** ESP32-WROOM-32 (38-pin devkit)
- **IMU:** SparkFun LSM6DSO (Qwiic, I2C)
- **Motors:** 2x Pololu 37D 50:1 12V w/ 64 CPR encoder
- **Driver:** Cytron MDD10A (dual-channel 10A)

## Wiring

| GPIO | Function     | GPIO | Function     |
|------|--------------|------|--------------|
| 16   | Motor 1 PWM  | 18   | Motor 2 PWM  |
| 17   | Motor 1 DIR  | 19   | Motor 2 DIR  |
| 23   | Encoder 1 A  | 25   | Encoder 2 A* |
| 4    | Encoder 1 B  | 26   | Encoder 2 B* |
| 21   | I2C SDA      | 22   | I2C SCL      |

*Encoder 2 is on the left side of the devkit (GPIO5/15 are strapping pins that interfere with flashing).

Encoder Vcc → 3V3, IMU Vcc → 3V3, all GND → common ground.

## Commands

```bash
# Build and flash
./flash.sh

# Run dashboard (two terminals)
scripts/bridge.py          # WebSocket bridge (serial → ws://localhost:8080)
cd dashboard && pnpm dev   # Dashboard at http://localhost:3000

# PID tuning trial
scripts/tune.py            # Interactive tuning with live stats

# Analyze saved trials
scripts/analyze_trials.py data/trials/trial_*.jsonl
```

## Sign conventions

- **Pitch:** positive = leaning forward (AX negative on IMU)
- **Encoders:** positive = robot moves forward
- **Motor effort:** positive = drive wheels forward (reaction torque tilts body backward)
- **Motor 2** is mounted opposite, so enc2 is negated and motor 2 direction is inverted in firmware

Mark "forward" on the robot with tape — the physical chassis is symmetrical.

## Control architecture

Cascaded PID: inner P+D angle loop at 200Hz, outer PI velocity loop at ~50Hz.

- **Inner loop:** `effort = angle_kp * (pitch - target_pitch) + angle_kd * pitch_rate`
- **Outer loop:** velocity error → target_pitch. If drifting forward, commands backward lean to decelerate.

## Serial commands

Send over UART or via dashboard/bridge WebSocket:

```
PID_ON / PID_OFF / STOP
KP <val> / KD <val>           # inner angle loop
VKP <val> / VKI <val>         # outer velocity loop
TARGET <val>                   # target velocity (rad/s)
```

Current gains: angle_kp=15, angle_kd=0.35, vel_kp=0.3, vel_ki=0.6.
