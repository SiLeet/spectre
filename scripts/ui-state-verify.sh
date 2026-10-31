#!/bin/bash
# Verify ui_state candidates: read a few bytes at each candidate in world view
# and with the AFK panel open, twice each.
set -u
cd /c/Users/Sigi/spectre
T="C:/Users/Sigi/AppData/Local/Temp/spectre-gold/ui"
ADB="$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe"
PID=7529
ADDRS=(0x724DF0071648 0x724DF0072038 0x724DF022E938 0x724DF022B5FC 0x724DF022BAAC 0x724DF0201C68)
tap() { "$ADB" -s 127.0.0.1:5555 shell input tap "$1" "$2"; }

probe() { # $1 = tag
  local tag="$1" i=0
  for a in "${ADDRS[@]}"; do
    ./target/release/spectre.exe dump "$PID" "$a" 16 --adb --format raw --output "$T/probe_${tag}_${i}.bin" >/dev/null 2>&1
    i=$((i+1))
  done
  python - "$tag" "${#ADDRS[@]}" <<'PY'
import struct, sys
from pathlib import Path
tag, count = sys.argv[1], int(sys.argv[2])
T = Path(r'C:/Users/Sigi/AppData/Local/Temp/spectre-gold/ui')
vals = []
for i in range(count):
    p = T / f'probe_{tag}_{i}.bin'
    d = p.read_bytes() if p.exists() else b''
    vals.append(struct.unpack_from('<I', d, 0)[0] if len(d) >= 4 else None)
print(tag, vals)
PY
}

tap 474 1010; sleep 1; tap 474 1010; sleep 1; tap 300 250; sleep 1
probe world1
tap 60 1036; sleep 3
probe panel1
tap 474 1010; sleep 2; tap 300 250; sleep 1
probe world2
tap 60 1036; sleep 3
probe panel2
tap 474 1010
