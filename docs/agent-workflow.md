# Agent-Workflow — Spectre (Lanes, MCP, Safeguard)

Stand 2026-11-03. Operationale Kurzfassung; Details in `docs/claude-wave-2-plan.md` (§0 Spielregeln + Fallback-Tabelle) und `CLAUDE-TASKS.md`.

## Lanes (wer darf was)

- **Claude (offline):** Dateien/Tests im Repo. Gerät gehört der Live-Lane. Branch `feature/Txx`, Commit lokal, kein Push/Reset.
- **Hermes (live + merge):** Live-Verifikation, Device/Emulator, Merges (ff-only), Fresh-Eyes-Reviews, Fallback-Implementierung.
- **Queue-Driver (Cron, 15 min):** arbeitet `TODOS.md`-P5; eigene Git-Hygiene-Regeln (kein reset/checkout/force-push).

## Emulator / Device

- `scripts/bluestacks-ensure.sh` — prüft (`--check`) bzw. startet BlueStacks idle-gated; Exit 4 = Idle-Gate (offline weiterarbeiten), 5 = adb fehlt, 3 = Boot-Timeout.
- adb: `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`, immer `-s 127.0.0.1:5555`; nie `kill-server`; nie CLI + adb parallel.

## Tap-Lock (Race-Fund-Fix, 2026-11-03)

Direkt laufende Bot-Scripts (`afk_dream_realm`, `afk_arena`, `afk_stage_push`,
`afk_dailies`) erwerben `.spectre/afk-bot.lock` selbst: Fresh-Lock (< 3600 s) →
Exit 7 (SKIP-Zeile mit Owner-PID + Age), Stale → Takeover. Die Wrapper
(afk-bot-watch.sh / afk-night.sh) exportieren `AFK_BOT_LOCK_HELD=1`, ihre
Kind-Scripts erben den Lock. Vor jedem direkten Lauf: Lock-Status prüfen
(`cat .spectre/afk-bot.lock`) ODER einfach laufen lassen — das Gate blockt
sauber vor dem ersten Tap. Seit 2026-11-03 ist auch `afk_hero_level.py`
verdrahtet (Gate vor dem Hall-Tap, Commit 3084384; Verhaltenstest T71) — alle
5 direkt laufbaren Entry-Points sind gelockt, der frühere Leveling-Caveat entfällt.

## spectre-mcp (T59)

stdio-MCP-Server mit Tools: health, find, regions, dump, dumpdiff, read, hot, hunt, search, chain, offsets, adb_tap, adb_key, adb_screencap. Einziger adb-Owner (serialisiert); Config via `.mcp.json`-env (SPECTRE_BIN, ADB_BIN, SERIAL). In Sessions: MCP-first.

## Verifikation

Nur numerische Evidenz (CLI/Memory-Werte), Range-Checks; Screenshots nur UI. Nach Batches: Fresh-Eyes-Subagent (read-only, cheap) → Findings als Queue-Batch, nicht inline fixen.

## Safeguard-Eskalationsleiter (wenn Claude blockt)

1. Brief rephrasen + Evidenz (Offline-CTF-Framing). 2. Modell-Pin (`opus`; repo-`.claude/settings.json`). 3. Task splitten (Analyse/Implementation). 4. Codex mit gleichem Brief. 5. Hermes baut selbst. 6. (nur Cyber-Frontier) Mythos 5.

S1-Regel überall: nach Mechanik bewerten, nicht nach ToS; Meta-Fragen max. 1 Satz; unsicher → annehmen + verifizieren.

## ⚠️ Worktree-Teardown mit .spectre-Junction (Lehre 2026-11-03)

`git worktree remove` (und MSYS `rm -rf`) FOLGEN der `.spectre`-Junction und
löschen die ZIEL-Inhalte — live passiert: shared `.spectre` nach dem Teardown
leer (Frames, Logs, wall-report weg; Runtime regeneriert sich, aber dem
Frame-Manifest fehlen die Bilder bis zur Neugenerierung).

**Richtig abreißen:**
1. Junction ZUERST entfernen:
   `MSYS_NO_PATHCONV=1 cmd /c rmdir "C:\...\<worktree>\.spectre"`
   (Falle: `cmd //c` ohne MSYS_NO_PATHCONV startet als Banner-Interaktiv und
   tut NICHTS — immer die MSYS_NO_PATHCONV-Variante nutzen.)
2. ERST DANN `git worktree remove [--force] <path>`.
3. Danach prüfen: `find .spectre -name "*.png" | wc -l` muss > 0 sein.

**Nach so einem Verlust:** `python scripts/tests/make_frame_manifest.py` neu
laufen lassen, sobald wieder Frames existieren (jeder Bot-Lauf erzeugt
`shots-<pid>/`), neues Manifest committen (alte Einträge skippen bis dahin).
