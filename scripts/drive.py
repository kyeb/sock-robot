#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyserial"]
# ///
"""Arrow-key motor controller for sock-robot.

  UP    = both forward
  DOWN  = both reverse
  LEFT  = turn left (M1 rev, M2 fwd)
  RIGHT = turn right (M1 fwd, M2 rev)
  SPACE = stop
  q     = quit
"""

import os
import serial
import sys
import termios
import time
import tty

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-0001"

def send(ser: serial.Serial, cmd: str):
    ser.write(f"{cmd}\n".encode())


def write(msg: str):
    os.write(sys.stdout.fileno(), msg.encode())


def readch() -> bytes:
    return os.read(sys.stdin.fileno(), 1)


def main():
    speed = 60
    ser = serial.Serial(PORT, 115200, timeout=0.1)

    # Reset ESP32 and wait for boot
    print("Resetting ESP32...", end=" ", flush=True)
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.rts = False
    time.sleep(3)
    # Drain boot output
    ser.read(ser.in_waiting or 4096)
    print("ready!")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    write("sock-robot controller\r\n")
    write("Arrow keys to drive, SPACE to stop, 1-9 to set speed, q to quit\r\n\r\n")

    try:
        tty.setraw(fd)
        while True:
            ch = readch()
            if ch in (b"q", b"\x03"):  # q or ctrl+c
                send(ser, "STOP")
                break
            elif ch in (b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"):
                speed = int(ch) * 10
                write(f"  SPEED={speed}%\r\n")
            elif ch == b" ":
                send(ser, "STOP")
                write("  STOP\r\n")
            elif ch == b"\x1b":
                seq = readch() + readch()
                if seq == b"[A":  # up
                    send(ser, f"M1 {speed}")
                    send(ser, f"M2 {speed}")
                    write(f"  FWD {speed}%\r\n")
                elif seq == b"[B":  # down
                    send(ser, f"M1 -{speed}")
                    send(ser, f"M2 -{speed}")
                    write(f"  REV {speed}%\r\n")
                elif seq == b"[C":  # right
                    send(ser, f"M1 {speed}")
                    send(ser, f"M2 -{speed}")
                    write(f"  RIGHT {speed}%\r\n")
                elif seq == b"[D":  # left
                    send(ser, f"M1 -{speed}")
                    send(ser, f"M2 {speed}")
                    write(f"  LEFT {speed}%\r\n")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        ser.close()
        print("\nbye")


if __name__ == "__main__":
    main()
