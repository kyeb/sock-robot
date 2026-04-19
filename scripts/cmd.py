#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets"]
# ///
"""Send commands to the robot or view telemetry stats.

Usage: scripts/cmd.py ENABLE
       scripts/cmd.py K1 1.0
       scripts/cmd.py STOP
       scripts/cmd.py stats [seconds]     # default 10s
       scripts/cmd.py watch [seconds]     # live 1Hz samples
       scripts/cmd.py gains               # show current state from telemetry
       scripts/cmd.py ctrlrun             # analyze most recent controller-on run
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
    effs = [d["effort"] for d in samples]
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

    samples = []
    with open(log) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if not d.get("ctrl_on"):
                    continue
                samples.append(d)
            except json.JSONDecodeError:
                continue

    if samples:
        t_end = samples[-1]["t"]
        t_start = t_end - seconds * 1000
        samples = [s for s in samples if s["t"] >= t_start]

    if not samples:
        print(f"No controller-on samples in last {seconds}s")
        return

    print(f"=== Stats (last {seconds}s) ===")
    compute_stats(samples)


def cmd_gains():
    log = latest_log()
    if not log:
        print("No log files found in data/")
        return

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

    ctrl = "ON" if last.get("ctrl_on") else "OFF"
    print(f"  CTRL: {ctrl}")
    print(f"  pitch={last['pitch']:+.1f}  wp={last.get('wp', 0):+.2f}")
    print(f"  v1={last['v1']:+.1f}  v2={last['v2']:+.1f}")
    print(
        f"  effort={last['effort']:+.1f}  up={last.get('up', 0):+.2f}  "
        f"ur={last.get('ur', 0):+.2f}  ux={last.get('ux', 0):+.2f}  "
        f"uv={last.get('uv', 0):+.2f}  uy={last.get('uy', 0):+.2f}"
    )


def cmd_watch(seconds):
    log = latest_log()
    if not log:
        print("No log files found in data/")
        return

    print(f"Watching for {seconds}s...")
    end_time = time.time() + seconds
    with open(log) as f:
        f.seek(0, 2)
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
                    ctrl = "ON" if d.get("ctrl_on") else "OFF"
                    print(
                        f"pitch={d['pitch']:+6.1f} vel={d['v1']:+5.1f}/{d['v2']:+5.1f} "
                        f"eff={d['effort']:+6.1f} up={d.get('up', 0):+5.2f} "
                        f"ur={d.get('ur', 0):+5.2f} ux={d.get('ux', 0):+5.2f} "
                        f"uv={d.get('uv', 0):+5.2f} [{ctrl}]"
                    )
            except (json.JSONDecodeError, KeyError):
                continue


def cmd_ctrlrun(last_seconds: float | None = None):
    """Analyze the most recent contiguous controller-on run across all logs.

    If last_seconds is given, only the trailing window of the run is used —
    useful for isolating the effect of a recent gain change.
    """
    import statistics

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
                if d.get("ctrl_on") == 1:
                    samples.append(d)
        if samples:
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
        print("no controller-on runs found")
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
    efforts = [s["effort"] for s in run]
    ups = [s.get("up", 0) for s in run]
    urs = [s.get("ur", 0) for s in run]
    uxs = [s.get("ux", 0) for s in run]
    uvs = [s.get("uv", 0) for s in run]
    uys = [s.get("uy", 0) for s in run]
    lhzs = [s["lhz"] for s in run]
    sat_pct = 100 * sum(1 for e in efforts if abs(e) >= 99) / len(efforts)
    print(
        f"pitch: [{min(pitches):.2f}, {max(pitches):.2f}] "
        f"std={statistics.stdev(pitches) if len(pitches)>1 else 0:.2f}"
    )
    print(f"effort: [{min(efforts):.1f}, {max(efforts):.1f}]  saturated: {sat_pct:.1f}%")
    print(f"up (θ):    [{min(ups):+.2f}, {max(ups):+.2f}]")
    print(f"ur (θ̇):    [{min(urs):+.2f}, {max(urs):+.2f}]")
    print(f"ux (pos):  [{min(uxs):+.2f}, {max(uxs):+.2f}]")
    print(f"uv (vel):  [{min(uvs):+.2f}, {max(uvs):+.2f}]")
    print(f"uy (yaw):  [{min(uys):+.2f}, {max(uys):+.2f}]")
    print(f"loop_hz:[{min(lhzs):.1f}, {max(lhzs):.1f}]")

    # Dominant frequency from zero crossings around mean
    pm = sum(pitches) / len(pitches)
    xs = 0
    for i in range(1, len(pitches)):
        if (pitches[i - 1] - pm) * (pitches[i] - pm) < 0:
            xs += 1
    if xs and dur > 0:
        print(f"pitch zero-cross freq: {xs/2/dur:.2f} Hz")

    # Separate fast (ring) vs slow (drift) components via 1s moving-average.
    wsize = max(1, int(len(run) / max(dur, 1e-3)))
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
    win_s = max(0.5, min(5.0, dur / 4))
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
    print(f"  {'t(s)':>6}  {'wp_pkpk':>8}  {'pitch_pkpk':>10}  {'fast_std':>8}  {'wp_mean':>8}  {'sat%':>5}")
    for w in buckets:
        if len(w) < 2:
            continue
        t = (w[0]["t"] - t0) / 1000
        wps_w = [s["wp"] for s in w]
        pit_w = [s["pitch"] for s in w]
        eff_w = [s["effort"] for s in w]
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
        sat_w = 100 * sum(1 for e in eff_w if abs(e) >= 99) / len(eff_w)
        print(
            f"  {t:>6.1f}  {max(wps_w)-min(wps_w):>8.2f}  "
            f"{max(pit_w)-min(pit_w):>10.2f}  {fast_std_w:>8.3f}  "
            f"{sum(wps_w)/len(wps_w):>8.2f}  {sat_w:>5.1f}"
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
    elif cmd == "ctrlrun":
        last = float(sys.argv[2]) if len(sys.argv) > 2 else None
        cmd_ctrlrun(last)
    else:
        msg = " ".join(sys.argv[1:])
        asyncio.run(cmd_send(msg))


main()
