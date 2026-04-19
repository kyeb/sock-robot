#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets"]
# ///
"""Motor identification: drive the robot through a programmed EFFORT step
sequence and capture the wheel-velocity response. Analyze with analyze_motor.py.

Prerequisites:
  - Robot wheels OFF the ground (so there is no load/coupling from the pendulum)
  - Controller must be OFF (script asserts this by sending DISABLE first)
  - Bridge running at ws://localhost:8080

Usage:
    scripts/motor_id.py                        # default: +/- 20, 40, 60 %
    scripts/motor_id.py --amp 30 50 70         # custom amplitudes
    scripts/motor_id.py --step-dur 1.5         # longer step

EFFORT commands are re-sent at 20 Hz so the firmware's 500 ms manual-effort
watchdog never trips mid-step.
"""
import argparse
import asyncio
import json
import time

import websockets

WS_URL = "ws://localhost:8080"
SEND_HZ = 20


def build_sequence(amps, step_dur, rest_dur):
    """Bipolar multi-step sequence returning [(duration_s, effort_pct), ...]."""
    steps = [(1.0, 0)]  # warmup
    for a in amps:
        steps += [(step_dur, a), (rest_dur, 0)]
    for a in amps:
        steps += [(step_dur, -a), (rest_dur, 0)]
    steps += [(0.8, 0)]  # cooldown
    return steps


async def run_sequence(steps):
    """Stream EFFORT commands through the bridge for the programmed sequence."""
    period = 1.0 / SEND_HZ
    capture_file = None
    async with websockets.connect(WS_URL) as ws:
        # Drain any initial greeting message from the bridge
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.3)
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            pass

        await ws.send("DISABLE")
        await asyncio.sleep(0.2)

        await ws.send("CAPTURE_START")
        for _ in range(5):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.3)
                m = json.loads(raw)
                if m.get("capture") == "started":
                    capture_file = m.get("file")
                    print(f"  capture: {capture_file}")
                    break
            except (asyncio.TimeoutError, json.JSONDecodeError):
                continue

        await asyncio.sleep(0.3)

        print("  running sequence...")
        t_start = time.monotonic()
        for i, (dur, eff) in enumerate(steps):
            step_end = time.monotonic() + dur
            print(f"    [{i+1:>2}/{len(steps)}] "
                  f"t={time.monotonic()-t_start:5.1f}s  "
                  f"effort={eff:+4.0f}%  for {dur:.2f}s")
            while time.monotonic() < step_end:
                await ws.send(f"EFFORT {eff}")
                await asyncio.sleep(period)

        # Ensure motors stop
        await ws.send("EFFORT 0")
        await asyncio.sleep(0.3)
        await ws.send("CAPTURE_STOP")
        await asyncio.sleep(0.2)

    return capture_file


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--amp", type=float, nargs="+", default=[20, 40, 60],
                    help="effort amplitudes in %% (each run + then -)")
    ap.add_argument("--step-dur", type=float, default=1.0,
                    help="step duration in seconds")
    ap.add_argument("--rest-dur", type=float, default=0.6,
                    help="rest (effort=0) duration between steps in seconds")
    args = ap.parse_args()

    steps = build_sequence(args.amp, args.step_dur, args.rest_dur)
    total = sum(dur for dur, _ in steps)
    print(f"motor ID: {len(steps)} steps, total {total:.1f}s  "
          f"(amps={args.amp}%, step={args.step_dur}s, rest={args.rest_dur}s)\n")

    capture_file = asyncio.run(run_sequence(steps))
    print()
    if capture_file:
        print(f"  capture saved: data/{capture_file}")
        print(f"  analyze with:  scripts/analyze_motor.py data/{capture_file}")
    else:
        print("  (capture file not reported — check bridge logs)")


if __name__ == "__main__":
    main()
