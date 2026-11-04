# Claude Wave-5 Run (T75–T80) — Sammelbericht (2026-11-04)

Auftrag: T75 → T80 laut Wave-5-Prompt (reine Speed-/Memory-Welle), offline, kein push, keine
neuen Dependencies, `.spectre` read-only. Worktree `C:\Users\Sigi\spectre-w5` (ohne Junction),
Branches ab `main` (`aa3982a`/`b492f67`, Basis **288 Tests**). Jede Umstellung einzeln begründet;
wo Restrisiko bleibt: Helper + `LIVE:`-Marker statt Umstellung.

| Task | Branch | Commit | Suite auf dem Branch |
|---|---|---|---|
| T75 Tap-/Key-Batching | `feature/T75-tap-batching` | `289b7d9` | `Ran 292 tests … OK (skipped=22)` |
| T76 Shot-/OCR-Fast-Paths | `feature/T76-fast-shots` | `4a9f1a0` | `Ran 296 tests … OK (skipped=22)` |
| T77 `spectre read-batch` | `feature/T77-read-batch` | `ca1b274` | Python 288 unverändert; `cargo test -p spectre-cli`: 46 passed (5 neu) |
| T78 `afk_memory.py` | `feature/T78-afk-memory` | `3329d15` | `Ran 297 tests … OK (skipped=22)` |
| T79 `mem_probe.py` | `feature/T79-mem-probe` | `551f577` | `Ran 297 tests … OK (skipped=22)` |
| T80 Speed-Profil + Timing | `feature/T80-speed-profile` | `144d871` (+ dieser Bericht) | `Ran 303 tests … OK (skipped=22)` |

**Probe-Merge** T75–T80 auf `main` (detached HEAD im Worktree, kein Branch bewegt): konfliktfrei,
**`Ran 333 tests in 40.262s — OK (skipped=22)`** (= 288 + 4 + 8 + 9 + 9 + 15).
Rust auf dem Merge (GNU-Toolchain): `check --workspace` 0 errors, `clippy --workspace --all-targets`
**0 warnings**, `spectre-cli` 46 passed, `spectre-game` 15 + 1 passed. 22 Skips = Real-Frame-Tests.
`.spectre` nach dem Lauf unverändert (keine neueren Dateien), kein `.spectre` im Worktree.

## T75 — Tap-/Key-Batching

- Neu in `afk_claim_vision`: `tap_seq([(x, y, wait), …], tolerate=True, dry=False)` und
  `key_seq([(code, wait), …])` → **ein** `adb shell` (`input tap …; sleep …; …`), Timeout
  `sum(waits) + 15`. `tolerate=False` → `RuntimeError` bei rc ≠ 0; `dry=True` liefert die Zeile.
- Umgestellt (nur blinde Paare ohne Screen-Check dazwischen, alle `tolerate=False` = gleiches
  Fehlerverhalten wie `tap`): `afk_normalize` back2, `claim_round` GROUND → AFK_PROGRESS (2×),
  stage_push still-BATTLE-Retry BACK → CARD_CLOSE, R12-Recovery BACK → (960,540).
- **Bewusst nicht** umgestellt: der hero_level-Zwei-Tap (live-verifizierter Geld-Pfad).
- `LIVE:` toybox-`sleep` mit Bruchteilen (0.5) prüfen — sonst ganzzahlige Waits.
- Bestehende Tests unverändert grün; FakeDevice zeichnet `tap_seq`/`key_seq` als Taps auf.

## T76 — Shot-/OCR-Fast-Paths

- a) `v.shot`: zuerst `exec-out screencap` **raw** → `Image.frombytes` (Header 12/16 B, Format 1,
  Länge = w·h·4 + Header geprüft), PNG `compress_level=1`; jede Abweichung → unveränderter PNG-Pfad.
- b) `v.ocr_region(name, box)`: Crop → `TMP/{name}_r.png` → `ocr_png`; Fehler → `[]`.
  `afk_hero_level.slot_level` nutzt es (gleiche Box, gleicher Regex).
- c) Weitere Full-OCR-Checks **nicht** umgestellt: ohne aktuelle Frames sind keine Boxen messbar —
  Kandidaten (Hall-Check, Detail-Check) als Folge-Task, erst nach Frame-Messung.
- `LIVE:` Header-Länge der BlueStacks-Android-Version + gemessener Zeitgewinn pro Shot.

## T77 — `spectre read-batch` (Rust)

- `spectre read-batch --offsets <game|yaml> --pid P --base 0x… [--adb] [--json]`: **ein** Reader
  für alle Felder, Ausgabe `[{name, address, value, fmt, valid, note?}]`.
- Validierung identisch zu `spectre offsets` (`spectre_game::validate`; Pfadauflösung jetzt
  gemeinsam: `resolve_offsets_path`). Validierungsfehler oder Lesefehler → nur dieser Eintrag
  `valid: false` + `note` (`read failed: …` / `short read` / `unknown field type …`), Rest läuft.
- Adresse = `base + base_offset + offset` (für die bestehende afk-journey.yaml mit absoluten
  base_offsets: `--base 0x0`).
- Tests: Plan/Adressen/Typen, Decode aller Typen, ein kaputter Eintrag killt den Rest nicht,
  JSON-Form, Validierungsfehler → invalid. Offline-Smoke mit toter PID: jede Zeile
  `read failed: OpenProcess failed …`, rc 0.
- **Hermes:** Release-Binary neu bauen (`cargo +stable-x86_64-pc-windows-gnu build --release`),
  sonst fehlt `read-batch` (T78 fällt dann automatisch zurück, s. u.).

