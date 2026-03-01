#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyserial"]
# ///
"""E2E serial test for sock-robot ESP32 firmware."""

import serial
import sys
import time

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-0001"
BAUD = 115200


def reset_and_read(port: str, duration: float = 8) -> str:
    ser = serial.Serial(port, BAUD, timeout=2)
    time.sleep(0.5)

    # Reset ESP32 via RTS toggle
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.rts = False

    # Read continuously until duration elapses
    chunks = []
    end = time.time() + duration
    while time.time() < end:
        waiting = ser.in_waiting
        if waiting:
            chunks.append(ser.read(waiting))
        else:
            time.sleep(0.1)
    ser.close()
    return b"".join(chunks).decode("utf-8", errors="replace")


def main():
    print(f"Reading from {PORT}...")
    output = reset_and_read(PORT)

    assert "sock-robot ready" in output, f"Missing ready message. Got:\n{output}"

    print("PASS")
    print("---")
    # Print just the app log lines
    for line in output.splitlines():
        if "sock_robot" in line:
            print(line)


if __name__ == "__main__":
    main()
