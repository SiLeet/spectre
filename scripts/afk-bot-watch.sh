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
# --scheduled-progress: same idle gate, but the run does ONLY chest (vision
# driver) + stage push — all once-per-day tasks stay in the 05:10 Daily run.
MIN_IDLE=0
PROGRESS=0
case "${1:-}" in
  --scheduled)          MIN_IDLE="${AFK_MIN_IDLE:-180}" ;;
  --scheduled-progress) MIN_IDLE="${AFK_MIN_IDLE:-180}"; PROGRESS=1 ;;
esac

if ! mkdir -p "$OUT_DIR" "$OUT_DIR/logs"; then
  echo "afk-bot-watch: cannot create the log directory; refusing to continue" >&2
  exit 1
fi
LOG="$OUT_DIR/logs/afk-bot-$(date -u +%Y-%m-%d).log"
if ! printf '=== %s watch start (mode=%s shell_pid=%s)\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${1:-manual}" "$$" >> "$LOG"; then
  echo "afk-bot-watch: cannot write the daily log; refusing to continue" >&2
  exit 1
fi

# Serialize runs: the scheduled task and manual invocations must never tap at
# the same time. The stale threshold must exceed the worst-case runtime (a
# dailies round runs claim + quests + mail, several minutes), otherwise an
# overlapping run deletes the lock and taps concurrently.
LOCK="$OUT_DIR/afk-bot.lock"
LOCK_STALE="${AFK_LOCK_STALE:-1200}"
if [ -e "$LOCK" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$age" -lt "$LOCK_STALE" ]; then
    echo "afk-bot-watch: another run in progress (lock age ${age}s)" | tee -a "$LOG" >&2
    exit 6
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

pid=$("$SPECTRE" find igame --adb 2>/dev/null | awk '/^[0-9]+[[:space:]]/ {print $1; exit}')
if [ -z "${pid:-}" ]; then
  echo "afk-bot-watch: game process not found (is BlueStacks running and the game open?)" | tee -a "$LOG" >&2
  exit 2
fi

base_tmp="$OUT_DIR/regions.json"
if ! "$SPECTRE" regions "$pid" --adb --json > "$base_tmp" 2>/dev/null; then
  echo "afk-bot-watch: 'regions' failed for pid $pid" | tee -a "$LOG" >&2
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
  echo "afk-bot-watch: could not resolve the hot-heap base for pid $pid" | tee -a "$LOG" >&2
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

# Resolve the interpreter explicitly: under Task Scheduler the PATH can differ,
# and silently falling back to the un-gated CLI tap sequence is exactly the
# dangerous mode these scripts exist to avoid. Fail loudly instead.
if [ -n "${AFK_PYTHON:-}" ]; then
  PY="$AFK_PYTHON"
elif command -v python >/dev/null 2>&1 && python -c 'import PIL' >/dev/null 2>&1; then
  PY=python
elif [ -x "$LOCALAPPDATA/hermes/tools/python-3.14.9+20261021-win32-x64/python.exe" ]; then
  PY="$LOCALAPPDATA/hermes/tools/python-3.14.9+20261021-win32-x64/python.exe"
else
  echo "afk-bot-watch: no python with PIL available (set AFK_PYTHON) — refusing to fall back to blind taps" | tee -a "$LOG" >&2
  exit 7
fi
if "$PY" -c 'import PIL' >/dev/null 2>&1; then
  {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$pid heap_base=$base (vision driver, $PY)"
    "$PY" scripts/afk_claim_vision.py --pid "$pid" --base "$base" --min-idle "$MIN_IDLE" 2>&1
  } | tee -a "$LOG"
  rc="${PIPESTATUS[0]}"
  # --scheduled-progress: the 17:10 Progress run = chest (above) + stage push.
  # Stage push is NOT marker-gated here: each Progress run pushes until the
  # wall (the script stops itself on DEFEAT). Daily-only tasks are skipped.
  if [ "$PROGRESS" = "1" ]; then
    if [ "$rc" = "0" ] || [ "$rc" = "4" ]; then
      {
        echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) progress stage push"
        "$PY" scripts/afk_stage_push.py --pid "$pid" --base "$base" --auto --auto-minutes 6 --retry-defeats 2>&1
      } | tee -a "$LOG"
      rc="${PIPESTATUS[0]}"
    fi
    exit "$rc"
  fi
  # --scheduled: once per day, also claim the daily login reward (same gates)
  if [ "$rc" = "0" ] || [ "$rc" = "4" ]; then
    today=$(date -u +%Y-%m-%d)
    last=$(cat "$OUT_DIR/daily-gift-last.txt" 2>/dev/null || echo never)
    if [ "$last" != "$today" ]; then
      {
        echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) daily Journey's Gift"
        "$PY" scripts/afk-daily-gift.py --pid "$pid" --base "$base" --min-idle "$MIN_IDLE" 2>&1
      } | tee -a "$LOG"
      [ "${PIPESTATUS[0]}" = "0" ] && date -u +%Y-%m-%d > "$OUT_DIR/daily-gift-last.txt"
    fi
    # once per day: the full quest/mail routine
    dl_last=$(cat "$OUT_DIR/dailies-last.txt" 2>/dev/null || echo never)
    if [ "$dl_last" != "$today" ]; then
      {
        echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) daily routine (quests + mail)"
        "$PY" scripts/afk_dailies.py --pid "$pid" --base "$base" --min-idle "$MIN_IDLE" 2>&1
      } | tee -a "$LOG"
      [ "${PIPESTATUS[0]}" = "0" ] && date -u +%Y-%m-%d > "$OUT_DIR/dailies-last.txt"
    fi

    # once per day: gameplay loops. Each costs screen time (arena ~80 s, dream
    # realm 7 x ~75 s, stage push ~6 min); the once-per-day markers keep the
    # total hijack window bounded to one run per day.
    run_daily_task() {  # $1 = label, $2 = marker file, rest = command
      local name="$1" marker="$2"; shift 2
      local last
      last=$(cat "$OUT_DIR/$marker" 2>/dev/null || echo never)
      if [ "$last" != "$today" ]; then
        {
          echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) $name"
          "$@" 2>&1
        } | tee -a "$LOG"
        [ "${PIPESTATUS[0]}" = "0" ] && date -u +%Y-%m-%d > "$OUT_DIR/$marker"
      fi
    }
    # arena: use ALL daily attempts (4) — one invocation per attempt is the
    # verified path; a rejected purchase dialog stops the loop early
    if [ "$(cat "$OUT_DIR/arena-last.txt" 2>/dev/null || echo never)" != "$today" ]; then
      first_ok=0
      for i in 1 2 3 4; do
        {
          echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) arena attempt $i/4"
          "$PY" scripts/afk_arena.py --fights 1 --min-idle "$MIN_IDLE" 2>&1
        } | tee -a "$LOG"
        rc_a="${PIPESTATUS[0]}"
        [ "$i" = "1" ] && [ "$rc_a" = "0" ] && first_ok=1
        [ "$rc_a" != "0" ] && break
      done
      # a failed arena day should not burn the marker: a later manual run can retry
      [ "$first_ok" = "1" ] && date -u +%Y-%m-%d > "$OUT_DIR/arena-last.txt"
    fi
    run_daily_task "dream realm (all chances)" "dream-last.txt" \
      "$PY" scripts/afk_dream_realm.py --fights 7 --pid "$pid" --base "$base" \
      --min-idle "$MIN_IDLE"
    run_daily_task "stage push (auto battle)" "stage-last.txt" \
      "$PY" scripts/afk_stage_push.py --auto --auto-minutes 6 --retry-defeats \
      --pid "$pid" --base "$base" --min-idle "$MIN_IDLE"
  fi
  exit "$rc"
fi

echo "afk-bot-watch: vision driver unavailable — refusing the blind CLI fallback" | tee -a "$LOG" >&2
exit 7
