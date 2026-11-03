#!/usr/bin/env bash
# device-ensure.sh — BlueStacks + AFK Journey spielbereit machen (T65, Wave-3 C5).
# Baut auf bluestacks-ensure.sh auf: Emulator + adb sicherstellen, dann das Spiel
# per monkey starten (falls es nicht läuft) und mit scripts/afk_device_ready.py
# bis zur Welt pollen (Titel-Tap OCR-gated, Login-Popup via Resolver, keine
# Blind-Taps). Noch NICHT in watch/night verdrahtet.
# Nutzung: scripts/device-ensure.sh [--force] [--min-idle SEK] [--timeout SEK]
#   --force / --min-idle  gehen an bluestacks-ensure.sh (Idle-Gate)
#   --timeout             max. Sekunden bis zur Welt (Default 180)
# Exit: 0 bereit · 2/3/4/5 von bluestacks-ensure.sh (Start/Boot-Timeout/Idle-Gate/kein adb)
#       · 6 Spiel nicht installiert · 7 Spiel startet nicht · 8 Welt nicht erreicht
#       · 9 kein python mit PIL · 64 unbekanntes Argument
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG="${DEVICE_LOG:-$REPO/.spectre/logs/device-ensure.log}"
mkdir -p "$(dirname "$LOG")"
log(){ echo "$(date '+%F %T') [device] $*" | tee -a "$LOG"; }

ENSURE="${BS_ENSURE:-$SCRIPT_DIR/bluestacks-ensure.sh}"
LOCAL="${LOCALAPPDATA:-}"
ADB="${ADB:-$LOCAL/Android/Sdk/platform-tools/adb.exe}"
[ -x "$ADB" ] || ADB="$HOME/platform-tools/adb.exe"
[ -x "$ADB" ] || ADB="/c/Program Files/BlueStacks_nxt/HD-Adb.exe"
SERIAL="${BS_SERIAL:-127.0.0.1:5555}"
MATCH="${AFK_PROCESS_MATCH:-igame}"
START_TIMEOUT="${GAME_START_TIMEOUT:-60}"

ENSURE_ARGS=(); TIMEOUT=180
while [ $# -gt 0 ]; do
  case "$1" in
    --force) ENSURE_ARGS+=(--force);;
    --min-idle) ENSURE_ARGS+=(--min-idle "${2:-180}"); shift;;
    --timeout) TIMEOUT="${2:-180}"; shift;;
    *) echo "unbekanntes Argument: $1" >&2; exit 64;;
  esac
  shift
done
case "$TIMEOUT" in ''|*[!0-9]*) TIMEOUT=180;; esac

# 1) Emulator + adb (Exit-Codes 2/3/4/5 unverändert durchreichen)
bash "$ENSURE" "${ENSURE_ARGS[@]}"
rc=$?
[ "$rc" -eq 0 ] || { log "bluestacks-ensure: rc=$rc — abbrechen"; exit "$rc"; }

# 2) Spiel-Paket finden (AFK_PACKAGE überschreibt die Suche)
PKG="${AFK_PACKAGE:-}"
if [ -z "$PKG" ]; then
  PKG=$("$ADB" -s "$SERIAL" shell pm list packages 2>/dev/null | tr -d '\r' \
        | sed -n 's/^package://p' | grep -i "$MATCH" | head -n1)
fi
[ -n "$PKG" ] || { log "FEHLER: kein Paket mit '$MATCH' installiert"; exit 6; }

game_pid(){ "$ADB" -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}'; }

# 3) Spiel starten, falls es nicht läuft
pid="$(game_pid)"
if [ -z "$pid" ]; then
  log "starte $PKG (monkey)..."
  "$ADB" -s "$SERIAL" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  deadline=$(( $(date +%s) + START_TIMEOUT ))
  while [ -z "$pid" ] && [ "$(date +%s)" -lt "$deadline" ]; do
    sleep 3
    pid="$(game_pid)"
  done
  [ -n "$pid" ] || { log "FEHLER: $PKG nach ${START_TIMEOUT}s ohne Prozess"; exit 7; }
fi
log "Spiel läuft: $PKG pid=$pid"

# 4) bis zur Welt pollen (Python mit PIL, wie afk-bot-watch.sh)
PY="${AFK_PYTHON:-python}"
"$PY" -c 'import PIL' >/dev/null 2>&1 || { log "FEHLER: kein python mit PIL (AFK_PYTHON setzen)"; exit 9; }
# native python braucht einen Windows-Pfad (MSYS /c/... wird sonst als C:\c\... gelesen)
READY_PY="$(cygpath -m "$SCRIPT_DIR/afk_device_ready.py" 2>/dev/null || printf '%s' "$SCRIPT_DIR/afk_device_ready.py")"
"$PY" "$READY_PY" --timeout "$TIMEOUT" 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
[ "$rc" -eq 0 ] || { log "Welt nicht erreicht (rc=$rc)"; exit 8; }
log "bereit: Welt/AFK-Panel erreicht"
exit 0
