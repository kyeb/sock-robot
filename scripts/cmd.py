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
       scripts/cmd.py diagnose [seconds]  # full diagnostic report
       scripts/cmd.py gains               # show current gains from telemetry
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


def find_zero_crossings(values, timestamps_ms):
    """Find zero-crossing intervals to estimate oscillation period."""
    crossings = []
    for i in range(1, len(values)):
        if values[i - 1] * values[i] < 0:
            crossings.append(timestamps_ms[i])
    if len(crossings) < 3:
        return None, None
    # period = 2x the average half-period between crossings
    intervals = [crossings[i + 1] - crossings[i] for i in range(len(crossings) - 1)]
    half_period_ms = sum(intervals) / len(intervals)
    period_s = half_period_ms * 2 / 1000
    freq_hz = 1 / period_s if period_s > 0 else 0
    return period_s, freq_hz


def cmd_diagnose(seconds):
    log = latest_log()
    if not log:
        print("No log files found in data/")
        return

    samples = []
    with open(log) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if d.get("pid_on"):
                    samples.append(d)
            except json.JSONDecodeError:
                continue

    if samples:
        t_end = samples[-1]["t"]
        t_start = t_end - seconds * 1000
        samples = [s for s in samples if s["t"] >= t_start]

    if len(samples) < 10:
        print(f"Not enough PID-on samples (got {len(samples)}, need 10+)")
        return

    dt_s = (samples[-1]["t"] - samples[0]["t"]) / 1000
    print(f"=== DIAGNOSTIC REPORT ({len(samples)} samples, {dt_s:.1f}s) ===\n")

    # --- Basic stats ---
    def stat(arr):
        m = sum(arr) / len(arr)
        std = math.sqrt(sum((x - m) ** 2 for x in arr) / len(arr))
        return m, std, min(arr), max(arr)

    pitches = [d["pitch"] for d in samples]
    vels = [(d["v1"] + d["v2"]) / 2 for d in samples]
    efforts = [d["pid"] for d in samples]
    tps = [d["tp"] for d in samples]
    ois = [d["i"] for d in samples]
    ops = [d["op"] for d in samples]
    ts = [d["t"] for d in samples]

    pm, ps, plo, phi = stat(pitches)
    vm, vs, vlo, vhi = stat(vels)
    em, es, elo, ehi = stat(efforts)
    tpm, tps_std, tplo, tphi = stat(tps)
    oim, ois_std, oilo, oihi = stat(ois)

    print("  SIGNALS:")
    print(f"    pitch:        mean={pm:+.2f}  std={ps:.3f}  range=[{plo:+.1f}, {phi:+.1f}]")
    print(f"    target_pitch: mean={tpm:+.2f}  std={tps_std:.3f}  range=[{tplo:+.2f}, {tphi:+.2f}]")
    print(f"    velocity:     mean={vm:+.2f}  std={vs:.2f}  range=[{vlo:+.1f}, {vhi:+.1f}]")
    print(f"    effort:       mean={em:+.2f}  std={es:.2f}  range=[{elo:+.1f}, {ehi:+.1f}]")
    print(f"    outer_i:      mean={oim:+.2f}  std={ois_std:.3f}  range=[{oilo:+.2f}, {oihi:+.2f}]")

    # --- Sway analysis (low-freq oscillation in target_pitch) ---
    print("\n  SWAY ANALYSIS (low-freq oscillation):")
    # de-mean target_pitch and look for zero crossings
    tp_centered = [tp - tpm for tp in tps]
    period, freq = find_zero_crossings(tp_centered, ts)
    if period:
        print(f"    target_pitch oscillation: period={period:.2f}s ({freq:.2f}Hz)")
        print(f"    target_pitch pk-pk: {tphi - tplo:.3f} deg")
    else:
        print(f"    no clear oscillation detected in target_pitch")

    # sway in position (wheel_pos in radians from telemetry)
    e1s = [d["e1"] for d in samples]
    e2s = [d["e2"] for d in samples]
    wps = [d.get("wp", 0) for d in samples]
    if wps and any(wp != 0 for wp in wps):
        wpm, wps_std, wplo, wphi = stat(wps)
        # 80mm diameter Pololu wheel, radius = 40mm
        wheel_r = 0.04
        pos_range_m = (wphi - wplo) * wheel_r
        pos_range_in = pos_range_m * 39.37
        print(f"    wheel_pos range: [{wplo:+.2f}, {wphi:+.2f}] rad  (~{pos_range_in:.1f} inches pk-pk)")
        # zero-crossing analysis on de-meaned wheel_pos
        wp_centered = [wp - wpm for wp in wps]
        wp_period, wp_freq = find_zero_crossings(wp_centered, ts)
        if wp_period:
            print(f"    position oscillation: period={wp_period:.2f}s ({wp_freq:.2f}Hz)")
    else:
        avg_enc = [(e1 + e2) / 2 for e1, e2 in zip(e1s, e2s)]
        enc_drift = avg_enc[-1] - avg_enc[0]
        enc_drift_per_s = enc_drift / dt_s if dt_s > 0 else 0
        print(f"    encoder drift: {enc_drift:+.0f} counts ({enc_drift_per_s:+.1f}/s)")

    # --- Vibration analysis (high-freq pitch variation) ---
    print("\n  VIBRATION ANALYSIS (high-freq noise):")
    # compute pitch rate of change from consecutive samples
    pitch_deltas = []
    for i in range(1, len(pitches)):
        dt_ms = ts[i] - ts[i - 1]
        if dt_ms > 0:
            pitch_deltas.append(abs(pitches[i] - pitches[i - 1]) / (dt_ms / 1000))
    if pitch_deltas:
        pdm, pds, pdlo, pdhi = stat(pitch_deltas)
        print(f"    pitch rate of change: mean={pdm:.1f} deg/s  max={pdhi:.1f} deg/s")

    effort_deltas = []
    for i in range(1, len(efforts)):
        effort_deltas.append(abs(efforts[i] - efforts[i - 1]))
    if effort_deltas:
        edm, eds, edlo, edhi = stat(effort_deltas)
        print(f"    effort jitter: mean={edm:.1f}  max={edhi:.1f}  (step-to-step delta)")

    # --- Yaw analysis ---
    print("\n  YAW ANALYSIS:")
    yaw_drift = e1s[-1] - e1s[0] - (e2s[-1] - e2s[0])
    yaw_drift_per_s = yaw_drift / dt_s if dt_s > 0 else 0
    print(f"    encoder divergence (e1-e2 drift): {yaw_drift:+.0f} counts ({yaw_drift_per_s:+.1f}/s)")
    yaw_rates = [d["yr"] for d in samples]
    yrm, yrs, yrlo, yrhi = stat(yaw_rates)
    print(f"    gyro yaw rate: mean={yrm:+.2f} deg/s  std={yrs:.2f}")

    # --- Integrator health ---
    print("\n  INTEGRATOR HEALTH:")
    oi_at_limit = sum(1 for oi in ois if abs(oi) > 1.8) / len(ois) * 100
    print(f"    outer_i near limit (>1.8): {oi_at_limit:.1f}% of samples")
    print(f"    outer_i range: [{oilo:+.3f}, {oihi:+.3f}]")


def cmd_gains():
    log = latest_log()
    if not log:
        print("No log files found in data/")
        return

    # read last few lines to get current state
    last = None
    with open(log) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    last = json.loads(line)
                except json.JSONDecodeError:
                    continue
    if not last:
        print("No valid samples found")
        return

    pid = "ON" if last.get("pid_on") else "OFF"
    print(f"  PID: {pid}")
    print(f"  pitch={last['pitch']:+.1f}  tp={last['tp']:+.2f}")
    print(f"  v1={last['v1']:+.1f}  v2={last['v2']:+.1f}")
    print(f"  effort={last['pid']:+.1f}  p={last['p']:+.1f}  i={last['i']:+.2f}  d={last['d']:+.1f}")


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
    elif cmd == "diagnose":
        seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 10
        cmd_diagnose(seconds)
    elif cmd == "gains":
        cmd_gains()
    else:
        msg = " ".join(sys.argv[1:])
        asyncio.run(cmd_send(msg))


main()
