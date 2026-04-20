# LQR Tuning Log

## 2026-04-19: Best so far (tagged `best`)

**Gains:** K1=9.5, K2=0.8, K3=0.3, K4=8.7, K5=0.5, KYAW=0.5, THEQ=1.22

**Filters:** GYRO_TC=35ms, VEL_TC=45ms, COMP_TC=495ms

**Best run (data/20260419_155711.jsonl, run 1):**
- Duration: 43s (38s clean before power cord perturbation)
- Pitch std: 0.24-0.26° (flat across all windows)
- Effort std: 3.7-4.5%
- Position drift: ~0mm over 38s clean portion (integrator working)
- Position span: ±0.2 rad
- Saturation: 0%
- Oscillation freq: 2.76 Hz

**Notes:**
- K5=0.5 integrator eliminated position drift completely (was 138mm/14s without)
- Conditional anti-windup (freeze integration when saturated)
- Gains K1/K2/K4 validated by PRBS + chirp sysid (identified-plant inverse LQR reproduces them)
- K3=0.3 is much lower than model predicts (~7-13) due to A[prate,wvel] back-EMF artifact inflating model's position gain prediction
- Recovery from perturbation takes ~5s (slowest closed-loop mode ~13s decay)
