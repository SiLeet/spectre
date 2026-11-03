#!/usr/bin/env bash
# bluestacks-ensure.sh — stellt sicher, dass BlueStacks (Instanz Pie64) läuft und adb verbunden ist.
# Nutzung: scripts/bluestacks-ensure.sh [--check] [--force] [--min-idle SEK]
#   --check    nur Status: 0 = ok (läuft + adb verbunden), 1 = nicht ok
#   --force    Idle-Gate ignorieren (z. B. manueller Aufruf)
#   --min-idle Mindest-Idle in s, wenn NICHT --force (Default 180)
# Exit: 0 ok · 2 Start fehlgeschlagen · 3 Boot-Timeout · 4 Idle-Gate blockiert · 5 adb fehlt
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG="$REPO/.spectre/logs/bluestacks-ensure.log"
mkdir -p "$(dirname "$LOG")"
log(){ echo "$(date '+%F %T') [ensure] $*" | tee -a "$LOG"; }

ADB="${ADB:-$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe}"
[ -x "$ADB" ] || ADB="$HOME/platform-tools/adb.exe"
[ -x "$ADB" ] || ADB="/c/Program Files/BlueStacks_nxt/HD-Adb.exe"
[ -x "$ADB" ] || { log "FEHLER: kein adb gefunden"; exit 5; }

BS="/c/Program Files/BlueStacks_nxt/HD-Player.exe"
INSTANCE="${BS_INSTANCE:-Pie64}"
SERIAL="${BS_SERIAL:-127.0.0.1:5555}"
BOOT_TIMEOUT="${BS_BOOT_TIMEOUT:-240}"

MODE=run; FORCE=0; MIN_IDLE=180
while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE=check;;
    --force) FORCE=1;;
    --min-idle) MIN_IDLE="${2:-180}"; shift;;
    *) echo "unbekanntes Argument: $1" >&2; exit 64;;
  esac
  shift
done

vm_running(){ tasklist 2>/dev/null | grep -qi "HD-Player.exe"; }
connected(){ "$ADB" -s "$SERIAL" get-state 2>/dev/null | grep -q "device"; }
idle_seconds(){
  python3 - 2>/dev/null <<'PY' || echo 999
import ctypes
class LII(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("dwTime", ctypes.c_uint32)]
lii = LII(); lii.cbSize = ctypes.sizeof(lii)
ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
print(((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) // 1000)
PY
}

if [ "$MODE" = check ]; then
  if vm_running && connected; then log "check: ok ($SERIAL verbunden)"; exit 0; fi
  log "check: nicht ok (vm_läuft=$(vm_running && echo ja || echo nein), adb=$(connected && echo ja || echo nein))"
  exit 1
fi

if vm_running && connected; then
  log "ok: VM läuft + adb verbunden"
  exit 0
fi

if ! vm_running; then
  if [ "$FORCE" -eq 0 ]; then
    idle="$(idle_seconds)"
    if [ "$idle" -lt "$MIN_IDLE" ]; then
      log "Idle-Gate: ${idle}s < ${MIN_IDLE}s — Emulator NICHT gestartet (offline weiterarbeiten)"
      exit 4
    fi
  fi
  log "starte BlueStacks ($INSTANCE, idle ok)..."
  cmd //c start '""' "$(cygpath -w "$BS")" --instance "$INSTANCE" >/dev/null 2>&1 \
    || { log "FEHLER: BlueStacks-Start fehlgeschlagen ($BS)"; exit 2; }
  sleep 5
else
  log "VM-Prozess läuft bereits, warte auf adb-Verbindung..."
fi

deadline=$(( $(date +%s) + BOOT_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  "$ADB" connect "$SERIAL" >/dev/null 2>&1 || true
  if connected; then log "verbunden: $SERIAL"; exit 0; fi
  sleep 5
done
log "TIMEOUT: $SERIAL nach ${BOOT_TIMEOUT}s nicht verbunden"
exit 3