## T78 — `afk_memory.py`

- `snapshot(pid, base, yaml)` → `spectre read-batch --json` per Subprocess, Timeout 30 s,
  Cache 1.5 s pro (pid, base, YAML-Inhalt); Fehler → `{}` und werden **nicht** gecacht.
- `power(pid, base)` dupliziert den Drift-Guard **nicht**: er ruft `v.memory_preflight`; dessen
  zwei Reads (Wert + Map-Entry-Shape) sind jetzt injizierbar (Defaults unverändert → alle
  bestehenden Guard-Tests unverändert grün) und kommen aus **einem** read-batch des 16-Byte-Slots
  (`lo`/`hi`/`ptr`). Ohne read-batch → klassische Dumps (Verhalten wie vorher). Die doppelt
  geschriebene Drift-Toleranz ist jetzt `v.drift_window()` (eine Regel für Preflight + Relocation).
- Paritätstest: 4 Guard-Fälle (u32-Entry ok, Drift → disabled, u64 ok, u64-Alias eines
  Map-Entry → disabled) liefern mit read-batch exakt das Ergebnis des Dump-Pfads.
- Erster Consumer: `afk_dailies` (Power-Gate). `afk-daily-gift`, `afk_dream_realm`,
  `afk_stage_push`, `afk_claim_vision` bleiben bis zum LIVE-Check auf `v.memory_preflight`.
- CLI: `python scripts/afk_memory.py --show --pid P --base 0x… [--offsets yaml]`.

## T79 — `mem_probe.py`

- `spectre hot --json` je Wert (≥ 2 Werte, Änderung im Spiel dazwischen: Enter oder
  `--no-prompt --wait N`) → Schnittmenge der Adressen → offsets.yaml-Feld-Vorschlag auf stdout
  mit Kandidaten pro Scan, Confidence (high = 1 Kandidat; medium ≤ 3; low sonst) und Alternativen.
- Bounded: Timeout je Scan, `--limit`; ein Scan, der das Limit trifft, ist `TRUNCATED` → max. low.
- Log-only: keine Memory-Writes, keine Datei-Writes. Exit 0 Vorschlag / 3 kein Kandidat /
  2 spectre-Fehler / 1 falsche Argumente (gleiche Werte werden abgelehnt).

## T80 — Speed-Profil + Timing-Härtung

- a) `scripts/speed_profile.py on|off|status [--scale 1.5|2|4] [--repeat-ms N] [--server-bin …]
  [--port N] [--dry-run]`: frida-tools fehlt → rc 3 (ohne Device-Zugriff); Root-Check
  (`su -c id`), frida-server vorhanden/push + `chmod`, Start auf eigenem Port
  (`-D -l 127.0.0.1:PORT`) + `adb forward` → rc 4 bei Problemen; Game-PID via `frida-ps`;
  Kommando über `attach.py build()` mit `--params` (OFF = scale 1, status = log-only Probe);
  `frida -q`, Timeout 60 s → rc 5. `attach.py` bekam optional `--host` (Default unverändert
  `-D serial`; bestehende Kit-Tests unverändert grün).
- b) `afk_hero_level.daily_charge`: nach dem Hand-Tap Poll bis `is_detail` (16 × 0.5 s ≈ 8 s)
  statt fixer 3.0 s; pre-Level None **oder ≠ Scan-Wert der Hand** (der live gesehene Stale-Read
  der Vorgänger-Hand, 85) → bis 2 Re-Reads; post-Level None → bis 2 Re-Reads. Keine
  Koordinaten geändert. `scan_hands`/`level_hand` unverändert (Scan hat seinen T72-Retry).
- Bestehender Test angepasst (bewusste Verhaltensänderung): „Detail erscheint nie" scriptet jetzt
  die Frames des begrenzten Polls (`6 + 2 × DETAIL_POLLS` statt 8).

## LIVE-Check-Liste (Hermes)

1. Release-Binary neu bauen; `spectre read-batch --offsets <slot.yaml> --pid P --base B --adb --json`
   gegen `spectre dump` des Power-Slots vergleichen; dann `afk_memory.py --show` → `team_power: ok …`.
2. `afk_dailies` einmal live: Log `preflight team_power = …` wie bisher, Laufzeit des Preflights.
3. T75: ein Normalize-/Claim-Lauf; prüfen, dass `sleep 0.5` im Batch wirkt (sonst Waits runden).
4. T76: `shot`-Zeit raw vs. PNG messen; ein Frame mit Raw-Pfad gegen PNG-Pfad (identische Pixel).
5. T79: `mem_probe.py` am Gold-Slot (Claim als Wertänderung) → Vorschlag + Action-Diff.
6. T80a: frida-tools + passender frida-server (`frida --version`), Root für Pie64, Port 27142 /
   `-l`-Flag der Server-Version, `-q`/`--eternalize`; zuerst `status`, dann `on --scale 1.5`,
   Battle-Wallzeit gegen T61-Baseline, `off`.
7. T80b: nächster Daily-Charge — Log zeigt `hl_daily_pre0_w*`/`_rr*` nur bei Bedarf; pre-Wert = Scan-Wert.

## Offene Punkte

- T76 c: weitere Region-Boxen erst nach Frame-Messung.
- T78: übrige 4 Preflight-Consumer nach LIVE-OK auf `afk_memory.power()` umstellen.
- T80b: Stale-Read-Erkennung stützt sich auf den Scan-Wert; ohne Scan (Fallback-Hand) greift nur
  der None-Re-Read.
