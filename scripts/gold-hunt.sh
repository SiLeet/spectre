#!/bin/bash
# Gold wallet hunt: dump big rw heaps at 3 points around a claim.
# A = idle before, B = right after claim, C = idle 90s later.
# Wallet: A != B, B == C, B > A (claim moves pool -> wallet), stable while idle.
set -u
cd /c/Users/Sigi/spectre
T="C:/Users/Sigi/AppData/Local/Temp/spectre-gold/heaps"
mkdir -p "$T"
PID=7529
BASE=0x724DF0000000

# start:end pairs of the big rw- anonymous regions (from spectre regions --json)
REGIONS=(
  "0x724dd04e7000 0x724dd4a16000"
  "0x724ddff1d000 0x724de4700000"
  "0x724e30000000 0x724e33400000"
  "0x724e60000000 0x724e64400000"
  "0x724ea0000000 0x724ea9400000"
  "0x724eb0000000 0x724eb4000000"
)

dump_all() {
  local tag="$1"
  local idx=0
  for r in "${REGIONS[@]}"; do
    set -- $r
    local start=$1 end=$2
    local size=$(( end - start ))
    local out="$T/${tag}_${idx}.bin"
    if [ -f "$out" ]; then idx=$((idx+1)); continue; fi
    echo "dump $tag heap$idx start=$start size=$size"
    ./target/release/spectre.exe dump "$PID" "$start" "$size" --adb --format raw --output "$out" 2>&1 | tail -1
    idx=$((idx+1))
  done
}

echo "=== PHASE A (idle baseline) $(date -u +%H:%M:%S)"
dump_all A

echo "=== CLAIM $(date -u +%H:%M:%S)"
./target/release/spectre.exe -v bot examples/bot-config-afk-live.yaml --adb --once 2>&1 | grep -E "tap sequence|WARN" | head -3

echo "=== PHASE B (right after claim) $(date -u +%H:%M:%S)"
dump_all B

echo "=== wait 90s idle"
sleep 90

echo "=== PHASE C (idle after) $(date -u +%H:%M:%S)"
dump_all C

echo "=== DONE $(date -u +%H:%M:%S)"
ls -la "$T" | tail -25
