# _t34_patch.py — re-apply the once-per-day gameplay loops in afk-bot-watch.sh
from pathlib import Path

w = Path(r'C:\Users\Sigi\spectre\scripts\afk-bot-watch.sh')
t = w.read_text(encoding='utf-8')

if 'run_daily_task' in t:
    print('ALREADY APPLIED — nothing to do')
    raise SystemExit(0)

old = """    # once per day: the full quest/mail routine
    dl_last=$(cat "$OUT_DIR/dailies-last.txt" 2>/dev/null || echo never)
    if [ "$dl_last" != "$today" ]; then
      {
        echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) daily routine (quests + mail)"
        "$PY" scripts/afk_dailies.py --pid "$pid" --base "$base" --min-idle "$MIN_IDLE" 2>&1
      } | tee -a "$LOG"
      [ "${PIPESTATUS[0]}" = "0" ] && date -u +%Y-%m-%d > "$OUT_DIR/dailies-last.txt"
    fi
  fi
  exit "$rc\""""
new = """    # once per day: the full quest/mail routine
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
    run_daily_task "arena (1 fight)" "arena-last.txt" \\
      "$PY" scripts/afk_arena.py --fights 1
    run_daily_task "dream realm (all chances)" "dream-last.txt" \\
      "$PY" scripts/afk_dream_realm.py --fights 7
    run_daily_task "stage push (auto battle)" "stage-last.txt" \\
      "$PY" scripts/afk_stage_push.py --auto --auto-minutes 6
  fi
  exit "$rc\""""
assert old in t, 'old block not found — file changed again'
w.write_text(t.replace(old, new), encoding='utf-8')
print('patched OK, run_daily_task present:', 'run_daily_task' in w.read_text(encoding='utf-8'))
