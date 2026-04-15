#!/bin/bash
cd "$(dirname "$0")"

# Kill bridge (holds serial port) before flashing
bridge_pids=$(lsof -t /dev/cu.usbserial-0001 2>/dev/null)
if [ -n "$bridge_pids" ]; then
    echo "Killing bridge (pids: $bridge_pids)..."
    echo "$bridge_pids" | xargs kill 2>/dev/null
    sleep 1
fi

cargo espflash flash -B 1500000 "$@"
flash_exit=$?

# Restart bridge after successful flash
if [ $flash_exit -eq 0 ] && [ -n "$bridge_pids" ]; then
    echo "Restarting bridge..."
    uv run scripts/bridge.py &
    sleep 2
fi

exit $flash_exit
