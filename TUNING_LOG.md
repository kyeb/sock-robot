# 200 Hz Tuning Log

Trials on the current firmware state: 200 Hz control loop (CONFIG_FREERTOS_HZ=1000, thread::sleep(500µs)), standard filter TCs (COMP_TC_S=0.495, GYRO_FILTER_TC_S=0.062, VEL_FILTER_TC_S=0.045), non-blocking UART @ 921600.

Metrics from `scripts/cmd.py pidrun`:
- `pitch_std` — stdev of raw pitch (°)
- `fast_std` — stdev of pitch minus 1s moving avg (HF ring, °)
- `slow_range` — range of 1s moving avg (LF sway, °)
- `wp_pkpk` — per-5s wheel_pos pk-pk (rad). `↘` = shrinking = stable. `↗` = growing = unstable.

## Gain sweep

Outer loops off unless noted.

| KP | KD | PBIAS | Outer | pitch | fast | slow | wp trend | verdict |
|---:|---:|---:|---|---:|---:|---:|---|---|
| 10 | 0.5 | 1.25 | VKP=0.25, PKP=0.5, PKD=0.4 | ~1.6 | ~1.4 | ~3.6 | ↗ | baseline; hit walls |
| 10 | 0.5 | 1.25 | PKP=0.25 | — | — | — | ↗ | worse growth |
| 10 | 0.5 | 1.25 | all off | 1.74 / 1.40 | 1.57 / 1.25 | 4.42 / 2.78 | ↗ | still grew |
| 10 | 0.5 | 1.25 | VKP=0, PKP=0 | 0.90 | 0.82 | — | ↗ | unstable mode persists |
| 8 | 0.5 | 1.25 | off | 2.11 | 1.59 | 6.31 | ↗ | slow worse |
| 12 | 0.5 | 1.25 | off | 2.69 | 2.56 | 4.62 | ↗ | fast ring |
| 15 | 0.35 | 1.25 | off | — | — | — | effort ±100 | saturated HF |
| 10 | 0.3 | 1.25 | off | 2.04 | 1.97 | 5.08 | ↗ | noise up, slow worse |
| 10 | 0.7 | 1.25 | off | 2.27 | 2.12 | 5.53 | ↗ | noise amp |
| 10 | 1.0 | 1.25 | off | — | — | — | effort ±100 | D noise blowup |
| 10 | 0.5 | **1.5** | off | 1.09 | **1.01** | 5.68 | ↘ | first visibly better |
| 10 | 0.5 | 1.75 | off | 1.33 | 1.25 | 3.09 | ↗ | too far |
| 10 | 0.5 | 1.35 | off | 1.03 | 0.95 | 1.93 | ~ | best PBIAS so far |
| 10 | 0.5 | 1.2 | off | 1.59 | 1.41 | 3.46 | ↗ | regressed |
| 10 | 0.5 | 1.35 | VKP=0.05 | 0.94 / 1.06 / 1.87 | 0.82 / 1.06 / 2.00 | 1.66–2.55 | mixed | high variance |
| 10 | 0.5 | 1.35 | +VKD=0.02 | 5.20 | 5.55 | 7.70 | effort ±100 | velocity D amplifies encoder noise, catastrophic |
| 10 | 0.5 | 1.35 | +VKI=0.05 | 1.51 | 1.54 | 2.31 | ↗ | integral destabilizes |
| 10 | 0.5 | 1.35 | VKP=0.05, PKP=0.2 | 0.70 | 0.65 | 1.67 | ↘ | new best |
| 10 | 0.5 | 1.35 | VKP=0.05, PKP=0.35 | 1.68 | 1.74 | 3.09 | ↗ | too strong |
| 10 | 0.5 | 1.35 | VKP=0.05, PKP=0.2, PKD=0.1 | 1.97 | 2.04 | 5.37 | ↗ | PKD destabilizes soft-inner |
| 6 | 0.3 | 1.35 | VKP=0.05, PKP=0.2 | 1.34 | 0.99 | 4.56 | ↗ | fast much better, slow worse |
| 4 | 0.2 | 1.35 | VKP=0.05, PKP=0.2 | 1.67 | 1.16 | 5.87 | leans on hand | too soft to catch |
| 6 | 0.3 | 1.35 | VKP=0.1, PKP=0.1 | 2.16 | 1.74 | 6.19 | ↗ | VKP bump bad |
| 6 | 0.3 | 1.35 | VKP=0.05, PKP=0.3 | 3.15 | 2.54 | 13.56 | ↗ | PKP too strong at soft inner |
| 6 | 0.3 | 1.35 | VKP=0.05, PKP=0.1 | 1.50 | 1.26 | 4.40 | ↗ | still drifts |
| **8** | **0.4** | 1.35 | VKP=0.05, PKP=0.1 | **0.76** | **0.41** | 2.17 | ~ | inner-loop sweet spot; no ring |
| 8 | 0.4 | 1.35 | VKP=0.05, PKP=0.3 | 0.56 | 0.51 | 1.49 | ↘ | strong inner handles stronger pos |
| 8 | 0.4 | 1.35 | VKP=0.05, PKP=0.3, PKD=0.2 | 0.74 | 0.43 | 2.59 | mixed | "leans into wall" visually |
| 12 | 0.5 | 1.35 | VKP=0.05, PKP=0.3, PKD=0.2 | 1.97 | 1.91 | 0.85 | fast ring | too stiff |
| 12 | 0.7 | 1.35 | same | 2.62 | 2.64 | 3.16 | worse | D noise |
| 12 | 0.35 | 1.35 | same | 2.40 | 2.40 | 2.72 | fast ring | KP=12 rings regardless of KD |
| 10 | 0.4 | 1.35 | VKP=0.05, PKP=0.3, PKD=0.2 | 1.05 | 1.01 | 2.62 | ~ | "much much better" visually, some ring |
| 10 | 0.4 | 1.5 | same | 0.50 | 0.49 | 0.87 | ↘ | best-ever metrics but 1.5 may mask |
| 10 | 0.4 | 1.6 | same | 1.57 | 1.38 | 4.35 | ↗ | overshoot |
| **10** | **0.4** | **1.35** | **VKP=0.05, PKP=0.3, PKD=0.2** | **0.37** | **0.37** | **0.76** | **↘** | **current checkpoint (commit 1543e24)** |

