#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyserial", "websockets"]
# ///
"""IMU WebSocket server — reads serial JSONL and broadcasts to clients.

Usage:
    ./scripts/imu_dashboard.py [PORT]

Broadcasts IMU data via WebSocket on ws://localhost:8080/ws.
Data is saved to data/<timestamp>.jsonl for later analysis.

Run the dashboard frontend separately:
    cd dashboard && npm run dev    # http://localhost:3000
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import serial
import websockets
from websockets.asyncio.server import serve

PORT = "/dev/cu.usbserial-0001"
BAUD = 115200
WEB_PORT = 8080

# All connected websocket clients
clients: set = set()

# JSONL output file
log_file = None


async def ws_handler(websocket):
    clients.add(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        clients.discard(websocket)


async def broadcast(data: str):
    if clients:
        websockets.broadcast(clients, data)


async def serial_reader(port: str, baud: int):
    """Read serial data, log to file, broadcast to websockets."""
    global log_file

    # Open log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent.parent / "data" / f"{timestamp}.jsonl"
    log_file = open(log_path, "a")
    print(f"Logging to {log_path}")

    # Open serial and reset ESP32
    ser = serial.Serial(port, baud, timeout=0.01)
    print("Resetting ESP32...", end=" ", flush=True)
    ser.dtr = False
    ser.rts = True
    await asyncio.sleep(0.1)
    ser.rts = False
    await asyncio.sleep(3)
    ser.read(ser.in_waiting or 4096)
    print("ready!")

    print(f"WebSocket: ws://localhost:{WEB_PORT}/ws")
    print(f"Dashboard: cd dashboard && npm run dev")

    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, ser.readline)
        if not line:
            continue

        line = line.decode("utf-8", errors="replace").strip()
        if not line.startswith("{"):
            if line:
                print(f"[log] {line}")
            continue

        try:
            json.loads(line)
        except json.JSONDecodeError:
            continue

        log_file.write(line + "\n")
        log_file.flush()

        await broadcast(line)


async def main():
    args = sys.argv[1:]
    port = args[0] if args else PORT

    server = await serve(ws_handler, "0.0.0.0", WEB_PORT)

    print(f"WebSocket server on :{WEB_PORT}")

    try:
        await serial_reader(port, BAUD)
    except KeyboardInterrupt:
        pass
    finally:
        if log_file:
            log_file.close()
        server.close()
        print("\nDone.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
