#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""Analyze an LQR run from telemetry logs.

Extracts contiguous ctrl-on runs, computes statistics, then fits a
discrete-time state-space model (A, B) from the observed data via
least-squares. Compares the identified plant to the analytical model
and recomputes LQR gains from the identified plant.

Usage:
    scripts/analyze_lqr_run.py                    # latest log
    scripts/analyze_lqr_run.py data/file.jsonl
    scripts/analyze_lqr_run.py --q-pitch 200      # tune Q for recomputed gains
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import linalg


def load_ctrl_runs(path: Path):
    """Load jsonl, return list of contiguous ctrl-on runs."""
    samples = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            samples.append(d)

    ctrl_key = "ctrl_on" if "ctrl_on" in samples[0] else "pid_on"

    runs = []
    current = []
    for s in samples:
        if s.get(ctrl_key):
            current.append(s)
        else:
            if current:
                runs.append(current)
                current = []
    if current:
        runs.append(current)

    return runs


def analyze_run(run, run_idx):
    t = np.array([s["t"] for s in run], dtype=np.float64)
    t_s = (t - t[0]) / 1000.0
    dur = t_s[-1]

    pitch = np.array([s["pitch"] for s in run])
    effort = np.array([s.get("effort", s.get("pid", 0)) for s in run])
    up = np.array([s.get("up", 0) for s in run])
    ur = np.array([s.get("ur", 0) for s in run])
    ux = np.array([s.get("ux", 0) for s in run])
    uv = np.array([s.get("uv", 0) for s in run])
    uy = np.array([s.get("uy", 0) for s in run])
    wp = np.array([s.get("wp", 0) for s in run])
    v1 = np.array([s.get("v1", 0) for s in run])
    v2 = np.array([s.get("v2", 0) for s in run])
    vel = (v1 + v2) / 2
    al = np.array([s.get("al", 0) for s in run])
    ar = np.array([s.get("ar", 0) for s in run])

    print(f"\n{'='*60}")
    print(f"Run {run_idx}: {len(run)} samples, {dur:.2f}s")
    print(f"{'='*60}")

    # Basic stats
    print(f"\n--- Pitch ---")
    print(f"  mean={np.mean(pitch):+.2f}°  std={np.std(pitch):.2f}°  "
          f"range=[{np.min(pitch):+.1f}, {np.max(pitch):+.1f}]°")

    print(f"\n--- Effort ---")
    print(f"  mean={np.mean(effort):+.1f}%  std={np.std(effort):.1f}%  "
          f"range=[{np.min(effort):+.1f}, {np.max(effort):+.1f}]%")
    sat_pct = 100 * np.sum(np.abs(effort) >= 99) / len(effort)
    print(f"  saturated: {sat_pct:.1f}% of samples")

    print(f"\n--- Per-term contributions (effort %) ---")
    ui = np.array([s.get("ui", 0) for s in run])
    for name, arr in [("u_pitch", up), ("u_pitch_rate", ur),
                       ("u_pos", ux), ("u_vel", uv), ("u_pos_int", ui),
                       ("u_yaw", uy)]:
        print(f"  {name:14s}: mean={np.mean(arr):+6.2f}  std={np.std(arr):5.2f}  "
              f"range=[{np.min(arr):+.1f}, {np.max(arr):+.1f}]")

    print(f"\n--- Wheel position ---")
    print(f"  start={wp[0]:+.2f} rad  end={wp[-1]:+.2f} rad  "
          f"drift={wp[-1]-wp[0]:+.2f} rad ({(wp[-1]-wp[0])*40:.0f} mm)")
    print(f"  range=[{np.min(wp):+.2f}, {np.max(wp):+.2f}] rad  "
          f"span={np.max(wp)-np.min(wp):.2f} rad")

    print(f"\n--- Wheel velocity ---")
    print(f"  mean={np.mean(vel):+.2f} rad/s  std={np.std(vel):.2f}  "
          f"range=[{np.min(vel):+.1f}, {np.max(vel):+.1f}]")

    print(f"\n--- Applied L/R ---")
    print(f"  left:  mean={np.mean(al):+.1f}  range=[{np.min(al):+.1f}, {np.max(al):+.1f}]")
    print(f"  right: mean={np.mean(ar):+.1f}  range=[{np.min(ar):+.1f}, {np.max(ar):+.1f}]")
    diff = al - ar
    print(f"  L-R diff: mean={np.mean(diff):+.1f}  std={np.std(diff):.1f}")

    # Oscillation analysis
    print(f"\n--- Oscillation ---")
    pm = np.mean(pitch)
    crossings = 0
    for i in range(1, len(pitch)):
        if (pitch[i-1] - pm) * (pitch[i] - pm) < 0:
            crossings += 1
    if crossings > 0 and dur > 0:
        freq = crossings / 2 / dur
        print(f"  pitch zero-crossing freq: {freq:.2f} Hz ({crossings} crossings)")
    else:
        print(f"  no oscillation detected")

    # Time windowed analysis
    win_s = max(0.5, min(3.0, dur / 5))
    win_ms = win_s * 1000
    t0 = t[0]
    buckets = [[]]
    wstart = t0
    for s in run:
        if s["t"] - wstart > win_ms:
            buckets.append([])
            wstart = s["t"]
        buckets[-1].append(s)

    print(f"\n--- Per-{win_s:.0f}s window (stability over time) ---")
    print(f"  {'t(s)':>5}  {'pitch_std':>9}  {'effort_std':>10}  "
          f"{'wp_mean':>8}  {'sat%':>5}  {'pitch_pk':>8}")
    for w in buckets:
        if len(w) < 3:
            continue
        wt = (w[0]["t"] - t0) / 1000
        wp_w = [s.get("pitch", 0) for s in w]
        we_w = [s.get("effort", s.get("pid", 0)) for s in w]
        wpos = [s.get("wp", 0) for s in w]
        sat = 100 * sum(1 for e in we_w if abs(e) >= 99) / len(we_w)
        print(f"  {wt:>5.1f}  {np.std(wp_w):>9.2f}°  {np.std(we_w):>10.1f}%  "
              f"{np.mean(wpos):>+8.2f}  {sat:>5.1f}  "
              f"{max(wp_w)-min(wp_w):>8.2f}°")

    spectral_analysis(run)
    sensitivity_analysis(run)


