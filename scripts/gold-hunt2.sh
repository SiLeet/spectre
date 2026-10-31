#!/bin/bash
# Gold hunt round 2: different accrual -> different delta. Intersect with round 1.
set -u
cd /c/Users/Sigi/spectre
T="C:/Users/Sigi/AppData/Local/Temp/spectre-gold/heaps"
PID=7529
REGIONS=(
  "0x724dd04e7000 0x724dd4a16000"
  "0x724ddff1d000 0x724de4700000"
  "0x724e30000000 0x724e33400000"
  "0x724e60000000 0x724e64400000"
  "0x724ea0000000 0x724ea9400000"
  "0x724eb0000000 0x724eb4000000"
)
dump_all() {
  local tag="$1" idx=0
  for r in "${REGIONS[@]}"; do
    set -- $r
    local size=$(( $2 - $1 ))
    ./target/release/spectre.exe dump "$PID" "$1" "$size" --adb --format raw --output "$T/${tag}_${idx}.bin" 2>&1 | tail -1
    idx=$((idx+1))
  done
}
echo "=== A2 $(date -u +%H:%M:%S)"; dump_all A2
echo "=== CLAIM $(date -u +%H:%M:%S)"
./target/release/spectre.exe -v bot examples/bot-config-afk-live.yaml --adb --once 2>&1 | grep -E "tap sequence|WARN" | head -2
echo "=== B2 $(date -u +%H:%M:%S)"; dump_all B2
echo "=== DONE $(date -u +%H:%M:%S)"
