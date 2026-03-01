#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyserial", "websockets"]
# ///
"""IMU live dashboard — logs serial JSONL and serves a real-time web chart.

Usage:
    ./scripts/imu_dashboard.py [PORT]

Opens http://localhost:8080 with live accel + gyro charts.
Data is saved to data/<timestamp>.jsonl for later analysis.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import serial
import websockets
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

PORT = "/dev/cu.usbserial-0001"
BAUD = 115200
WEB_PORT = 8080

# All connected websocket clients
clients: set = set()

# JSONL output file
log_file = None

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>sock-robot IMU</title>
<script src="https://cdn.jsdelivr.net/npm/smoothie@1"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #1a1a2e; color: #eee; font-family: system-ui, sans-serif; padding: 16px; }
  h1 { font-size: 18px; margin-bottom: 12px; color: #888; }
  .charts { display: flex; flex-direction: column; gap: 12px; max-width: 1200px; margin: 0 auto; }
  .chart-section h2 { font-size: 14px; color: #aaa; margin-bottom: 4px; }
  .chart-section canvas { width: 100%; height: 200px; border-radius: 8px; }
  .legend { display: flex; gap: 16px; margin-bottom: 4px; font-size: 12px; }
  .legend span::before { content: ''; display: inline-block; width: 12px; height: 3px; margin-right: 4px; vertical-align: middle; }
  .status { font-size: 12px; color: #666; margin-top: 8px; }
  #rate { color: #4cc9f0; }
</style>
</head>
<body>
<h1>sock-robot IMU</h1>
<div class="charts">
  <div class="chart-section">
    <h2>Accelerometer (m/s&sup2;)</h2>
    <div class="legend">
      <span style="color:#f72585" id="ax-val">X</span>
      <span style="color:#4cc9f0" id="ay-val">Y</span>
      <span style="color:#7209b7" id="az-val">Z</span>
    </div>
    <canvas id="accelChart"></canvas>
  </div>
  <div class="chart-section">
    <h2>Gyroscope (rad/s)</h2>
    <div class="legend">
      <span style="color:#f77f00" id="gx-val">X</span>
      <span style="color:#06d6a0" id="gy-val">Y</span>
      <span style="color:#118ab2" id="gz-val">Z</span>
    </div>
    <canvas id="gyroChart"></canvas>
  </div>
</div>
<div class="status">
  <span id="rate">connecting...</span> &middot; <span id="samples">0</span> samples
</div>
<script>
const chartOpts = {
  millisPerPixel: 20,
  grid: { fillStyle: '#16213e', strokeStyle: '#ffffff10', borderVisible: false },
  labels: { fillStyle: '#888', fontSize: 11 },
  interpolation: 'linear',
  responsive: true,
};

const accelChart = new SmoothieChart({...chartOpts, minValue: -20, maxValue: 20});
const gyroChart = new SmoothieChart({...chartOpts, minValue: -2, maxValue: 2});

function makeSeries(color) {
  return new TimeSeries();
}

const ax = makeSeries(), ay = makeSeries(), az = makeSeries();
const gx = makeSeries(), gy = makeSeries(), gz = makeSeries();

accelChart.addTimeSeries(ax, {strokeStyle: '#f72585', lineWidth: 1.5});
accelChart.addTimeSeries(ay, {strokeStyle: '#4cc9f0', lineWidth: 1.5});
accelChart.addTimeSeries(az, {strokeStyle: '#7209b7', lineWidth: 1.5});

gyroChart.addTimeSeries(gx, {strokeStyle: '#f77f00', lineWidth: 1.5});
gyroChart.addTimeSeries(gy, {strokeStyle: '#06d6a0', lineWidth: 1.5});
gyroChart.addTimeSeries(gz, {strokeStyle: '#118ab2', lineWidth: 1.5});

accelChart.streamTo(document.getElementById('accelChart'), 100);
gyroChart.streamTo(document.getElementById('gyroChart'), 100);

let sampleCount = 0;
let lastRateTime = performance.now();
let rateCount = 0;

const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onopen = () => { document.getElementById('rate').textContent = 'connected'; };
ws.onclose = () => { document.getElementById('rate').textContent = 'disconnected'; };

ws.onmessage = (event) => {
  const d = JSON.parse(event.data);
  const now = Date.now();

  ax.append(now, d.ax); ay.append(now, d.ay); az.append(now, d.az);
  gx.append(now, d.gx); gy.append(now, d.gy); gz.append(now, d.gz);

  document.getElementById('ax-val').textContent = 'X ' + d.ax.toFixed(2);
  document.getElementById('ay-val').textContent = 'Y ' + d.ay.toFixed(2);
  document.getElementById('az-val').textContent = 'Z ' + d.az.toFixed(2);
  document.getElementById('gx-val').textContent = 'X ' + d.gx.toFixed(3);
  document.getElementById('gy-val').textContent = 'Y ' + d.gy.toFixed(3);
  document.getElementById('gz-val').textContent = 'Z ' + d.gz.toFixed(3);

  sampleCount++;
  rateCount++;
  document.getElementById('samples').textContent = sampleCount;
  const t = performance.now();
  if (t - lastRateTime > 1000) {
    const hz = (rateCount / (t - lastRateTime) * 1000).toFixed(0);
    document.getElementById('rate').textContent = hz + ' Hz';
    rateCount = 0;
    lastRateTime = t;
  }
};
</script>
</body>
</html>"""


async def ws_handler(websocket):
    clients.add(websocket)
    try:
        # Handle incoming messages (we don't expect any, but keep connection alive)
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

    print(f"Dashboard: http://localhost:{WEB_PORT}")

    loop = asyncio.get_event_loop()
    while True:
        # Read serial in executor to avoid blocking event loop
        line = await loop.run_in_executor(None, ser.readline)
        if not line:
            continue

        line = line.decode("utf-8", errors="replace").strip()
        if not line.startswith("{"):
            # Skip non-JSON lines (boot messages, log output)
            if line:
                print(f"[log] {line}")
            continue

        try:
            # Validate it's proper JSON
            json.loads(line)
        except json.JSONDecodeError:
            continue

        # Log to file
        log_file.write(line + "\n")
        log_file.flush()

        # Broadcast to all websocket clients
        await broadcast(line)


async def main():
    args = sys.argv[1:]
    port = args[0] if args else PORT

    # Custom handler that serves HTML for HTTP and upgrades WebSocket
    async def handler(websocket):
        await ws_handler(websocket)

    async def process_request(connection, request):
        if request.path != "/ws":
            return Response(
                200, "OK",
                Headers({"Content-Type": "text/html; charset=utf-8"}),
                HTML.encode(),
            )

    server = await serve(
        handler,
        "0.0.0.0",
        WEB_PORT,
        process_request=process_request,
    )

    print(f"WebSocket server on :{WEB_PORT}")

    # Run serial reader
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
