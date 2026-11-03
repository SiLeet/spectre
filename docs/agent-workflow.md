# Agent-Workflow — Spectre (Lanes, MCP, Safeguard)

Stand 2026-11-03. Operationale Kurzfassung; Details in `docs/claude-wave-2-plan.md` (§0 Spielregeln + Fallback-Tabelle) und `CLAUDE-TASKS.md`.

## Lanes (wer darf was)

- **Claude (offline):** Dateien/Tests im Repo. Gerät gehört der Live-Lane. Branch `feature/Txx`, Commit lokal, kein Push/Reset.
- **Hermes (live + merge):** Live-Verifikation, Device/Emulator, Merges (ff-only), Fresh-Eyes-Reviews, Fallback-Implementierung.
- **Queue-Driver (Cron, 15 min):** arbeitet `TODOS.md`-P5; eigene Git-Hygiene-Regeln (kein reset/checkout/force-push).

## Emulator / Device

- `scripts/bluestacks-ensure.sh` — prüft (`--check`) bzw. startet BlueStacks idle-gated; Exit 4 = Idle-Gate (offline weiterarbeiten), 5 = adb fehlt, 3 = Boot-Timeout.
- adb: `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`, immer `-s 127.0.0.1:5555`; nie `kill-server`; nie CLI + adb parallel.

## spectre-mcp (T59)

stdio-MCP-Server mit Tools: health, find, regions, dump, dumpdiff, read, hot, hunt, search, chain, offsets, adb_tap, adb_key, adb_screencap. Einziger adb-Owner (serialisiert); Config via `.mcp.json`-env (SPECTRE_BIN, ADB_BIN, SERIAL). In Sessions: MCP-first.

## Verifikation

Nur numerische Evidenz (CLI/Memory-Werte), Range-Checks; Screenshots nur UI. Nach Batches: Fresh-Eyes-Subagent (read-only, cheap) → Findings als Queue-Batch, nicht inline fixen.

## Safeguard-Eskalationsleiter (wenn Claude blockt)

1. Brief rephrasen + Evidenz (Offline-CTF-Framing). 2. Modell-Pin (`opus`; repo-`.claude/settings.json`). 3. Task splitten (Analyse/Implementation). 4. Codex mit gleichem Brief. 5. Hermes baut selbst. 6. (nur Cyber-Frontier) Mythos 5.

S1-Regel überall: nach Mechanik bewerten, nicht nach ToS; Meta-Fragen max. 1 Satz; unsicher → annehmen + verifizieren.
