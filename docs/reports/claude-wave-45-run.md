# Claude Wave-4.5 Run (E1–E5) — Sammelbericht (2026-11-04)

Auftrag: E1 → E5 laut Wave-4.5-Prompt, offline, kein push, keine neuen Dependencies,
`.spectre` read-only. Live-verifizierte Pfade (two-tap, `slot_level`-Crop, blocked-skip) nicht
angefasst. Worktree `C:\Users\Sigi\spectre-w45` (ohne Junction), Branches ab `main` (`11c703c`,
Basis **272 Tests**).

| Task | Branch | Commits | Suite auf dem Branch |
|---|---|---|---|
| E1 Review-Testlücken | `feature/T70-review-test-gaps` | `7c64d58` | `Ran 281 tests … OK (skipped=22)` |
| E2 hero_level Tap-Lock | `feature/T71-hero-level-lock` | `5c1dace`, `dd7a3e2` | `Ran 275 tests … OK (skipped=22)` |
| E3 Hand-Scan-Retry | `feature/T72-hand-scan-retry` | `d48c130` | `Ran 276 tests … OK (skipped=22)` |
| E4 MCP Search-Refine | `feature/T73-mcp-search-refine` | `f05ffd7`, `e14f328` (+ dieser Bericht) | Python unverändert 272; `cargo test -p spectre-mcp`: 12 passed |
| E5 Log-Rotation | — (kein Code) | — | — |

**Probe-Merge** T70–T73 auf `main` (detached, nichts verändert): konfliktfrei,
**`Ran 288 tests … OK (skipped=22)`** + `spectre-mcp` 12 passed. Die 22 Skips = Real-Frame-Tests
(Frames nur teilweise regeneriert).

Hinweis zu E2/E4: je ein zweiter Mini-Commit, weil ein Doku-Edit beim ersten Commit noch nicht
angewendet war (kein Amend, keine History-Änderung).

## E1 / T70 — Review-Testlücken (nur Tests, keine Produktionsänderung nötig)

- a) Dream-World-Recovery: genau 2 vollständige Escape-Zyklen (Frames exakt verbraucht, kein
  `escape 3/`), dann `ESCAPE: gave up after 2 cycle(s)` + Exit 1, Taps = 2 × (BACK, GROUND, BACK, BACK).
- b) Arena: Kauf-Dialog in Step 0 der Fight-Chain → `advance_to_fight` gibt `'DIALOG'` (nach
  Cancel-Tap); `main` loggt genau **eine** `STOP: purchase dialog during the fight chain`-Zeile,
  kein Battle-Tap.
- c) watch + night Schritt 0: Hang-Stub für `device-ensure` + aufzeichnender `timeout`-Stub pinnen
  den Wert: `timeout: 600 bash scripts/device-ensure.sh --min-idle 180`; Override
  `AFK_ENSURE_TIMEOUT=45` → `45`; rc 124 bleibt WARN, normaler Check entscheidet (Exit 2).
- d) Dura's: Sweep stoppt sauber, wenn „Sweep" verschwindet; Challenge-Dialog → Rückgabe ohne
  Kampf (Exit 4); keine Token auf ungeclearten Floor → Exit 0 ohne weitere Taps.
- e) Daily-Wrapper zweimal im selben Temp-Root/Tag → genau **1** Leveling-Aufruf (beide Läufe liefen).
- Harness-Hooks: `run_wrapper(extra_files=…)`, `_run_wrapper(runs=N)`. Neue Datei `test_review_gaps.py`.

## E2 / T71 — afk_hero_level im Tap-Lock

- Befund: Das Wiring selbst lag bereits auf `main` (Queue-Driver `1504750`/`3084384`: Gate vor dem
  Hall-Tap, Exit 7, Source-Wiring + Reihenfolge-Check).
- Ergänzt: `HeroLevelLockBehaviour` in `test_bot_lock.py` mit echter Lock-Semantik auf Temp-Lock:
  frischer Fremd-Lock → **Exit 7, 0 Screenshots, 0 Taps**, Owner im SKIP-Log;
  `AFK_BOT_LOCK_HELD=1` → läuft am Gate vorbei, Fremd-Lock bleibt unangetastet; Stale-Lock → Übernahme.
- `docs/agent-workflow.md`: alle 5 Entry-Points gelistet, Leveling-Caveat ersetzt.
- Keine Produktionsänderung; Leveling-Tests unverändert grün.

## E3 / T72 — Hand-Scan-Robustheit

- `scan_hands()`: nicht lesbares Level → **genau 1** Re-Read (`SCAN_RETRY_WAIT` 1,5 s, neuer Shot
  `hl_scan_<x>b`, gleiche `slot_level`-oder-OCR-Lesung), geloggt; weiter `None` → Hand übersprungen.
- `HAND_XS = [730, 850, 970, 1090, 1210]` (gemessene Kartenmitten, `LIVE:`-Kommentar), `HANDS_Y` 460.
- Tests: `test_hand_scan.py` (None→Wert, dauerhaft None, kein Retry wenn lesbar, Mitten gepinnt);
  die Fixture „Scan scheitert" bekommt die 2 Retry-Frames (Assertions unverändert).

## E4 / T73 — MCP Search-Refine

- Passt ins bestehende Tool-Muster ohne Umbau: das `search`-Tool bekam zwei optionale Felder —
  `continue` (bool → `--continue`, vorige Treffermenge verfeinern) und `state` (→ `--state PATH`,
  Default `.spectre-search.json`). Funktioniert für Wert- und Bereichssuche wie `spectre-cli`.
  Tool-Anzahl bleibt 14; README-Zeile ergänzt.
- Test `search_refine_passes_continue_and_state`; `clippy -p spectre-mcp --all-targets`: keine Warnungen.

## E5 / T74 — Log-Rotation

**Vorhanden — nichts gebaut:** watch.sh und night.sh schreiben schon tagesrotiert
(`.spectre/logs/afk-bot-<UTC-Datum>.log`, eine Datei pro Tag; 03.11.: 3,4 KB), eine 5-MB-Grenze
pro Tagesdatei würde nie greifen. Randnotiz: `bluestacks-ensure.log` / `device-ensure.log` sind
undatiert und wachsen unbegrenzt (heute < 1 KB) — bei Bedarf eigener Mini-Task.

## LIVE-Check-Liste für Hermes

1. **E3:** nächster `afk_hero_level.py --level`-Lauf: Taps treffen die Kartenmitten (730/850/…/1210),
   bei sporadischem `None` erscheint `level not readable — one retry` und die Hand wird gelesen.
2. **E2:** direkter `afk_hero_level.py`-Start während eines Wrapper-Laufs → `SKIP: tap lock held … (exit 7)`.
3. **E4:** MCP `search` mit `continue: true` nach einem ersten Scan → Trefferzahl sinkt
   (State-Datei im Arbeitsverzeichnis des MCP-Servers).

## Offene Punkte

- E3-Koordinaten sind gemessen, aber noch nicht mit dem neuen Retry live gefahren.
- E5: undatierte Ensure-Logs ohne Rotation (siehe oben).
- Nicht in dieser Welle (Live-Recon nötig): T29, T45h, Dura's-Koordinaten-Feinschliff.
