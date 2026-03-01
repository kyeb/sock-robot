# sock-robot

## Building and flashing

Run `./flash.sh` from the project root. Pass `--monitor` to watch serial output after flash.

The script uses `-B 1500000` for fast baud rate (~2s flash vs ~30s at default).

Do NOT use `cargo espflash flash --monitor` from Claude — the monitor needs a TTY and will fail. Use pyserial scripts instead to interact with the device.

## Development notes

- **No head/tail on build output.** Don't pipe build or flash commands through `head` or `tail` — it truncates useful output and kills the process early.
- **Python scripts are self-contained uv scripts.** Use `#!/usr/bin/env -S uv run` with inline dependency metadata. Don't create a uv project or use pip install.
- **Serial monitoring from Claude:** Use pyserial in Python scripts, not `espflash monitor` (needs TTY).
- **UART:** Firmware uses raw `uart_read_bytes` from ESP-IDF sys, not the HAL `UartDriver` (which conflicts with ESP-IDF's UART0 logging).
- **Toolchain:** Uses the `esp` Rust toolchain channel (xtensa target). See `rust-toolchain.toml`.
- **Serial port:** `/dev/cu.usbserial-0001`
