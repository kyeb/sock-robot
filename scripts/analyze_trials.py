#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Analyze multiple trial JSONL files for cross-run patterns.

Usage:
    ./scripts/analyze_trials.py data/trials/trial_*.jsonl
"""

import json
import math
import sys
from pathlib import Path


def load_trial(path: Path) -> tuple[dict, list[dict]]:
    lines = path.read_text().strip().split("\n")
    meta = json.loads(lines[0])
    samples = [json.loads(l) for l in lines[1:] if l.strip()]
    return meta, samples


def oscillation_period(samples: list[dict], target: float) -> float | None:
    """Estimate dominant oscillation period by finding zero crossings."""
    errors = [s["pitch"] - target for s in samples]
    crossings = []
    for i in range(1, len(errors)):
        if (errors[i-1] < 0 and errors[i] >= 0) or (errors[i-1] >= 0 and errors[i] < 0):
            t = samples[i]["t"]
            crossings.append(t)
    if len(crossings) < 4:
        return None
    # Period = 2 * avg half-period
    half_periods = [crossings[i+1] - crossings[i] for i in range(len(crossings)-1)]
    return 2 * sum(half_periods) / len(half_periods) / 1000  # ms to s


def settle_time(samples: list[dict], target: float, threshold: float = 1.0) -> float | None:
    """Time until pitch stays within ±threshold of target for the rest of the run."""
    t0 = samples[0]["t"]
    for i in range(len(samples) - 1, -1, -1):
        if abs(samples[i]["pitch"] - target) > threshold:
            if i == len(samples) - 1:
                return None  # never settled
            return (samples[i+1]["t"] - t0) / 1000
    return 0.0


def steady_state_stats(samples: list[dict], target: float, skip_s: float = 5.0) -> dict | None:
    """Analyze only the steady-state portion (after skip_s seconds)."""
    t0 = samples[0]["t"]
    ss = [s for s in samples if (s["t"] - t0) / 1000 >= skip_s]
    if len(ss) < 20:
        return None
    errors = [s["pitch"] - target for s in ss]
    n = len(errors)
    mean = sum(errors) / n
    rms = math.sqrt(sum(e**2 for e in errors) / n)
    std = math.sqrt(sum((e - mean)**2 for e in errors) / n)
    p_vals = [s.get("p", 0) for s in ss]
    i_vals = [s.get("i", 0) for s in ss]
    d_vals = [s.get("d", 0) for s in ss]
    return {
        "ss_rms": rms,
        "ss_std": std,
        "ss_mean": mean,
        "ss_max": max(abs(e) for e in errors),
        "ss_p_rms": math.sqrt(sum(v**2 for v in p_vals) / n),
        "ss_i_mean": sum(i_vals) / n,
        "ss_i_range": max(i_vals) - min(i_vals),
        "ss_d_rms": math.sqrt(sum(v**2 for v in d_vals) / n),
    }


def main():
    files = [Path(f) for f in sys.argv[1:]]
    if not files:
        print(__doc__)
        sys.exit(1)

    print(f"Analyzing {len(files)} trials\n")

    all_ss = []
    all_periods = []
    all_settle = []

    for f in sorted(files):
        meta, samples = load_trial(f)
        target = meta.get("target", 0.0)
        kd = meta.get("kd", "?")
        rms = meta.get("rms", "?")

        period = oscillation_period(samples, target)
        settle = settle_time(samples, target, 1.0)
        ss = steady_state_stats(samples, target, skip_s=5.0)

        label = f.stem.split("_", 2)[-1]  # strip "trial_TIMESTAMP_"
        parts = label.split("_", 1)
        if len(parts) > 1:
            label = parts[1]

        line = f"  {f.name:55s}  rms={rms:>6s}"
        if period:
            line += f"  T={period:.2f}s"
            all_periods.append(period)
        if settle is not None:
            line += f"  settle={settle:.1f}s"
            all_settle.append(settle)
        if ss:
            line += f"  ss_rms={ss['ss_rms']:.2f}°  ss_max={ss['ss_max']:.1f}°"
            all_ss.append(ss)
        print(line)

    print()

    # Cross-run summary
    if all_periods:
        avg_p = sum(all_periods) / len(all_periods)
        std_p = math.sqrt(sum((p - avg_p)**2 for p in all_periods) / len(all_periods)) if len(all_periods) > 1 else 0
        print(f"Oscillation period: {avg_p:.2f}s ± {std_p:.2f}s  (n={len(all_periods)})")

    if all_settle:
        print(f"Settle time (±1°):  {sum(all_settle)/len(all_settle):.1f}s avg,  {max(all_settle):.1f}s worst  (n={len(all_settle)})")

    if all_ss:
        print(f"\nSteady-state (after 5s):")
        avg_rms = sum(s["ss_rms"] for s in all_ss) / len(all_ss)
        avg_std = sum(s["ss_std"] for s in all_ss) / len(all_ss)
        avg_max = sum(s["ss_max"] for s in all_ss) / len(all_ss)
        avg_p_rms = sum(s["ss_p_rms"] for s in all_ss) / len(all_ss)
        avg_i_mean = sum(s["ss_i_mean"] for s in all_ss) / len(all_ss)
        avg_i_range = sum(s["ss_i_range"] for s in all_ss) / len(all_ss)
        avg_d_rms = sum(s["ss_d_rms"] for s in all_ss) / len(all_ss)
        print(f"  RMS:      {avg_rms:.2f}° avg")
        print(f"  Std dev:  {avg_std:.2f}° avg")
        print(f"  Max err:  {avg_max:.1f}° avg")
        print(f"  P_rms:    {avg_p_rms:.1f}  (proportional effort)")
        print(f"  I_mean:   {avg_i_mean:+.2f}  (steady-state bias)")
        print(f"  I_range:  {avg_i_range:.1f}  (integral swing)")
        print(f"  D_rms:    {avg_d_rms:.1f}  (damping effort)")

        # Check for vibration: high D_rms relative to P_rms suggests noise amplification
        if avg_d_rms > avg_p_rms * 0.8:
            print(f"\n  ⚠ D_rms/P_rms = {avg_d_rms/avg_p_rms:.2f} — D term is fighting P (possible vibration source)")

        # Check I_range — large swings indicate slow oscillation
        if avg_i_range > 8:
            print(f"\n  ⚠ I_range = {avg_i_range:.1f} — large I swings driving slow oscillation")


if __name__ == "__main__":
    main()
