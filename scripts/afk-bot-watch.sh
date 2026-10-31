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

# --scheduled: only act when the PC has been untouched for a while, so a
# scheduled run never hijacks the screen while Sergej is playing or working.
MIN_IDLE=0
if [ "${1:-}" = "--scheduled" ]; then
  MIN_IDLE="${AFK_MIN_IDLE:-180}"
fi

mkdir -p "$OUT_DIR"

# Serialize runs: the scheduled task and manual invocations must never tap at
# the same time. A lock older than 3 minutes is considered stale (a crashed
# run), anything younger means "another run is in progress".
LOCK="$OUT_DIR/afk-bot.lock"
if [ -e "$LOCK" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$age" -lt 180 ]; then
    echo "afk-bot-watch: another run in progress (lock age ${age}s)" >&2
    exit 6
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

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

# Preferred path: the vision driver only taps after verifying the screen state
# (and after a team_power memory preflight). Falls back to the CLI tap sequence
# only when python/PIL is unavailable — never on a state mismatch, that is
# exactly what produced silent no-ops before.
if python -c 'import PIL' >/dev/null 2>&1; then
  {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$pid heap_base=$base (vision driver)"
    python scripts/afk_claim_vision.py --pid "$pid" --base "$base" --min-idle "$MIN_IDLE" 2>&1
  } | tee -a "$LOG"
  rc="${PIPESTATUS[0]}"
  # --scheduled: once per day, also claim the daily login reward (same gates)
  if [ "$rc" = "0" ] || [ "$rc" = "4" ]; then
    today=$(date -u +%Y-%m-%d)
    last=$(cat "$OUT_DIR/daily-gift-last.txt" 2>/dev/null || echo never)
    if [ "$last" != "$today" ] && python -c 'import PIL' >/dev/null 2>&1; then
      {
        echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) daily Journey's Gift"
        python scripts/afk-daily-gift.py --pid "$pid" --base "$base" --min-idle "$MIN_IDLE" 2>&1
      } | tee -a "$LOG"
      [ "${PIPESTATUS[0]}" = "0" ] && date -u +%Y-%m-%d > "$OUT_DIR/daily-gift-last.txt"
    fi
    # once per day: the full quest/mail routine
    dl_last=$(cat "$OUT_DIR/dailies-last.txt" 2>/dev/null || echo never)
    if [ "$dl_last" != "$today" ] && python -c 'import PIL' >/dev/null 2>&1; then
      {
        echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) daily routine (quests + mail)"
        python scripts/afk_dailies.py --pid "$pid" --base "$base" --min-idle "$MIN_IDLE" 2>&1
      } | tee -a "$LOG"
      [ "${PIPESTATUS[0]}" = "0" ] && date -u +%Y-%m-%d > "$OUT_DIR/dailies-last.txt"
    fi
  fi
  exit "$rc"
fi

{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$pid heap_base=$base (CLI tap fallback, no PIL)"
  "$SPECTRE" -v bot "$OUT" --adb --once 2>&1
} | tee -a "$LOG"
