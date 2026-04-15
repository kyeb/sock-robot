#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets"]
# ///
"""Send commands to the robot via the WebSocket bridge.

Usage: scripts/cmd.py PID_ON
       scripts/cmd.py VKP 0.5
       scripts/cmd.py STOP
"""
import asyncio
import sys
import websockets

async def main():
    msg = " ".join(sys.argv[1:])
    if not msg:
        print("Usage: scripts/cmd.py <command> [args]")
        sys.exit(1)
    async with websockets.connect("ws://localhost:8080") as ws:
        await ws.send(msg)
        print(f"sent: {msg}")

asyncio.run(main())
