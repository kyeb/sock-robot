#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""Fit pendulum natural frequency ω_n and equilibrium angle θ_eq from
free-fall tip releases (controller off).

Model (linear, valid for small angles): θ̈ = ω_n²·(θ − θ_eq)
Rewritten as regression:                 θ̈ = a + b·θ   (ω_n=√b, θ_eq=−a/b)

To obtain a precise θ_eq, drop the robot many times from ±1–2° both ways.
Per-event regressions are noisy with short windows, so we also do a joint
fit stacking all usable samples and bootstrap the uncertainty.

Usage:
    scripts/fit_eq.py                    # latest file in data/
    scripts/fit_eq.py data/file.jsonl
    scripts/fit_eq.py --verbose          # show per-event breakdown
    scripts/fit_eq.py --theta-max 12     # widen linearization cap
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import savgol_filter


def load(path: Path):
    """Return dict with t (s), pitch (deg), ctrl_on (bool)."""
    t, pitch, ctrl_on = [], [], []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t.append(d["t"])
            pitch.append(d.get("pitch", 0.0))
            ctrl_on.append(1 if d.get("ctrl_on") else 0)
    return {
        "t": np.array(t, dtype=np.float64) / 1000.0,
        "pitch": np.array(pitch, dtype=np.float64),
        "ctrl_on": np.array(ctrl_on, dtype=np.int8),
    }


def find_drops(d, theta_max=10.0, min_rate=5.0):
    """Yield (i_start, i_end) for monotonic tip windows with controller off.

    A drop starts when |dθ/dt| exceeds `min_rate` while the controller is
    off and |θ| < theta_max; it ends when |θ| exceeds theta_max or
    pitch_rate reverses sign.
    """
    t, pitch, ctrl_on = d["t"], d["pitch"], d["ctrl_on"].astype(bool)
    if len(t) < 20:
        return []
    try:
        pitch_s = savgol_filter(pitch, 9, 2)
    except Exception:
        pitch_s = pitch
    pitch_rate = np.gradient(pitch_s, t)

    drops = []
    in_drop = False
    start = None
    sign = 0
    for i in range(len(t)):
        if ctrl_on[i]:
            if in_drop:
                drops.append((start, i))
                in_drop = False
            continue
        if not in_drop:
            if abs(pitch_rate[i]) > min_rate and abs(pitch[i]) < theta_max:
                in_drop = True
                start = i
                sign = int(np.sign(pitch_rate[i]))
        else:
            if abs(pitch[i]) > theta_max or pitch_rate[i] * sign < -1.0:
                drops.append((start, i))
                in_drop = False
    if in_drop:
        drops.append((start, len(t) - 1))
    return [(s, e) for s, e in drops if e - s >= 5]


def fit_event(t, pitch):
    """Per-event fit: θ̈ = a + b·θ. Returns (ω_n, θ_eq, n) or None."""
    if len(t) < 4:
        return None
    dt = float(np.median(np.diff(t)))
    wl = min(9, len(t) | 1)
    if wl < 3:
        return None
    try:
        acc = savgol_filter(pitch, window_length=wl,
                            polyorder=min(2, wl - 1), deriv=2, delta=dt)
    except Exception:
        acc = np.gradient(np.gradient(pitch, t), t)
    trim = 2
    if len(pitch) > 2 * trim:
        th_c, acc_c = pitch[trim:-trim], acc[trim:-trim]
    else:
        th_c, acc_c = pitch, acc
    if len(th_c) < 3:
        return None
    A = np.column_stack([np.ones_like(th_c), th_c])
    coef, *_ = np.linalg.lstsq(A, acc_c, rcond=None)
    a, b = coef
    if b <= 0:
        return None
    return np.sqrt(b), -a / b, th_c, acc_c


