#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyserial", "websockets"]
# ///
"""IMU WebSocket server — reads serial JSONL and broadcasts to clients.

Usage:
    ./scripts/bridge.py [PORT]

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

clients: set = set()
log_file = None
capture_file = None

# Queue for commands from dashboard → serial (avoids thread-safety issues)
cmd_queue: asyncio.Queue = asyncio.Queue()


async def ws_handler(websocket):
    global capture_file
    clients.add(websocket)
    try:
        async for message in websocket:
            msg = message.strip()
            if not msg:
                continue
            if msg == "CAPTURE_START":
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                cap_path = Path(__file__).parent.parent / "data" / f"capture_{ts}.jsonl"
                capture_file = open(cap_path, "w")
                print(f"[capture] started → {cap_path}")
                await websocket.send(json.dumps({"capture": "started", "file": str(cap_path.name)}))
            elif msg == "CAPTURE_STOP":
                if capture_file:
                    capture_file.close()
                    print(f"[capture] stopped")
                    capture_file = None
                await websocket.send(json.dumps({"capture": "stopped"}))
            else:
                print(f"[cmd] {msg}")
                await cmd_queue.put(msg)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)


async def broadcast(data: str):
    if clients:
        websockets.broadcast(clients, data)


async def serial_reader(port: str, baud: int):
    global log_file

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(__file__).parent.parent / "data" / f"{timestamp}.jsonl"
    log_file = open(log_path, "a")
    print(f"Logging to {log_path}")

    ser = serial.Serial(port, baud, timeout=0.01)
    print("Resetting ESP32...", end=" ", flush=True)
    ser.dtr = False
    ser.rts = True
    await asyncio.sleep(0.1)
    ser.rts = False
    await asyncio.sleep(3)
    ser.read(ser.in_waiting or 4096)
    print("ready!")
    await broadcast(json.dumps({"bridge": "connected"}))

    print(f"WebSocket: ws://localhost:{WEB_PORT}/ws")
    print(f"Dashboard: cd dashboard && npm run dev")

    loop = asyncio.get_event_loop()
    while True:
        # Drain command queue → serial (all in this single thread, no races)
        while not cmd_queue.empty():
            cmd = cmd_queue.get_nowait()
            ser.write((cmd + "\n").encode())

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

        if capture_file:
            capture_file.write(line + "\n")
            capture_file.flush()

        await broadcast(line)


async def main():
    args = sys.argv[1:]
    port = args[0] if args else PORT

    server = await serve(ws_handler, "0.0.0.0", WEB_PORT)
    print(f"WebSocket server on :{WEB_PORT}")

    while True:
        try:
            await serial_reader(port, BAUD)
        except serial.SerialException as e:
            print(f"\nSerial error: {e}")
            await broadcast(json.dumps({"bridge": "disconnected"}))
            print("Reconnecting in 2s...")
            await asyncio.sleep(2)
        except KeyboardInterrupt:
            break

    if log_file:
        log_file.close()
    server.close()
    print("\nDone.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
