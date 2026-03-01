#!/bin/bash
cd "$(dirname "$0")"
cargo espflash flash -B 1500000 "$@"
