#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Extract a specific ctrl-on run from a telemetry log file.

Usage:
    scripts/extract_run.py                          # latest run from latest file
    scripts/extract_run.py data/file.jsonl           # latest run from specific file
    scripts/extract_run.py data/file.jsonl --run 2   # specific run index
    scripts/extract_run.py -o data/my_run.jsonl      # custom output name
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?")
    ap.add_argument("--run", "-r", type=int, default=-1,
                    help="run index (-1 = last)")
    ap.add_argument("--output", "-o", type=str, default=None,
                    help="output file path")
    args = ap.parse_args()

    if args.file:
        path = Path(args.file)
    else:
        data_dir = Path(__file__).parent.parent / "data"
        cands = sorted(data_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        cands = [c for c in cands if c.stat().st_size > 0]
        if not cands:
            raise SystemExit("no logs in data/")
        path = cands[-1]

    lines = path.open().readlines()
    ctrl_key = None
    for line in lines:
        d = json.loads(line.strip())
        if "ctrl_on" in d:
            ctrl_key = "ctrl_on"
            break
        elif "pid_on" in d:
            ctrl_key = "pid_on"
            break
    if not ctrl_key:
        raise SystemExit("no ctrl data found")

    runs = []
    current = []
    for line in lines:
        d = json.loads(line.strip())
        if d.get(ctrl_key):
            current.append(line)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    print(f"file: {path.name} — {len(runs)} ctrl-on runs")
    for i, r in enumerate(runs):
        first = json.loads(r[0])
        last = json.loads(r[-1])
        dur = (last["t"] - first["t"]) / 1000
        print(f"  Run {i}: {len(r)} samples, {dur:.1f}s")

    idx = args.run if args.run >= 0 else len(runs) + args.run
    if idx < 0 or idx >= len(runs):
        raise SystemExit(f"run {args.run} out of range (0..{len(runs)-1})")

    run = runs[idx]
    first = json.loads(run[0])
    last = json.loads(run[-1])
    dur = (last["t"] - first["t"]) / 1000

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = path.parent / f"run_{idx}_{len(run)}s.jsonl"

    with open(out_path, "w") as f:
        f.writelines(run)

    print(f"\nExtracted run {idx}: {len(run)} samples, {dur:.1f}s → {out_path.name}")


if __name__ == "__main__":
    main()
