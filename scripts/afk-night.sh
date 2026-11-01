#!/bin/bash
# Night-mode stage push: climb stages for hours during idle night hours.
#
# Uses --retry-defeats: on DEFEAT the bot taps Retry and keeps pushing - the
# retry loop wins the wall eventually (verified: 249->252 over ~2 h). Wall
# reports land in .spectre/wall-report.log (JSONL).
#
# Called by Task "Spectre AFK Night" (02:00 daily). The idle gate (180 s)
# applies: if Sergej uses the PC, the run skips.
set -u
cd "$(dirname "$0")/.."
SPECTRE="./target/release/spectre.exe"
OUT_DIR=".spectre"

mkdir -p "$OUT_DIR"

# lock: shared with the scheduled task
LOCK="$OUT_DIR/afk-bot.lock"
LOCK_STALE="${AFK_LOCK_STALE:-1200}"
if [ -e "$LOCK" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$age" -lt "$LOCK_STALE" ]; then
    echo "afk-night: another run in progress (lock age ${age}s)" >&2
    exit 6
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

pid=$("$SPECTRE" find igame --adb 2>/dev/null | awk '/^[0-9]+[[:space:]]/ {print $1; exit}')
if [ -z "${pid:-}" ]; then
  echo "afk-night: game process not found" >&2
  exit 2
fi

base_tmp="$OUT_DIR/regions.json"
if ! "$SPECTRE" regions "$pid" --adb --json > "$base_tmp" 2>/dev/null; then
  echo "afk-night: 'regions' failed for pid $pid" >&2
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
    if s >> 44 != 0x7:
        continue
    size = e - s
    if best is None or size > best[1]:
        best = (s, size)
print(f"0x{best[0]:X}" if best else "")
PY
)
if [ -z "${base:-}" ]; then
  echo "afk-night: could not resolve the hot-heap base for pid $pid" >&2
  exit 3
fi

echo "afk-night: pid=$pid heap_base=$base"
mkdir -p "$OUT_DIR/logs"
LOG="$OUT_DIR/logs/afk-bot-$(date -u +%Y-%m-%d).log"
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) NIGHT STAGE PUSH pid=$pid heap_base=$base"
  python scripts/afk_stage_push.py --auto --auto-minutes 240 --retry-defeats \
    --pid "$pid" --base "$base" 2>&1
} | tee -a "$LOG"
