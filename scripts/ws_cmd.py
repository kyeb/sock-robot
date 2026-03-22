#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets"]
# ///
"""Send commands and capture data via the bridge WebSocket.

Usage:
    ./scripts/ws_cmd.py send "KP 8" "KD 0.8" "PID_ON"
    ./scripts/ws_cmd.py capture 3          # capture 3 seconds of data
    ./scripts/ws_cmd.py send "KP 8" "KD 0.8" "PID_ON" --capture 5
"""

import asyncio
import json
import sys
import time

WS_URL = "ws://localhost:8080/ws"


async def run(commands: list[str], capture_secs: float | None):
    from websockets.asyncio.client import connect

    async with connect(WS_URL) as ws:
        for cmd in commands:
            await ws.send(cmd)
            print(f"[sent] {cmd}")

        if capture_secs is None:
            return

        samples = []
        deadline = time.monotonic() + capture_secs
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

        if not samples:
            print("No data captured.")
            return

        for line in samples:
            print(json.dumps(line))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    commands = []
    capture_secs = None
    i = 0
    while i < len(args):
        if args[i] == "send":
            i += 1
        elif args[i] == "capture":
            i += 1
            if i < len(args) and not args[i].startswith("-"):
                capture_secs = float(args[i])
                i += 1
            else:
                capture_secs = 3.0
        elif args[i] == "--capture":
            i += 1
            capture_secs = float(args[i]) if i < len(args) else 3.0
            i += 1
        else:
            commands.append(args[i])
            i += 1

    asyncio.run(run(commands, capture_secs))


if __name__ == "__main__":
    main()
