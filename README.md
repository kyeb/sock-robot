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

## Serial commands

Send over UART or via dashboard/bridge WebSocket:

```
PID_ON / PID_OFF / STOP
KP <val> / KI <val> / KD <val> / TARGET <val>
```

Current tuned gains: Kp=15, Ki=40, Kd=0.55, target=0.