## Filter experiment (flashed, then reverted)

| COMP_TC | GYRO_TC | result |
|---:|---:|---|
| 0.495 | 0.062 | baseline (current) |
| 0.15 | 0.02 | oscillated much more wildly than baseline — reverted |

Shorter filters reduced phase lag but let in too much noise. Hypothesis that filter lag was the cause of slow mode was disproven.

## Open questions

1. **Recoverability from perturbations.** Current checkpoint is stable when undisturbed but accelerates into walls when bumped. Pre-200 Hz `best` recovered from small bumps; this config doesn't.
2. **KP ceiling.** KP=12 rings at 5 Hz regardless of KD at current filters. Either:
   - Slower gyro filter (GYRO_FILTER_TC_S > 0.062) to allow KP higher with less D noise
   - Motor effort lowpass to emulate slower plant
3. **Physical PBIAS.** Not empirically measured. Tilt-till-static test would give a ground truth.
4. **Motor direction sanity check.** After the dir2 wire issue earlier, worth verifying both motors drive the same direction for same sign of effort.
5. **LQR as structural fix.** Cascaded PID ran out of room; LQR on [pos, vel, pitch, pitch_rate] is the textbook answer.

## Observational rules learned

- Higher KP at 200 Hz rings before it catches — ceiling ~10–11 with current filters.
- D noise dominates for KD > 0.6 at current gyro filter.
- Velocity-loop D (VKD) on encoder-derived velocity is poison — tiny values saturate effort instantly.
- VKI tends to destabilize the cascade rather than help.
- PKP/PKD tolerance depends on inner-loop stiffness: soft inner → low PKP needed; stiff inner → can handle PKP=0.3.
- Single-window metrics are noisy; look at per-5s envelope for "is amplitude growing" signal.
- Good metrics can be artifact of robot resting against hand/wall — cross-check visually.
