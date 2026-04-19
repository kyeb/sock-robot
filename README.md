# sock-robot

Segway-style self-balancing two-wheel robot. ESP32 + Rust firmware, React dashboard for live telemetry and LQR tuning.

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

# Send commands / inspect live telemetry
scripts/cmd.py ENABLE
scripts/cmd.py K1 1.0
scripts/cmd.py ctrlrun     # analyze most recent controller-on run
```

## Sign conventions

- **Pitch:** positive = leaning forward (AX negative on IMU)
- **Encoders:** positive = robot moves forward
- **Motor effort:** positive = drive wheels forward (reaction torque tilts body backward)
- **Motor 2** is mounted opposite, so enc2 is negated and motor 2 direction is inverted in firmware

Mark "forward" on the robot with tape — the physical chassis is symmetrical.

## Control architecture

Single-law LQR over state `x = [pitch − θ_eq, pitch_rate, pos − home, vel − tvel]`:

```
effort = K1·x_pitch + K2·x_pitch_rate + K3·x_pos + K4·x_vel
```

Runs at 200 Hz. Yaw is a separate decoupled P loop on encoder divergence.

## Serial commands

Send over UART or via dashboard/bridge WebSocket:

```
ENABLE / DISABLE / STOP
K1 / K2 / K3 / K4 <val>        # LQR state-feedback gains
KYAW <val>                      # yaw P gain
THEQ <val>                      # equilibrium pitch angle (deg)
TVEL / TYAW <val>              # target velocity / yaw rate
EFFORT <L> [R]                 # manual motor effort (controller must be off)
```