def sensitivity_analysis(run):
    """Compute empirical closed-loop sensitivity from chirp/PRBS data.

    Sensitivity S(jω) = 1 / (1 + L(jω)) where L is the open-loop TF.
    The peak |S|_∞ (M_s) tells us robustness margin:
      M_s < 2.0 → safe, good margins
      M_s 2-3   → works but brittle
      M_s > 3   → near instability

    We estimate S empirically from the relationship between the chirp
    excitation signal (uc) and pitch response.
    """
    from scipy.signal import welch, csd, coherence

    t = np.array([s["t"] for s in run], dtype=np.float64) / 1000.0
    dt = np.median(np.diff(t))
    fs = 1.0 / dt
    N = len(run)

    chirp = np.array([s.get("uc", 0) for s in run])
    if np.std(chirp) < 0.5:
        return  # no excitation signal

    pitch = np.array([s["pitch"] for s in run])
    pitch_rate = np.array([s["gy"] for s in run]) * (180.0 / np.pi)
    effort = np.array([s.get("effort", s.get("pid", 0)) for s in run])

    nperseg = min(256, N // 2)

    print(f"\n--- Sensitivity / Margin Analysis ---")

    # G_plant: u_total → pitch_rate (the plant as seen by the controller)
    f, Gpe = csd(effort, pitch_rate, fs=fs, nperseg=nperseg)
    _, Pee = welch(effort, fs=fs, nperseg=nperseg)
    G_plant = Gpe / (Pee + 1e-12)

    # Coherence for reliability
    _, coh_pe = coherence(effort, pitch_rate, fs=fs, nperseg=nperseg)

    # Sensitivity from chirp: S(jω) ≈ pitch_response_to_chirp / open_loop_chirp_effect
    # More directly: the complementary sensitivity T = 1 - S can be estimated
    # from how much of the chirp shows up in pitch vs how much the controller rejects.
    # Simplest empirical approach: S ≈ Φ_pitch_chirp / Φ_chirp_chirp normalized by G
    # But cleaner: compute the closed-loop TF from chirp→pitch and chirp→effort
    _, Pcc = welch(chirp, fs=fs, nperseg=nperseg)
    _, Gcp = csd(chirp, pitch_rate, fs=fs, nperseg=nperseg)
    _, Gce = csd(chirp, effort, fs=fs, nperseg=nperseg)
    _, coh_cp = coherence(chirp, pitch_rate, fs=fs, nperseg=nperseg)

    # T(jω) = closed-loop from chirp → pitch_rate = Gcp / Pcc
    # S(jω) = 1 - T(jω) ... but this only works if chirp enters at the plant input
    # Since chirp IS added to effort: chirp → effort_total → plant → pitch_rate
    # The closed-loop TF from chirp to pitch_rate is G/(1+L) = T·G_plant
    # And from chirp to effort is 1/(1+L) = S
    # So S(jω) ≈ Gce / Pcc (transfer from chirp to total effort)

    S_emp = Gce / (Pcc + 1e-12)
    S_mag = np.abs(S_emp)

    # Report sensitivity at key frequencies
    print(f"  freq(Hz)  |S|    coh(u,pr)  coh(chirp,pr)  interpretation")
    for freq_target in [0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 6.25, 7.0, 8.0, 10.0]:
        idx = np.argmin(np.abs(f - freq_target))
        if f[idx] > fs/2:
            continue
        s_val = S_mag[idx]
        c_pe = coh_pe[idx] if idx < len(coh_pe) else 0
        c_cp = coh_cp[idx] if idx < len(coh_cp) else 0
        marker = ""
        if s_val > 3:
            marker = "  ← DANGER"
        elif s_val > 2:
            marker = "  ← brittle"
        elif s_val > 1.5:
            marker = "  ← tight"
        print(f"  {f[idx]:>6.1f}    {s_val:>5.2f}  {c_pe:>10.2f}  {c_cp:>13.2f}{marker}")

    # Peak sensitivity
    valid = (f > 0.3) & (f < fs/2)
    ms_peak = np.max(S_mag[valid])
    ms_freq = f[valid][np.argmax(S_mag[valid])]
    print(f"\n  Peak sensitivity M_s = {ms_peak:.2f} at {ms_freq:.1f} Hz")
    if ms_peak < 2.0:
        print(f"  → Good margins. Room to increase gains.")
    elif ms_peak < 3.0:
        print(f"  → Tight margins. Near stability limit at {ms_freq:.1f} Hz.")
    else:
        print(f"  → Poor margins. System is brittle at {ms_freq:.1f} Hz.")


def spectral_analysis(run):
    """Per-term spectral analysis: which control term dominates at each frequency."""
    from scipy.signal import welch

    t = np.array([s["t"] for s in run], dtype=np.float64) / 1000.0
    dt = np.median(np.diff(t))
    fs = 1.0 / dt
    N = len(run)

    if N < 64:
        print(f"\n--- Spectral Analysis ---")
        print(f"  (too few samples for spectral analysis)")
        return

    nperseg = min(128, N // 2)

    signals = {
        "pitch":  np.array([s["pitch"] for s in run]),
        "effort": np.array([s.get("effort", s.get("pid", 0)) for s in run]),
        "u_pitch": np.array([s.get("up", 0) for s in run]),
        "u_prate": np.array([s.get("ur", 0) for s in run]),
        "u_pos":   np.array([s.get("ux", 0) for s in run]),
        "u_vel":   np.array([s.get("uv", 0) for s in run]),
        "u_pint":  np.array([s.get("ui", 0) for s in run]),
    }

    # Detrend (remove mean) before FFT
    for k in signals:
        signals[k] = signals[k] - np.mean(signals[k])

    print(f"\n--- Spectral Analysis (nperseg={nperseg}, fs={fs:.0f} Hz) ---")

    # Compute PSD for each signal
    psds = {}
    for name, sig in signals.items():
        f, psd = welch(sig, fs=fs, nperseg=nperseg)
        psds[name] = (f, psd)

    # Find dominant frequency of pitch oscillation
    f_pitch, psd_pitch = psds["pitch"]
    mask = f_pitch > 0.3  # ignore DC
    peak_idx = np.argmax(psd_pitch[mask]) + np.argmax(mask)
    peak_freq = f_pitch[peak_idx]
    print(f"  Pitch peak frequency: {peak_freq:.2f} Hz")

    # Show which control terms have the most power at the pitch peak frequency
    print(f"\n  Power at pitch peak ({peak_freq:.1f} Hz) and nearby:")
    freq_band = (f_pitch > peak_freq * 0.7) & (f_pitch < peak_freq * 1.4)
    term_names = ["u_pitch", "u_prate", "u_pos", "u_vel", "u_pint"]
    band_powers = {}
    for name in term_names:
        f, psd = psds[name]
        bp = np.mean(psd[freq_band]) if np.any(freq_band) else 0
        band_powers[name] = bp

    total_bp = sum(band_powers.values())
    if total_bp > 0:
        for name in sorted(band_powers, key=lambda n: -band_powers[n]):
            bp = band_powers[name]
            pct = 100 * bp / total_bp
            bar = "#" * int(pct / 2)
            print(f"    {name:10s}: {pct:5.1f}%  {bar}")

    # Also show power distribution across full spectrum for each term
    print(f"\n  Total RMS by term (all frequencies):")
    for name in term_names:
        f, psd = psds[name]
        rms = np.sqrt(np.trapezoid(psd[1:], f[1:]))
        print(f"    {name:10s}: {rms:6.2f} effort%")

    # Cross-coherence: which term leads pitch oscillation?
    from scipy.signal import csd, coherence
    print(f"\n  Coherence with pitch at peak ({peak_freq:.1f} Hz):")
    for name in term_names:
        sig = signals[name]
        f_coh, coh = coherence(signals["pitch"], sig, fs=fs, nperseg=nperseg)
        # Find coherence nearest to peak freq
        idx = np.argmin(np.abs(f_coh - peak_freq))
        f_csd, Pxy = csd(signals["pitch"], sig, fs=fs, nperseg=nperseg)
        phase = np.angle(Pxy[idx], deg=True)
        print(f"    {name:10s}: coh={coh[idx]:.2f}  phase={phase:+.0f}°"
              f"{'  ← LEADS pitch' if -180 < phase < -10 else ''}"
              f"{'  ← LAGS pitch' if 10 < phase < 180 else ''}")


def identify_plant(run):
    """Fit discrete-time A, B from telemetry via least-squares.

    State x = [pitch(deg), pitch_rate(deg/s), wheel_vel(rad/s), wheel_pos(rad)]
    Input u = effort(%)

    Fits: x[n+1] = A_id · x[n] + B_id · u[n]

    All in firmware units — no SI conversion needed. The identified model
    directly captures motor dynamics, filter lags, friction, etc.
    """
    pitch = np.array([s["pitch"] for s in run])
    # pitch_rate: use the telemetry gyro-derived value
    # We need to reconstruct pitch_rate from the data. The firmware uses
    # filtered gyro. We can approximate from telemetry fields.
    # The 'gy' field is raw gyro Y in rad/s; firmware converts to deg/s
    # and filters. But we have 'ur' = k_pitch_rate * pitch_rate, so if
    # we knew k_pitch_rate we could back it out. Easier: approximate
    # pitch_rate from finite differences of pitch, smoothed.
    v1 = np.array([s["v1"] for s in run])
    v2 = np.array([s["v2"] for s in run])
    vel = (v1 + v2) / 2
    wp = np.array([s["wp"] for s in run])
    effort = np.array([s.get("effort", s.get("pid", 0)) for s in run])
    t = np.array([s["t"] for s in run], dtype=np.float64) / 1000.0

    # Estimate pitch_rate from gyro data (degrees/s)
    # gy is gyro Y-axis in rad/s; firmware does gyro[1].to_degrees()
    pitch_rate = np.array([s["gy"] for s in run]) * (180.0 / np.pi)

    N = len(run)
    dt_samples = np.diff(t)
    median_dt = np.median(dt_samples)
    min_dt = np.min(dt_samples) if len(dt_samples) > 0 else median_dt
    max_dt = np.max(dt_samples) if len(dt_samples) > 0 else median_dt
    is_fast = median_dt < 0.015  # ~200 Hz if median dt < 15ms
    print(f"\n--- System Identification ---")
    print(f"  samples: {N}, median dt: {median_dt*1000:.1f} ms "
          f"(range: {min_dt*1000:.1f}–{max_dt*1000:.1f} ms) "
          f"{'[200 Hz]' if is_fast else '[50 Hz]'}")

    # Filter out samples with irregular dt (>2x median) to avoid
    # fitting across rate transitions or dropouts
    good_mask = dt_samples < 2.5 * median_dt
    n_dropped = np.sum(~good_mask)
    if n_dropped > 0:
        print(f"  dropping {n_dropped} irregular-dt transitions")

    # Build state matrix: x = [pitch, pitch_rate, wheel_vel, wheel_pos]
    X = np.column_stack([pitch, pitch_rate, vel, wp])  # (N, 4)
    U = effort.reshape(-1, 1)  # (N, 1)

    # x[n+1] = A · x[n] + B · u[n]
    # Stack [x[n], u[n]] and solve for [A, B] via least-squares
    X_now = X[:-1][good_mask]
    U_now = U[:-1][good_mask]
    X_next = X[1:][good_mask]

    Z = np.hstack([X_now, U_now])

    # Solve X_next = Z @ [A; B]^T  →  [A; B]^T = lstsq(Z, X_next)
    AB, residuals, rank, sv = np.linalg.lstsq(Z, X_next, rcond=None)

    A_id = AB[:4].T   # (4, 4)
    B_id = AB[4:].T   # (4, 1)

    # Recompute one-step prediction on full data for RMSE
    Z_full = np.hstack([X[:-1], U[:-1]])
    X_pred = Z_full @ AB
    errors = X[1:] - X_pred
    rmse_per_state = np.sqrt(np.mean(errors**2, axis=0))

    print(f"\n  Identified A (discrete, dt≈{median_dt*1000:.0f}ms):")
    state_names = ["pitch", "prate", "wvel ", "wpos "]
    print(f"         {'pitch':>8} {'prate':>8} {'wvel':>8} {'wpos':>8}")
    for i, name in enumerate(state_names):
        print(f"  {name}  [{', '.join(f'{v:+8.4f}' for v in A_id[i])}]")

    print(f"\n  Identified B (discrete):")
    print(f"  [{', '.join(f'{v:+.6f}' for v in B_id.flatten())}]")

    print(f"\n  One-step prediction RMSE:")
    for i, name in enumerate(["pitch(°)", "prate(°/s)", "wvel(rad/s)", "wpos(rad)"]):
        print(f"    {name:14s}: {rmse_per_state[i]:.4f}")

    # Multi-step (rollout) prediction quality
    X_sim = np.zeros_like(X)
    X_sim[0] = X[0]
    for i in range(N - 1):
        X_sim[i+1] = A_id @ X_sim[i] + B_id.flatten() * effort[i]
    rollout_rmse = np.sqrt(np.mean((X - X_sim)**2, axis=0))
    # How many steps before rollout diverges (error > 2x state std)?
    state_std = np.std(X, axis=0)
    diverge_step = N
    for i in range(N):
        if np.any(np.abs(X[i] - X_sim[i]) > 3 * state_std):
            diverge_step = i
            break
    diverge_time = diverge_step * median_dt

    print(f"\n  Rollout (full simulation) RMSE:")
    for i, name in enumerate(["pitch(°)", "prate(°/s)", "wvel(rad/s)", "wpos(rad)"]):
        print(f"    {name:14s}: {rollout_rmse[i]:.4f}  (state std={state_std[i]:.4f})")
    print(f"  Rollout tracks for {diverge_time:.2f}s ({diverge_step} steps) "
          f"before 3σ divergence")

    # Eigenvalue analysis of identified plant
    eigs_id = np.linalg.eigvals(A_id)
    print(f"\n  Identified open-loop eigenvalues:")
    for e in sorted(eigs_id, key=lambda x: -abs(x)):
        if np.isreal(e):
            print(f"    {e.real:+.4f}  (|λ|={abs(e):.4f})")
        else:
            print(f"    {e.real:+.4f} ± {abs(e.imag):.4f}j  (|λ|={abs(e):.4f})")
    unstable = [e for e in eigs_id if abs(e) > 1.0]
    if unstable:
        print(f"  ⚠ {len(unstable)} unstable pole(s) — expected for inverted pendulum")

    return A_id, B_id, median_dt


def analytical_model_comparison(A_id, B_id, dt):
    """Compare identified model to the analytical one."""
    from compute_lqr import build_model, discretize

    print(f"\n--- Analytical Model Comparison ---")

    import io, contextlib
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        A_c, B_c = build_model(0.794, 0.058, 0.040, 0.050, omega_n=5.07)
        A_an, B_an = discretize(A_c, B_c, dt)

    # The analytical model is in SI (rad, N·m).
    # The identified model is in firmware units (deg, deg/s, rad/s, rad, effort%).
    # To compare, convert the analytical model to firmware units.
    # x_fw = S · x_si, u_fw = u_si / tau_pp
    # x_si = S^-1 · x_fw
    # x_fw[n+1] = S · A_si · S^-1 · x_fw[n] + S · B_si / tau_pp · u_fw[n]

    # For now, just compare eigenvalues (unit-independent).
    eigs_an = np.linalg.eigvals(A_an)
    eigs_id = np.linalg.eigvals(A_id)

    print(f"  {'Eigenvalue':>20}  {'Analytical':>12}  {'Identified':>12}  {'Δ|λ|':>8}")
    eigs_an_sorted = sorted(eigs_an, key=lambda x: -abs(x))
    eigs_id_sorted = sorted(eigs_id, key=lambda x: -abs(x))
    for ea, ei in zip(eigs_an_sorted, eigs_id_sorted):
        print(f"  {'':>20}  {ea.real:+12.6f}  {ei.real:+12.6f}  {abs(ei)-abs(ea):+8.4f}")

    # The analytical unstable pole tells us about the gravitational dynamics.
    # Compare: is the identified instability faster/slower than predicted?
    unstable_an = max(abs(e) for e in eigs_an)
    unstable_id = max(abs(e) for e in eigs_id)
    print(f"\n  Unstable pole magnitude: analytical={unstable_an:.4f}, identified={unstable_id:.4f}")
    if unstable_id > unstable_an:
        print(f"  → Identified plant is MORE unstable than analytical model")
    else:
        print(f"  → Identified plant is LESS unstable than analytical model")


def recompute_lqr(A_id, B_id, q_pitch, q_pitch_rate, q_vel, q_pos, r_weight):
    """Compute LQR gains directly from the identified plant (firmware units)."""
    print(f"\n--- LQR from Identified Plant ---")
    print(f"  (gains are directly in firmware units — no torque scaling needed)")

    Q = np.diag([q_pitch, q_pitch_rate, q_vel, q_pos])
    R = np.array([[r_weight]])

    print(f"  Q = diag([{q_pitch}, {q_pitch_rate}, {q_vel}, {q_pos}])")
    print(f"  R = {r_weight}")

    try:
        P = linalg.solve_discrete_are(A_id, B_id, Q, R)
        K = np.linalg.solve(R + B_id.T @ P @ B_id, B_id.T @ P @ A_id)
        K_fw = K[0]
    except np.linalg.LinAlgError as e:
        print(f"  Riccati solve failed: {e}")
        print(f"  (identified plant may not be stabilizable with these weights)")
        return

    cl_eigs = np.linalg.eigvals(A_id - B_id @ K)

    print(f"\n  Identified-plant LQR gains (firmware units):")
    print(f"    k_pitch      (K1) = {K_fw[0]:+.4f}  effort%/deg")
    print(f"    k_pitch_rate (K2) = {K_fw[1]:+.4f}  effort%/(deg/s)")
    print(f"    k_vel        (K4) = {K_fw[2]:+.4f}  effort%/(rad/s)")
    print(f"    k_pos        (K3) = {K_fw[3]:+.4f}  effort%/rad")

    # Negate because firmware does effort = +K·x, LQR gives u = -K·x
    print(f"\n  For firmware (negate for effort = +k·x convention):")
    print(f"    K1 = {-K_fw[0]:.4f}")
    print(f"    K2 = {-K_fw[1]:.4f}")
    print(f"    K3 = {-K_fw[3]:.4f}")
    print(f"    K4 = {-K_fw[2]:.4f}")

    print(f"\n  Closed-loop eigenvalues:")
    all_stable = True
    for e in sorted(cl_eigs, key=lambda x: -abs(x)):
        stable = abs(e) < 1.0
        all_stable &= stable
        marker = "✓" if stable else "✗"
        print(f"    |λ|={abs(e):.4f}  ({e.real:+.4f})  {marker}")
    print(f"  All stable: {all_stable}")


def identify_combined(runs, run_indices):
    """Fit A, B from multiple runs combined.

    Each run contributes (x[n], u[n]) → x[n+1] pairs independently.
    Transitions across run boundaries are NOT included.
    """
    print(f"\n{'='*60}")
    print(f"Combined identification from runs {run_indices}")
    print(f"{'='*60}")

    all_X_now = []
    all_U_now = []
    all_X_next = []
    total_samples = 0
    all_median_dts = []

    for idx in run_indices:
        run = runs[idx]
        pitch = np.array([s["pitch"] for s in run])
        pitch_rate = np.array([s["gy"] for s in run]) * (180.0 / np.pi)
        v1 = np.array([s["v1"] for s in run])
        v2 = np.array([s["v2"] for s in run])
        vel = (v1 + v2) / 2
        wp = np.array([s["wp"] for s in run])
        effort = np.array([s.get("effort", s.get("pid", 0)) for s in run])
        t = np.array([s["t"] for s in run], dtype=np.float64) / 1000.0

        X = np.column_stack([pitch, pitch_rate, vel, wp])
        U = effort.reshape(-1, 1)

        dt_samples = np.diff(t)
        median_dt = np.median(dt_samples)
        all_median_dts.append(median_dt)

        # Filter irregular transitions
        good_mask = dt_samples < 2.5 * median_dt
        all_X_now.append(X[:-1][good_mask])
        all_U_now.append(U[:-1][good_mask])
        all_X_next.append(X[1:][good_mask])
        total_samples += len(run)
        dur = (run[-1]["t"] - run[0]["t"]) / 1000
        print(f"  Run {idx}: {len(run)} samples, {dur:.1f}s, dt≈{median_dt*1000:.0f}ms")

    X_now = np.vstack(all_X_now)
    U_now = np.vstack(all_U_now)
    X_next = np.vstack(all_X_next)
    N_pairs = X_now.shape[0]

    overall_median_dt = np.median(all_median_dts)
    # Check if runs have mixed rates — warn user
    if len(all_median_dts) > 1:
        dt_spread = max(all_median_dts) / min(all_median_dts)
        if dt_spread > 1.5:
            print(f"  ⚠ WARNING: mixed sample rates across runs "
                  f"({min(all_median_dts)*1000:.0f}ms – {max(all_median_dts)*1000:.0f}ms)")
            print(f"    Combine only runs with the same rate for best results!")

    print(f"  Total: {total_samples} samples, {N_pairs} transition pairs")

    Z = np.hstack([X_now, U_now])
    AB, residuals, rank, sv = np.linalg.lstsq(Z, X_next, rcond=None)

    A_id = AB[:4].T
    B_id = AB[4:].T

    X_pred = Z @ AB
    errors = X_next - X_pred
    rmse_per_state = np.sqrt(np.mean(errors**2, axis=0))

    print(f"\n  Identified A (discrete, dt≈{overall_median_dt*1000:.0f}ms):")
    state_names = ["pitch", "prate", "wvel ", "wpos "]
    print(f"         {'pitch':>8} {'prate':>8} {'wvel':>8} {'wpos':>8}")
    for i, name in enumerate(state_names):
        print(f"  {name}  [{', '.join(f'{v:+8.4f}' for v in A_id[i])}]")

    print(f"\n  Identified B (discrete):")
    print(f"  [{', '.join(f'{v:+.6f}' for v in B_id.flatten())}]")

    print(f"\n  One-step prediction RMSE:")
    for i, name in enumerate(["pitch(°)", "prate(°/s)", "wvel(rad/s)", "wpos(rad)"]):
        print(f"    {name:14s}: {rmse_per_state[i]:.4f}")

    # Eigenvalues
    eigs_id = np.linalg.eigvals(A_id)
    print(f"\n  Open-loop eigenvalues:")
    for e in sorted(eigs_id, key=lambda x: -abs(x)):
        if abs(e.imag) < 1e-6:
            print(f"    {e.real:+.4f}  (|λ|={abs(e):.4f})")
        else:
            print(f"    {e.real:+.4f} ± {abs(e.imag):.4f}j  (|λ|={abs(e):.4f})")
    unstable = [e for e in eigs_id if abs(e) > 1.0]
    if unstable:
        print(f"  ⚠ {len(unstable)} unstable pole(s)")

    # Per-run rollout validation
    print(f"\n  Per-run rollout validation:")
    for idx in run_indices:
        run = runs[idx]
        pitch = np.array([s["pitch"] for s in run])
        pitch_rate = np.array([s["gy"] for s in run]) * (180.0 / np.pi)
        v1 = np.array([s["v1"] for s in run])
        v2 = np.array([s["v2"] for s in run])
        vel = (v1 + v2) / 2
        wp = np.array([s["wp"] for s in run])
        effort = np.array([s.get("effort", s.get("pid", 0)) for s in run])
        X = np.column_stack([pitch, pitch_rate, vel, wp])
        N = len(run)

        X_sim = np.zeros_like(X)
        X_sim[0] = X[0]
        for i in range(N - 1):
            X_sim[i+1] = A_id @ X_sim[i] + B_id.flatten() * effort[i]
        state_std = np.std(X, axis=0)
        diverge_step = N
        for i in range(N):
            if np.any(np.abs(X[i] - X_sim[i]) > 3 * state_std):
                diverge_step = i
                break
        run_dt = np.median(np.diff(np.array([s["t"] for s in run], dtype=np.float64) / 1000.0))
        diverge_time = diverge_step * run_dt
        dur = (run[-1]["t"] - run[0]["t"]) / 1000
        print(f"    Run {idx}: tracks {diverge_time:.2f}s / {dur:.1f}s")

    return A_id, B_id, overall_median_dt


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?")
    ap.add_argument("--runs", type=str, default=None,
                    help="comma-separated run indices to combine for sysid (e.g. '0,2,4')")
    ap.add_argument("--q-pitch", type=float, default=1.0,
                    help="Q weight on pitch (deg²)")
    ap.add_argument("--q-pitch-rate", type=float, default=0.01,
                    help="Q weight on pitch rate (deg/s)²")
    ap.add_argument("--q-vel", type=float, default=0.1,
                    help="Q weight on wheel velocity (rad/s)²")
    ap.add_argument("--q-pos", type=float, default=0.5,
                    help="Q weight on wheel position (rad²)")
    ap.add_argument("--r", type=float, default=0.01,
                    help="R weight on effort (%%²)")
    ap.add_argument("--trim-start", type=float, default=0.0,
                    help="seconds to trim from start of each run")
    args = ap.parse_args()

    if args.file:
        path = Path(args.file)
    else:
        data_dir = Path(__file__).parent.parent / "data"
        cands = sorted(data_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        cands = [c for c in cands if c.stat().st_size > 0]
        if not cands:
            raise SystemExit("no logs in data/")
        path = cands[-1]

    print(f"file: {path.name}  ({path.stat().st_size/1e6:.2f} MB)")
    runs = load_ctrl_runs(path)
    if args.trim_start > 0:
        for i in range(len(runs)):
            t0 = runs[i][0]["t"]
            cutoff = t0 + args.trim_start * 1000
            runs[i] = [s for s in runs[i] if s["t"] >= cutoff]
        runs = [r for r in runs if len(r) >= 10]
        print(f"(trimmed {args.trim_start:.1f}s from start of each run)")
    print(f"ctrl-on runs found: {len(runs)}")
    for i, r in enumerate(runs):
        dur = (r[-1]["t"] - r[0]["t"]) / 1000
        print(f"  Run {i}: {len(r)} samples, {dur:.1f}s")

    if not runs:
        print("no controller-on data found")
        return

    if args.runs:
        run_indices = [int(x.strip()) for x in args.runs.split(",")]
        for idx in run_indices:
            analyze_run(runs[idx], idx)
        A_id, B_id, combined_dt = identify_combined(runs, run_indices)
        try:
            analytical_model_comparison(A_id, B_id, combined_dt)
        except Exception as e:
            print(f"\n  (analytical comparison skipped: {e})")
        recompute_lqr(A_id, B_id, args.q_pitch, args.q_pitch_rate,
                       args.q_vel, args.q_pos, args.r)
    else:
        for i, run in enumerate(runs):
            analyze_run(run, i)
            if len(run) < 20:
                print(f"\n  (run too short for sysid, need ≥20 samples)")
                continue
            A_id, B_id, dt = identify_plant(run)
            try:
                analytical_model_comparison(A_id, B_id, dt)
            except Exception as e:
                print(f"\n  (analytical comparison skipped: {e})")
            recompute_lqr(A_id, B_id, args.q_pitch, args.q_pitch_rate,
                           args.q_vel, args.q_pos, args.r)


if __name__ == "__main__":
    main()
