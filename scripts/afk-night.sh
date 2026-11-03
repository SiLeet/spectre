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

mkdir -p "$OUT_DIR" "$OUT_DIR/logs"
LOG="$OUT_DIR/logs/afk-bot-$(date -u +%Y-%m-%d).log"

# lock: shared with the scheduled task
LOCK="$OUT_DIR/afk-bot.lock"
LOCK_STALE="${AFK_LOCK_STALE:-3600}"
if [ -e "$LOCK" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$age" -lt "$LOCK_STALE" ]; then
    echo "afk-night: another run in progress (lock age ${age}s)" | tee -a "$LOG" >&2
    exit 6
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
LOCK_KEEPER=""
cleanup() {
  [ -n "$LOCK_KEEPER" ] && kill "$LOCK_KEEPER" 2>/dev/null
  rm -f "$LOCK"
}
trap cleanup EXIT
( while [ -e "$LOCK" ]; do sleep 240; touch "$LOCK" 2>/dev/null || true; done ) &
LOCK_KEEPER=$!

find_pid() { "$SPECTRE" find igame --adb 2>/dev/null | awk '/^[0-9]+[[:space:]]/ {print $1; exit}'; }
pid=$(find_pid)
# T68 step 0: game/emulator not reachable -> one bounded device-ensure
# (BlueStacks + game start, title/login popups only; idle-gated like this
# run). Any failure is only a warning: the normal check below decides.
if [ -z "${pid:-}" ] && [ "${AFK_DEVICE_ENSURE:-1}" = "1" ]; then
  echo "afk-night: game not reachable — device-ensure (--min-idle ${AFK_MIN_IDLE:-180})" | tee -a "$LOG"
  timeout "${AFK_ENSURE_TIMEOUT:-600}" bash scripts/device-ensure.sh --min-idle "${AFK_MIN_IDLE:-180}" 2>&1 | tee -a "$LOG"
  ens_rc="${PIPESTATUS[0]}"
  case "$ens_rc" in
    0) echo "afk-night: device-ensure ok" | tee -a "$LOG" ;;
    4) echo "afk-night: device-ensure skipped (idle gate: PC in use)" | tee -a "$LOG" ;;
    *) echo "afk-night: WARN device-ensure rc=$ens_rc — continuing with the normal checks" | tee -a "$LOG" ;;
  esac
  pid=$(find_pid)
fi
if [ -z "${pid:-}" ]; then
  echo "afk-night: game process not found (is BlueStacks running and the game open?)" | tee -a "$LOG" >&2
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
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) NIGHT STAGE PUSH pid=$pid heap_base=$base"
  python scripts/afk_stage_push.py --auto --auto-minutes 135 --retry-defeats \
    --pid "$pid" --base "$base" --min-idle "${AFK_MIN_IDLE:-180}" 2>&1
} | tee -a "$LOG"
pipeline_rc=("${PIPESTATUS[@]}")
push_rc="${pipeline_rc[0]}"
tee_rc="${pipeline_rc[1]}"
if [ "$push_rc" -ne 0 ]; then
  exit "$push_rc"
fi
exit "$tee_rc"
