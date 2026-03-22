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


WS_URL = "ws://localhost:8080/ws"
DEFAULT_SECONDS = 8
DEFAULT_TARGET = 0.0
CHART_WIDTH = 50
CHART_RANGE = 6.0


def print_chart(samples: list[dict], target: float):
    if not samples:
        return

    t0 = samples[0]["t"]
    center = CHART_WIDTH // 2

    # Bucket into 0.2s bins with pitch and pid output
    bin_ms = 200
    bins: dict[int, list[dict]] = {}
    for s in samples:
        b = (s["t"] - t0) // bin_ms
        bins.setdefault(b, []).append(s)

    print(f"       {'pitch':^{CHART_WIDTH}}  out")
    for b in sorted(bins):
        t = b * bin_ms / 1000
        ss = bins[b]
        avg_p = sum(s["pitch"] for s in ss) / len(ss)
        avg_out = sum(s.get("pid", 0) for s in ss) / len(ss)
        offset = avg_p - target
        pos = center + int(offset / CHART_RANGE * center)
        pos = max(0, min(CHART_WIDTH - 1, pos))

        row = list(" " * CHART_WIDTH)
        row[center] = "·"
        marker = "█" if abs(offset) < 1.0 else "▓" if abs(offset) < 2.0 else "░"
        row[pos] = marker

        # Show PID output as a compact bar: direction + magnitude
        out_bar = ">" * min(5, int(abs(avg_out) / 12)) if avg_out > 0 else "<" * min(5, int(abs(avg_out) / 12))
        if abs(avg_out) > 55:
            out_bar += "!"

        print(f" {t:4.1f}s {''.join(row)} {avg_out:+5.0f} {out_bar}")


def analyze(samples: list[dict], target: float) -> dict:
    if len(samples) < 10:
        return {"error": "too few samples", "n": len(samples)}

    pitches = [s["pitch"] for s in samples]
    errors = [p - target for p in pitches]
    n = len(errors)

    rms_error = math.sqrt(sum(e ** 2 for e in errors) / n)
    max_abs_error = max(abs(e) for e in errors)

    # Time in zone
    in_1 = sum(1 for e in errors if abs(e) < 1.0) / n * 100
    in_2 = sum(1 for e in errors if abs(e) < 2.0) / n * 100
    in_3 = sum(1 for e in errors if abs(e) < 3.0) / n * 100

    # Motor effort
    pid_outputs = [s.get("pid", 0) for s in samples]
    rms_out = math.sqrt(sum(o ** 2 for o in pid_outputs) / n)
    saturated = sum(1 for o in pid_outputs if abs(o) > 55) / n * 100

    return {
        "rms": f"{rms_error:.1f}°",
        "max": f"{max_abs_error:.1f}°",
        "±1°": f"{in_1:.0f}%",
        "±2°": f"{in_2:.0f}%",
        "±3°": f"{in_3:.0f}%",
        "rms_out": f"{rms_out:.0f}%",
        "saturated": f"{saturated:.0f}%",
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


if __name__ == "__main__":
    main()
