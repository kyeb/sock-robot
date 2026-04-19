#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""Fit a first-order motor model from a motor_id capture.

Model (per step, with constant commanded effort u):
    τ·v̇ + v = K·u
    v(t)    = K·u + (v₀ − K·u)·exp(−t/τ)

Per step we recover K (rad/s per %effort) and τ (time constant). Reports
the aggregate mean±std across steps plus per-amplitude breakdown, so
linearity and symmetry are easy to eyeball.

Usage:
    scripts/analyze_motor.py                   # latest capture in data/
    scripts/analyze_motor.py data/file.jsonl
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit


def load(path: Path):
    """Load jsonl; return (t, eff, v1, v2, pid_on) as numpy arrays.

    Prefers `al`/`ar` (applied-effort telemetry) over `pid` (inner-loop
    effort) so motor_id captures work. `pid` is 0 in manual-effort mode.
    """
    t, eff, v1, v2, pid_on = [], [], [], [], []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t.append(d["t"] / 1000.0)
            if "al" in d and "ar" in d:
                eff.append((d["al"] + d["ar"]) / 2.0)
            else:
                eff.append(d.get("pid", 0.0))
            v1.append(d["v1"])
            v2.append(d["v2"])
            pid_on.append(1 if d.get("pid_on") else 0)
    return (np.array(t), np.array(eff),
            np.array(v1), np.array(v2), np.array(pid_on))


def find_steps(t, eff, min_step=5.0, min_dur=0.4):
    """Return [(i_start, i_end, amplitude), ...] for sustained non-zero effort."""
    q = np.round(eff / 5.0) * 5.0
    steps = []
    i = 0
    while i < len(q):
        if abs(q[i]) < min_step:
            i += 1
            continue
        j = i + 1
        while j < len(q) and abs(q[j] - q[i]) < 1.0:
            j += 1
        if t[j - 1] - t[i] >= min_dur:
            steps.append((i, j, float(q[i])))
        i = j
    return steps


def fit_first_order(t, y, u, v0):
    """Fit v(t) = K·u + (v0 − K·u)·exp(−t/τ). Returns (K, τ, R², v_ss) or None."""
    t = t - t[0]

    def model(t, K, tau):
        vss = K * u
        return vss + (v0 - vss) * np.exp(-t / max(tau, 1e-4))

    try:
        p0 = [max(abs(y[-1] / u), 0.1) * np.sign(u), 0.1]
        popt, _ = curve_fit(model, t, y, p0=p0, maxfev=2000)
        K, tau = popt
        pred = model(t, K, tau)
        ss_res = np.sum((y - pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return float(K), float(tau), float(r2), float(model(t[-1], K, tau))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?",
                    help="jsonl capture (default: most recent in data/)")
    ap.add_argument("--pre", type=float, default=0.1,
                    help="skip this many seconds at the start of each step")
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

    t, eff, v1, v2, _ = load(path)
    v = (v1 + v2) / 2.0
    dt = float(np.median(np.diff(t)))
    print(f"samples: {len(t)}  duration: {t[-1]-t[0]:.1f}s  rate≈{1/dt:.1f} Hz")
    print(f"effort range: {np.min(eff):+.0f}..{np.max(eff):+.0f}%")
    print(f"v range:      {np.min(v):+.2f}..{np.max(v):+.2f} rad/s")

    steps = find_steps(t, eff)
    print(f"steps found: {len(steps)}")
    if not steps:
        print("no steps found — is the capture from motor_id.py?")
        return

    fits = []
    pre_n = int(args.pre / dt)
    print()
    print(f"{'step':>4} {'t0':>6} {'dur':>5} {'u':>5} {'v_ss':>6} "
          f"{'K':>6} {'τ_ms':>6} {'R²':>5}")
    print("-" * 50)
    for idx, (i, j, u) in enumerate(steps):
        start = min(j - 1, i + pre_n)
        if j - start < 4:
            continue
        res = fit_first_order(t[start:j], v[start:j], u, float(v[start]))
        if res is None:
            print(f"{idx:>4} {t[i]-t[0]:>6.2f} {t[j-1]-t[i]:>5.2f} {u:>5.0f}  fit failed")
            continue
        K, tau, r2, vss = res
        print(f"{idx:>4} {t[i]-t[0]:>6.2f} {t[j-1]-t[i]:>5.2f} {u:>5.0f} "
              f"{vss:>6.2f} {K:>6.3f} {tau*1000:>6.0f} {r2:>5.2f}")
        fits.append((u, K, tau, r2))

    if not fits:
        return

    Ks = np.array([f[1] for f in fits])
    taus = np.array([f[2] for f in fits])
    r2s = np.array([f[3] for f in fits])
    good = r2s > 0.7
    print()
    print(f"Summary (R²>0.7: {good.sum()}/{len(fits)} steps):")
    print(f"  K = {np.mean(Ks[good]):+.3f} ± {np.std(Ks[good]):.3f} "
          f"rad/s per %effort  (all: {np.mean(Ks):+.3f})")
    print(f"  τ = {np.mean(taus[good])*1000:.0f} ± {np.std(taus[good])*1000:.0f} ms"
          f"             (all: {np.mean(taus)*1000:.0f})")

    us = np.array([f[0] for f in fits])
    print("\nK vs amplitude (non-flat → nonlinear or deadzone):")
    for k in np.argsort(np.abs(us)):
        print(f"  u={us[k]:+4.0f}  K={Ks[k]:+.3f}  τ={taus[k]*1000:3.0f}ms  "
              f"R²={r2s[k]:.2f}")


if __name__ == "__main__":
    main()
