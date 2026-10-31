#!/bin/bash
# Find the AFK accrued-time slot: it grows +1/s and resets to ~0 on claim.
# Two dumps ~25 s apart; a candidate must grow by exactly the elapsed seconds.
set -u
cd /c/Users/Sigi/spectre
T="C:/Users/Sigi/AppData/Local/Temp/spectre-gold/timer"
mkdir -p "$T"
PID=7529
ADB="$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe"

t0=$(python -c 'import time;print(time.time())')
./target/release/spectre.exe dump "$PID" 0x724DF0000000 8388608 --adb --format raw --output "$T/X.bin" 2>&1 | tail -1
t1=$(python -c 'import time;print(time.time())')
echo "dump X done at $t1"
sleep 25
t2=$(python -c 'import time;print(time.time())')
./target/release/spectre.exe dump "$PID" 0x724DF0000000 8388608 --adb --format raw --output "$T/Y.bin" 2>&1 | tail -1
t3=$(python -c 'import time;print(time.time())')
echo "TIMES $t0 $t1 $t2 $t3" > "$T/times.txt"

# claim, then dump again: the timer slot must read small
./target/release/spectre.exe -v bot examples/bot-config-afk-live.yaml --adb --once 2>&1 | grep -E "tap sequence" | head -1
tc=$(python -c 'import time;print(time.time())')
./target/release/spectre.exe dump "$PID" 0x724DF0000000 8388608 --adb --format raw --output "$T/Z.bin" 2>&1 | tail -1
t4=$(python -c 'import time;print(time.time())')
echo "CLAIMTIMES $tc $t4" >> "$T/times.txt"
echo "=== DONE"
cat "$T/times.txt"