def joint_fit(d, drops, skip_initial_s=0.04,
              min_excursion=3.0, omega_range=(3.0, 8.0), theta_eq_max=5.0):
    """Stacked regression across all acceptable drops.

    Per-event outputs are collected for reporting, but only "good" events
    (physical omega, reasonable excursion and θ_eq) contribute to the
    stacked fit.
    """
    t, pitch = d["t"], d["pitch"]
    all_th, all_acc = [], []
    per_event = []

    for idx, (s, e) in enumerate(drops):
        dt = float(np.median(np.diff(t[s:e]))) if e - s > 2 else 0.02
        s2 = s + (int(skip_initial_s / dt) if dt > 0 else 0)
        if e - s2 < 4:
            continue
        fit = fit_event(t[s2:e], pitch[s2:e])
        if fit is None:
            continue
        omega, theta_eq_ev, th_c, acc_c = fit
        th_start = float(pitch[s])
        th_end = float(pitch[e - 1])
        excursion = th_end - th_start

        if abs(excursion) < min_excursion:
            reason = "small excursion"
        elif not (omega_range[0] <= omega <= omega_range[1]):
            reason = f"ω={omega:.1f} outside [{omega_range[0]},{omega_range[1]}]"
        elif abs(theta_eq_ev) > theta_eq_max:
            reason = f"θ_eq={theta_eq_ev:+.1f} implausible"
        else:
            reason = ""

        good = reason == ""
        per_event.append({
            "idx": idx, "t0": float(t[s]), "n": len(th_c),
            "omega_n": float(omega), "theta_eq": float(theta_eq_ev),
            "theta_start": th_start, "theta_end": th_end,
            "direction": "+" if excursion > 0 else "-",
            "good": good, "reason": reason,
        })
        if good:
            all_th.append(th_c)
            all_acc.append(acc_c)

    if not all_th:
        return {"per_event": per_event}

    Theta = np.concatenate(all_th)
    Accel = np.concatenate(all_acc)
    A = np.column_stack([np.ones_like(Theta), Theta])
    coef, *_ = np.linalg.lstsq(A, Accel, rcond=None)
    a, b = coef
    if b <= 0:
        return {"per_event": per_event}
    pred = A @ coef
    ss_res = np.sum((Accel - pred) ** 2)
    ss_tot = np.sum((Accel - np.mean(Accel)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Bootstrap uncertainty
    rng = np.random.default_rng(0)
    boots = []
    n = len(Theta)
    for _ in range(200):
        pick = rng.integers(0, n, n)
        cb, *_ = np.linalg.lstsq(A[pick], Accel[pick], rcond=None)
        if cb[1] > 0:
            boots.append((np.sqrt(cb[1]), -cb[0] / cb[1]))
    if boots:
        omega_std = float(np.std([b[0] for b in boots]))
        theta_std = float(np.std([b[1] for b in boots]))
    else:
        omega_std = theta_std = 0.0

    return {
        "omega_n": float(np.sqrt(b)),
        "theta_eq": float(-a / b),
        "omega_n_std": omega_std,
        "theta_eq_std": theta_std,
        "r2": float(r2),
        "n_events_good": sum(1 for e in per_event if e["good"]),
        "n_events_total": len(per_event),
        "n_samples": n,
        "per_event": per_event,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?")
    ap.add_argument("--theta-max", type=float, default=10.0,
                    help="linearization cap in degrees")
    ap.add_argument("--min-rate", type=float, default=5.0,
                    help="min |dθ/dt| to flag drop start (deg/s)")
    ap.add_argument("--skip-initial", type=float, default=0.04,
                    help="discard first N seconds of each drop (hand residual)")
    ap.add_argument("--verbose", action="store_true",
                    help="show per-event breakdown")
    args = ap.parse_args()

    if args.file:
        path = Path(args.file)
    else:
        data_dir = Path(__file__).parent.parent / "data"
        cands = sorted(data_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        cands = [c for c in cands if c.stat().st_size > 0]
        if not cands:
            raise SystemExit("no captures in data/")
        path = cands[-1]
    print(f"file: {path.name}  ({path.stat().st_size/1e6:.2f} MB)")

    d = load(path)
    print(f"samples: {len(d['t'])}  duration: {d['t'][-1]-d['t'][0]:.1f}s")

    drops = find_drops(d, theta_max=args.theta_max, min_rate=args.min_rate)
    print(f"drops detected: {len(drops)}")

    res = joint_fit(d, drops, skip_initial_s=args.skip_initial)

    if args.verbose and res.get("per_event"):
        print(f"\nper-event fits:")
        print(f"{'#':>3} {'t':>7} {'dir':>3} {'θ_start':>8} {'θ_end':>7} "
              f"{'ω_n':>6} {'θ_eq':>7} {'n':>4}  ok/reason")
        for e in res["per_event"]:
            mark = "✓" if e["good"] else "✗"
            print(f"{e['idx']:>3} {e['t0']:>7.1f} {e['direction']:>3} "
                  f"{e['theta_start']:>+8.2f} {e['theta_end']:>+7.2f} "
                  f"{e['omega_n']:>6.2f} {e['theta_eq']:>+7.2f} {e['n']:>4}  "
                  f"{mark} {e['reason']}")

    if "omega_n" not in res:
        print("\nno joint fit possible (not enough usable drops)")
        return

    print(f"\n=== joint fit across {res['n_events_good']}/"
          f"{res['n_events_total']} drops, {res['n_samples']} samples ===")
    print(f"  ω_n  = {res['omega_n']:.3f} ± {res['omega_n_std']:.3f} rad/s  "
          f"({res['omega_n']/(2*np.pi):.3f} Hz)")
    print(f"  θ_eq = {res['theta_eq']:+.3f} ± {res['theta_eq_std']:.3f}°")
    print(f"  R²   = {res['r2']:.3f}")


if __name__ == "__main__":
    main()
