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
       scripts/cmd.py gains               # show current gains from telemetry
       scripts/cmd.py pidrun              # analyze most recent PID-on run in log
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


def cmd_pidrun(last_seconds: float | None = None):
    """Analyze the most recent contiguous PID-on run across all logs.

    If last_seconds is given, only the trailing window of the run is used —
    useful for isolating the effect of a recent gain change.
    """
    import statistics

    # Walk logs from newest to oldest, collect the latest contiguous on-run
    logs = sorted(glob.glob("data/*.jsonl"), key=os.path.getmtime, reverse=True)
    run = []
    for path in logs:
        samples = []
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("pid_on") == 1:
                    samples.append(d)
        if samples:
            # split into runs (gap > 500ms)
            runs = []
            cur = []
            for s in samples:
                if cur and s["t"] - cur[-1]["t"] > 500:
                    runs.append(cur)
                    cur = []
                cur.append(s)
            if cur:
                runs.append(cur)
            run = runs[-1]
            print(f"log: {path}")
            break
    if not run:
        print("no PID-on runs found")
        return
    if last_seconds is not None:
        cutoff = run[-1]["t"] - last_seconds * 1000
        run = [s for s in run if s["t"] >= cutoff]
        if not run:
            print(f"no samples in last {last_seconds}s")
            return
    dur = (run[-1]["t"] - run[0]["t"]) / 1000
    print(f"run: t={run[0]['t']}..{run[-1]['t']} ({dur:.2f}s, {len(run)} samples)")
    pitches = [s["pitch"] for s in run]
    efforts = [s["pid"] for s in run]
    tps = [s["tp"] for s in run]
    ps = [s["p"] for s in run]
    ds = [s["d"] for s in run]
    lhzs = [s["lhz"] for s in run]
    print(
        f"pitch: [{min(pitches):.2f}, {max(pitches):.2f}] std={statistics.stdev(pitches) if len(pitches)>1 else 0:.2f}"
    )
    print(f"effort: [{min(efforts):.1f}, {max(efforts):.1f}]")
    print(f"tp:     [{min(tps):.2f}, {max(tps):.2f}]")
    print(f"inner_p:[{min(ps):.1f}, {max(ps):.1f}]")
    print(f"inner_d:[{min(ds):.1f}, {max(ds):.1f}]")
    print(f"loop_hz:[{min(lhzs):.1f}, {max(lhzs):.1f}]")
    # Back out KP from telemetry: inner_p = kp * (pitch - pbias - tp); pbias=1.35 default
    kps = []
    for s in run:
        err = (s["pitch"] - 1.35) - s["tp"]
        if abs(err) > 2 and abs(s["p"]) > 20:
            kps.append(s["p"] / err)
    if kps:
        print(f"implied KP (from telemetry): {statistics.median(kps):.2f}")
    # Dominant frequency from zero crossings around mean
    pm = sum(pitches) / len(pitches)
    xs = 0
    for i in range(1, len(pitches)):
        if (pitches[i - 1] - pm) * (pitches[i] - pm) < 0:
            xs += 1
    if xs and dur > 0:
        print(f"pitch zero-cross freq: {xs/2/dur:.2f} Hz")

    # Separate fast (ring) vs slow (drift) components via 1s moving-average.
    # Fast = pitch - slow (high-frequency content). Slow = 1s moving mean.
    # Approximates a 1Hz low-pass boundary.
    wsize = max(1, int(len(run) / max(dur, 1e-3)))  # ~1s window in samples
    slow = []
    total = 0.0
    q = []
    for s in run:
        q.append(s["pitch"])
        total += s["pitch"]
        if len(q) > wsize:
            total -= q.pop(0)
        slow.append(total / len(q))
    fast = [pitches[i] - slow[i] for i in range(len(pitches))]
    slow_range = max(slow) - min(slow)
    fast_std = statistics.stdev(fast) if len(fast) > 1 else 0
    # Slow zero crossings around slow-mean
    sm = sum(slow) / len(slow)
    sxs = 0
    for i in range(1, len(slow)):
        if (slow[i - 1] - sm) * (slow[i] - sm) < 0:
            sxs += 1
    print(
        f"fast (>1Hz): std={fast_std:.2f}°   slow (<1Hz): range={slow_range:.2f}°, "
        f"freq={sxs/2/dur if sxs and dur>0 else 0:.3f} Hz"
    )
    wps = [s["wp"] for s in run]
    print(f"wheel_pos drift: [{min(wps):.2f}, {max(wps):.2f}]  span={max(wps)-min(wps):.2f} rad")

    # Per-window amplitude envelope (is the oscillation growing?)
    win_s = 5.0
    win_ms = win_s * 1000
    t0 = run[0]["t"]
    buckets: list[list[dict]] = [[]]
    wstart = t0
    for s in run:
        if s["t"] - wstart > win_ms:
            buckets.append([])
            wstart = s["t"]
        buckets[-1].append(s)
    print(f"\nper-{win_s:.0f}s envelope (is amplitude growing?):")
    print(f"  {'t(s)':>6}  {'wp_pkpk':>8}  {'pitch_pkpk':>10}  {'fast_std':>8}  {'wp_mean':>8}")
    for w in buckets:
        if len(w) < 2:
            continue
        t = (w[0]["t"] - t0) / 1000
        wps_w = [s["wp"] for s in w]
        pit_w = [s["pitch"] for s in w]
        pm_w = sum(pit_w) / len(pit_w)
        # fast component: deviation from 1s moving mean
        wsize_inner = max(1, int(len(w) / max((w[-1]["t"] - w[0]["t"]) / 1000, 1e-3)))
        slow_w = []
        tot = 0.0
        q: list[float] = []
        for p in pit_w:
            q.append(p)
            tot += p
            if len(q) > wsize_inner:
                tot -= q.pop(0)
            slow_w.append(tot / len(q))
        fast_w = [pit_w[i] - slow_w[i] for i in range(len(pit_w))]
        fast_std_w = statistics.stdev(fast_w) if len(fast_w) > 1 else 0
        print(
            f"  {t:>6.1f}  {max(wps_w)-min(wps_w):>8.2f}  "
            f"{max(pit_w)-min(pit_w):>10.2f}  {fast_std_w:>8.3f}  {sum(wps_w)/len(wps_w):>8.2f}"
        )


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
    elif cmd == "gains":
        cmd_gains()
    elif cmd == "pidrun":
        last = float(sys.argv[2]) if len(sys.argv) > 2 else None
        cmd_pidrun(last)
    else:
        msg = " ".join(sys.argv[1:])
        asyncio.run(cmd_send(msg))


main()
