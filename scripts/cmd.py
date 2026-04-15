#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets"]
# ///
"""Send commands to the robot or view telemetry stats.

Usage: scripts/cmd.py PID_ON
       scripts/cmd.py VKP 0.5
       scripts/cmd.py STOP
       scripts/cmd.py stats [seconds]     # default 10s
       scripts/cmd.py watch [seconds]     # live 1Hz samples
"""
import asyncio
import glob
import json
import math
import os
import sys
import time
import websockets

WS_URL = "ws://localhost:8080"


def latest_log():
    logs = sorted(glob.glob("data/*.jsonl"), key=os.path.getmtime)
    return logs[-1] if logs else None


def compute_stats(samples):
    def s(arr):
        if not arr:
            return 0, 0, 0, 0
        m = sum(arr) / len(arr)
        std = math.sqrt(sum((x - m) ** 2 for x in arr) / len(arr))
        return m, std, min(arr), max(arr)

    pitches = [d["pitch"] for d in samples]
    vels = [(d["v1"] + d["v2"]) / 2 for d in samples]
    effs = [d["pid"] for d in samples]
    e1s = [d["e1"] for d in samples]
    e2s = [d["e2"] for d in samples]

    pm, ps, plo, phi = s(pitches)
    vm, vs, vlo, vhi = s(vels)
    em, es, elo, ehi = s(effs)

    e1_drift = e1s[-1] - e1s[0] if len(e1s) > 1 else 0
    e2_drift = e2s[-1] - e2s[0] if len(e2s) > 1 else 0
    yaw_drift = e1_drift - e2_drift

    dt = (samples[-1]["t"] - samples[0]["t"]) / 1000 if len(samples) > 1 else 0

    print(f"  {len(samples)} samples over {dt:.1f}s")
    print(f"  pitch:  mean={pm:+.2f}  std={ps:.2f}  range=[{plo:+.1f}, {phi:+.1f}]")
    print(f"  vel:    mean={vm:+.2f}  std={vs:.2f}  range=[{vlo:+.1f}, {vhi:+.1f}]")
    print(f"  effort: mean={em:+.2f}  std={es:.2f}  range=[{elo:+.1f}, {ehi:+.1f}]")
    print(f"  enc drift: e1={e1_drift:+d}  e2={e2_drift:+d}  diff={yaw_drift:+d}")


def cmd_stats(seconds):
    log = latest_log()
    if not log:
        print("No log files found in data/")
        return

    cutoff = time.time() - seconds
    samples = []
    with open(log) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if not d.get("pid_on"):
                    continue
                # use file mod approach: read all, keep last N seconds
                samples.append(d)
            except json.JSONDecodeError:
                continue

    # keep only samples from the last `seconds` based on timestamps
    if samples:
        t_end = samples[-1]["t"]
        t_start = t_end - seconds * 1000
        samples = [s for s in samples if s["t"] >= t_start]

    if not samples:
        print(f"No PID-on samples in last {seconds}s")
        return

    print(f"=== Stats (last {seconds}s) ===")
    compute_stats(samples)


def cmd_watch(seconds):
    log = latest_log()
    if not log:
        print("No log files found in data/")
        return

    print(f"Watching for {seconds}s...")
    end_time = time.time() + seconds
    with open(log) as f:
        f.seek(0, 2)  # seek to end
        last_print = 0
        while time.time() < end_time:
            line = f.readline()
            if not line:
                time.sleep(0.05)
                continue
            try:
                d = json.loads(line.strip())
                now = time.time()
                if now - last_print >= 1.0:
                    last_print = now
                    pid = "ON" if d.get("pid_on") else "OFF"
                    print(
                        f"pitch={d['pitch']:+6.1f} vel={d['v1']:+5.1f}/{d['v2']:+5.1f} "
                        f"eff={d['pid']:+6.1f} p={d['p']:+6.1f} i={d['i']:+6.2f} "
                        f"d={d['d']:+5.1f} [{pid}]"
                    )
            except (json.JSONDecodeError, KeyError):
                continue


async def cmd_send(msg):
    async with websockets.connect(WS_URL) as ws:
        await ws.send(msg)
        print(f"sent: {msg}")


def main():
    if len(sys.argv) < 2:
        print("Usage: scripts/cmd.py <command|stats|watch> [args]")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "stats":
        seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 10
        cmd_stats(seconds)
    elif cmd == "watch":
        seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 30
        cmd_watch(seconds)
    else:
        msg = " ".join(sys.argv[1:])
        asyncio.run(cmd_send(msg))


main()
