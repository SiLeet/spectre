#!/bin/bash
# ui_state hunt: W = world view, P = AFK panel open. Two cycles each so that
# churn (which differs between cycles) is filtered out:
#   candidate: W1 == W2, P1 == P2, W != P, small value.
set -u
cd /c/Users/Sigi/spectre
T="C:/Users/Sigi/AppData/Local/Temp/spectre-gold/ui"
mkdir -p "$T"
ADB="$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe"
PID=7529
SIZE=4194304

dump() { ./target/release/spectre.exe dump "$PID" 0x724DF0000000 "$SIZE" --adb --format raw --output "$T/$1.bin" 2>&1 | tail -1; }
tap()  { "$ADB" -s 127.0.0.1:5555 shell input tap "$1" "$2"; }

# make sure we start in the world view
tap 474 1010; sleep 1; tap 474 1010; sleep 1; tap 300 250; sleep 1

echo "W1 $(date -u +%H:%M:%S)"; dump W1
echo "open panel"; tap 60 1036; sleep 3
echo "P1 $(date -u +%H:%M:%S)"; dump P1
echo "close panel"; tap 474 1010; sleep 1; tap 300 250; sleep 1
# force some churn so the two world samples differ in noise slots
tap 968 1050; sleep 3; tap 474 1010; sleep 2
echo "W2 $(date -u +%H:%M:%S)"; dump W2
echo "open panel"; tap 60 1036; sleep 3
echo "P2 $(date -u +%H:%M:%S)"; dump P2
echo "close panel"; tap 474 1010
echo "=== DONE $(date -u +%H:%M:%S)"
