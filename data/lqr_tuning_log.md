# LQR Tuning Log

## 2026-04-19: Current best (tagged `best`)

**Gains:** K1=9.5, K2=0.8, K3=2.0, K4=8.7, K5=5.0, KYAW=0.5, THEQ=1.22
**Filters:** GYRO_TC=20ms, VEL_TC=45ms, COMP_TC=495ms

**Performance:** Fast position convergence, no vibration, zero saturation.

## Verified facts

These are backed by data analysis, not speculation:

- **Gyro filter TC is the binding constraint on gain aggressiveness.** At 35ms, sensitivity peak |S|=3.95 at 6.25 Hz. At 20ms, |S|=1.69. Measured via chirp excitation (data/chirp_gyro20ms.jsonl).
- **K5=5 with gyro 35ms triggers 6.25 Hz pitch-rate oscillation.** Spectral analysis: u_prate=56%, u_pitch=28% at 6.25 Hz. The integrator (u_pint=0%) is not the source — it excites pitch transients that resonate through the filter-lagged pitch rate channel.
- **K5=5 with gyro 20ms is stable.** The reduced filter lag provides enough margin.
- **K1=9.5 and K2=0.8 are validated by sysid.** Inverse LQR on both PRBS and chirp identified models reproduces these values (residual ≈ 0).
- **K3 predictions from sysid are unreliable.** A[prate,wvel] coupling (~5.5) is a back-EMF artifact confirmed by frequency-domain analysis (magnitude grows with freq, wrong phase at DC). This inflates K3 predictions by 5-40x.
- **Position integrator eliminates drift.** Without K5: 138mm/14s drift. With K5=0.5: 0mm/38s.
- **COMP_TC=150ms is violently unstable.** Motor vibration → accelerometer → pitch estimate → positive feedback. Do not reduce without accel LPF.
- **Sign convention: closed-loop = A + B·K** (not A - B·K). Sysid fits x[n+1]=A·x[n]+B·u, firmware applies effort=+K·x.

## What failed

- Gyro filter 3ms: too much noise, 5x worse pitch std (0.20° → 1.0°)
- Gyro filter 15ms: still too much noise (0.75° pitch std)
- COMP_TC 150ms: violent instability from accel vibration coupling
- K5=0.37 from sysid: not enough pitch rate damping, diverged
- K5=5 with gyro 35ms: pitch-rate resonance at 6.25 Hz
- Sysid K3 predictions: all inflated by back-EMF artifact in A matrix

## Next steps (if pursuing further)

1. Re-do sysid with explicit back-EMF term (u_eff = u - k_e·wvel) to fix A[prate,wvel]
2. Investigate 10 Hz sensitivity peak that appeared with 20ms gyro filter
3. Consider accel LPF to enable shorter COMP_TC for faster gyro drift rejection
4. Augmented plant model with explicit filter states for principled all-gains-at-once design
