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
    for name, arr in [("u_pitch", up), ("u_pitch_rate", ur),
                       ("u_pos", ux), ("u_vel", uv), ("u_yaw", uy)]:
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
    print(f"\n--- System Identification ---")
    print(f"  samples: {N}, median dt: {median_dt*1000:.1f} ms")

    # Build state matrix: x = [pitch, pitch_rate, wheel_vel, wheel_pos]
    X = np.column_stack([pitch, pitch_rate, vel, wp])  # (N, 4)
    U = effort.reshape(-1, 1)  # (N, 1)

    # x[n+1] = A · x[n] + B · u[n]
    # Stack [x[n], u[n]] and solve for [A, B] via least-squares
    X_now = X[:-1]   # (N-1, 4)
    U_now = U[:-1]   # (N-1, 1)
    X_next = X[1:]   # (N-1, 4)

    Z = np.hstack([X_now, U_now])  # (N-1, 5)

    # Solve X_next = Z @ [A; B]^T  →  [A; B]^T = lstsq(Z, X_next)
    AB, residuals, rank, sv = np.linalg.lstsq(Z, X_next, rcond=None)

    A_id = AB[:4].T   # (4, 4)
    B_id = AB[4:].T   # (4, 1)

    # Model quality: one-step prediction error
    X_pred = Z @ AB
    errors = X_next - X_pred
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
        U = effort.reshape(-1, 1)

        all_X_now.append(X[:-1])
        all_U_now.append(U[:-1])
        all_X_next.append(X[1:])
        total_samples += len(run)
        dur = (run[-1]["t"] - run[0]["t"]) / 1000
        print(f"  Run {idx}: {len(run)} samples, {dur:.1f}s")

    X_now = np.vstack(all_X_now)
    U_now = np.vstack(all_U_now)
    X_next = np.vstack(all_X_next)
    N_pairs = X_now.shape[0]

    print(f"  Total: {total_samples} samples, {N_pairs} transition pairs")

    Z = np.hstack([X_now, U_now])
    AB, residuals, rank, sv = np.linalg.lstsq(Z, X_next, rcond=None)

    A_id = AB[:4].T
    B_id = AB[4:].T

    X_pred = Z @ AB
    errors = X_next - X_pred
    rmse_per_state = np.sqrt(np.mean(errors**2, axis=0))

    print(f"\n  Identified A (discrete, dt≈20ms):")
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
        diverge_time = diverge_step * 0.02
        dur = (run[-1]["t"] - run[0]["t"]) / 1000
        print(f"    Run {idx}: tracks {diverge_time:.2f}s / {dur:.1f}s")

    return A_id, B_id


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
        A_id, B_id = identify_combined(runs, run_indices)
        try:
            analytical_model_comparison(A_id, B_id, 0.02)
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
