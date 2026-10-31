#!/bin/bash
# Run one AFK-bot claim round, surviving game restarts.
#
# The game PID and the hot-heap base (ASLR) change on every app restart, so the
# committed config can't hold them permanently. This wrapper re-discovers both,
# writes a generated config (metadata only), and runs a single bot round.
#
# Usage: scripts/afk-bot-watch.sh [--dry-run]
set -u
cd "$(dirname "$0")/.."
SPECTRE="./target/release/spectre.exe"
SRC="examples/bot-config-afk-live.yaml"
OUT_DIR=".spectre"
OUT="$OUT_DIR/afk-live.generated.yaml"

mkdir -p "$OUT_DIR"

pid=$("$SPECTRE" find igame --adb 2>/dev/null | awk '/^[0-9]+[[:space:]]/ {print $1; exit}')
if [ -z "${pid:-}" ]; then
  echo "afk-bot-watch: game process not found (is BlueStacks running and the game open?)" >&2
  exit 2
fi

base_tmp="$OUT_DIR/regions.json"
if ! "$SPECTRE" regions "$pid" --adb --json > "$base_tmp" 2>/dev/null; then
  echo "afk-bot-watch: 'regions' failed for pid $pid" >&2
  exit 3
fi
base=$(python - "$base_tmp" <<'PY'
import json, sys
regs = json.load(open(sys.argv[1]))
best = None
for r in regs:
    s = int(r['start'], 16); e = int(r['end'], 16)
    path = r.get('path') or ''
    perms = r.get('perms', '')
    if not perms.startswith('rw') or path:
        continue
    # the game-state heap is the biggest anonymous rw region in the 0x7... space
    if s >> 44 != 0x7:
        continue
    size = e - s
    if best is None or size > best[1]:
        best = (s, size)
print(f"0x{best[0]:X}" if best else "")
PY
)
if [ -z "${base:-}" ]; then
  echo "afk-bot-watch: could not resolve the hot-heap base for pid $pid" >&2
  exit 3
fi

echo "afk-bot-watch: pid=$pid heap_base=$base"
sed -e "s|^  pid: .*|  pid: $pid                     # auto-detected by scripts/afk-bot-watch.sh|" \
    -e "s|^  heap_base: .*|  heap_base: $base     # auto-detected (ASLR: changes per app start)|" \
    "$SRC" > "$OUT"

if [ "${1:-}" = "--dry-run" ]; then
  "$SPECTRE" bot "$OUT" --dry-run
  exit $?
fi

mkdir -p "$OUT_DIR/logs"
LOG="$OUT_DIR/logs/afk-bot-$(date -u +%Y-%m-%d).log"
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$pid heap_base=$base"
  "$SPECTRE" -v bot "$OUT" --adb --once 2>&1
} | tee -a "$LOG"
