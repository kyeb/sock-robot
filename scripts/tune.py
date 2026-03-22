#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets"]
# ///
"""PID tuning trial runner — sends gains, captures data, scores stability.

Usage:
    ./scripts/tune.py <kp> <ki> <kd> [target] [--seconds N]
"""

import asyncio
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path


WS_URL = "ws://localhost:8080/ws"
DEFAULT_SECONDS = 8
DEFAULT_TARGET = 0.0
CHART_WIDTH = 60
CHART_RANGE = 3.0


def print_chart(samples: list[dict], target: float):
    if not samples:
        return

    t0 = samples[0]["t"]
    center = CHART_WIDTH // 2

    # Bucket into 0.1s bins for finer resolution
    bin_ms = 100
    bins: dict[int, list[dict]] = {}
    for s in samples:
        b = (s["t"] - t0) // bin_ms
        bins.setdefault(b, []).append(s)

    # Header with scale markers
    scale = " " * 7
    for i in range(CHART_WIDTH):
        deg = (i - center) / center * CHART_RANGE
        if abs(deg - round(deg)) < 0.01 and deg == int(deg):
            scale += str(int(deg)).rjust(1) if deg >= 0 else str(int(deg))
        else:
            scale += " "
    print(scale)
    print(f"       {'|':>{center+1}}")

    for b in sorted(bins):
        t = b * bin_ms / 1000
        ss = bins[b]
        avg_p = sum(s["pitch"] for s in ss) / len(ss)
        min_p = min(s["pitch"] for s in ss) - target
        max_p = max(s["pitch"] for s in ss) - target
        avg_out = sum(s.get("pid", 0) for s in ss) / len(ss)
        avg_P = sum(s.get("p", 0) for s in ss) / len(ss)
        avg_I = sum(s.get("i", 0) for s in ss) / len(ss)
        avg_D = sum(s.get("d", 0) for s in ss) / len(ss)
        offset = avg_p - target

        row = list(" " * CHART_WIDTH)
        row[center] = "|"

        # Show min-max range as a bar
        lo = center + int(min_p / CHART_RANGE * center)
        hi = center + int(max_p / CHART_RANGE * center)
        lo = max(0, min(CHART_WIDTH - 1, lo))
        hi = max(0, min(CHART_WIDTH - 1, hi))
        for i in range(lo, hi + 1):
            row[i] = "-"

        # Mark average position
        pos = center + int(offset / CHART_RANGE * center)
        pos = max(0, min(CHART_WIDTH - 1, pos))
        marker = "█" if abs(offset) < 0.5 else "▓" if abs(offset) < 1.0 else "░"
        row[pos] = marker

        pid_detail = f"P{avg_P:+5.1f} I{avg_I:+5.2f} D{avg_D:+5.1f}"
        print(f" {t:4.1f}s {''.join(row)} {avg_out:+5.1f} {pid_detail}")


def analyze(samples: list[dict], target: float) -> dict:
    if len(samples) < 10:
        return {"error": "too few samples", "n": len(samples)}

    pitches = [s["pitch"] for s in samples]
    errors = [p - target for p in pitches]
    n = len(errors)

    mean_error = sum(errors) / n
    rms_error = math.sqrt(sum(e ** 2 for e in errors) / n)
    max_abs_error = max(abs(e) for e in errors)
    std_dev = math.sqrt(sum((e - mean_error) ** 2 for e in errors) / n)

    # Tighter zone stats for fine tuning
    in_025 = sum(1 for e in errors if abs(e) < 0.25) / n * 100
    in_05 = sum(1 for e in errors if abs(e) < 0.5) / n * 100
    in_1 = sum(1 for e in errors if abs(e) < 1.0) / n * 100
    in_2 = sum(1 for e in errors if abs(e) < 2.0) / n * 100

    # Motor effort
    pid_outputs = [s.get("pid", 0) for s in samples]
    rms_out = math.sqrt(sum(o ** 2 for o in pid_outputs) / n)
    saturated = sum(1 for o in pid_outputs if abs(o) > 55) / n * 100

    # P/I/D term breakdown (RMS)
    p_terms = [s.get("p", 0) for s in samples]
    i_terms = [s.get("i", 0) for s in samples]
    d_terms = [s.get("d", 0) for s in samples]
    rms_p = math.sqrt(sum(v ** 2 for v in p_terms) / n)
    rms_i = math.sqrt(sum(v ** 2 for v in i_terms) / n)
    rms_d = math.sqrt(sum(v ** 2 for v in d_terms) / n)
    mean_i = sum(i_terms) / n

    return {
        "mean": f"{mean_error:+.2f}°",
        "rms": f"{rms_error:.2f}°",
        "std": f"{std_dev:.2f}°",
        "max": f"{max_abs_error:.1f}°",
        "±0.25°": f"{in_025:.0f}%",
        "±0.5°": f"{in_05:.0f}%",
        "±1°": f"{in_1:.0f}%",
        "±2°": f"{in_2:.0f}%",
        "rms_out": f"{rms_out:.0f}%",
        "sat": f"{saturated:.0f}%",
        "P_rms": f"{rms_p:.1f}",
        "I_mean": f"{mean_i:+.2f}",
        "D_rms": f"{rms_d:.1f}",
    }


async def run_trial(kp: float, ki: float, kd: float, target: float, seconds: float):
    from websockets.asyncio.client import connect

    async with connect(WS_URL) as ws:
        for cmd in [f"KP {kp}", f"KI {ki}", f"KD {kd}", f"TARGET {target}", "PID_ON"]:
            await ws.send(cmd)
            await asyncio.sleep(0.05)

        print(f"▶ Kp={kp}  Ki={ki}  Kd={kd}  target={target}  ({seconds}s)")

        # Settle 0.5s before recording
        pre_deadline = time.monotonic() + 0.5
        while time.monotonic() < pre_deadline:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

        samples = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if not msg.startswith("{"):
                continue
            d = json.loads(msg)
            if "pitch" in d:
                samples.append(d)

        await ws.send("PID_OFF")
        return samples


def main():
    args = sys.argv[1:]
    if len(args) < 3:
        print(__doc__)
        sys.exit(1)

    kp = float(args[0])
    ki = float(args[1])
    kd = float(args[2])
    target = float(args[3]) if len(args) > 3 else DEFAULT_TARGET
    seconds = DEFAULT_SECONDS

    i = 0
    while i < len(args):
        if args[i] == "--seconds":
            seconds = float(args[i + 1])
            i += 2
        else:
            i += 1

    samples = asyncio.run(run_trial(kp, ki, kd, target, seconds))
    print_chart(samples, target)
    stats = analyze(samples, target)
    parts = [f"{k}={v}" for k, v in stats.items()]
    print(f"  → {' | '.join(parts)}")

    # Always save trial data
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(__file__).parent.parent / "data" / "trials"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"trial_{ts}_kp{kp}_ki{ki}_kd{kd}.jsonl"
    meta = {"trial": True, "kp": kp, "ki": ki, "kd": kd, "target": target,
            "seconds": seconds, "n_samples": len(samples), **stats}
    with open(out_path, "w") as f:
        f.write(json.dumps(meta) + "\n")
        for s in samples:
            f.write(json.dumps(s) + "\n")
    print(f"  → saved {out_path.name}")


if __name__ == "__main__":
    main()
