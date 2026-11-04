# Claude Wave 6 — Run-Report

## T82 — Region-OCR-Rollout (F2)

**Umgestellt** (`scripts/afk_hero_level.py`, Helper `hall_lines`): Hall-Gate in `main` (`hl_entry`)
und die drei `is_hall`-Prüfungen in `in_hall` (`tag`, `{tag}_b`, `{tag}_reenter`).
Muster: zuerst `v.ocr_region(name, HALL_BOX)`; ohne „Resonance Level“-Zeile folgt die bisherige
Voll-OCR. Negative (inkl. `is_detail`) verhalten sich daher identisch.

- `HALL_BOX = (740, 315, 1180, 405)`, gemessen an `.spectre/shots-69252/hl_entry.png`
  (Text ca. x 862..1110, y 345..370). LIVE: auf dem Gerät noch nicht gelaufen.
- Verifiziert auf 21 echten `hl_*`-Frames: 7 Hall-Treffer (hl_entry, hl_daily_hall0/1,
  hl_scan_hall_850/970/1090/1210), 14 Nicht-Hall-Frames (Detail hl_scan_*, hl_daily_pre*/post1,
  Quest-Panel shots-47096/hl_entry*). Region und Voll-OCR liefern überall dasselbe Urteil.

**Messnotiz** (WinRT über PowerShell, Median aus 5 Läufen, Frames als Kopie im Scratch):

| Frame | Voll-OCR | Region | hall_lines |
|---|---|---|---|
| hl_entry (Treffer) | 0,73 s | 0,57 s | 0,58 s |
| hl_scan_970 (Miss, Detail) | 0,53 s | 0,61 s | 1,12 s |

Ersparnis pro positivem Hall-Check etwa 0,15–0,3 s (rund 20–30 %); der Start von
PowerShell/WinRT dominiert. Ein negativer Check kostet etwa +0,6 s (Region plus Fallback).
Negative sind selten (Detail noch offen / Stadt). Die Werte schwanken je nach Last
(Reviewer haben 0,9 vs. 0,68 s bzw. 2,05 vs. 1,11 s gemessen); die Richtung ist überall gleich.

**Nicht umgestellt** (kein echter positiver Frame unter `.spectre/shots-*`, oder kein Gate):

- `afk_claim_vision.resolve_startup_popup` (Login-Popup): kein Popup-Frame, keine `claim_*`-Frames.
  „Daily Rewards“ steht nur in der Arena-Lobby.
- `afk_stage_push` `is_auto_complete` (:351/:357/:491/:633): kein Frame mit „Auto Battle Complete“.
- `afk_stage_push.wall_report` (:208): kein Gate; braucht die vollen Zeilen für den JSONL-Bericht.
- Hero-Detail-Parser (`read_level`, `resources_ok`, „within 10“): brauchen die vollen Zeilen als Daten.
- `afk_device_ready.is_title`, `afk_normalize` :54, `afk_duras.read`: keine passenden Frames.
- `afk_dream_realm.parse_chances` (:575): positive Frames gibt es nur in `.spectre/trash/`
  (`dr_f*_chances.png`) und `.spectre/livecheck/now.png`, also außerhalb des Scopes `shots-*`.
  Daher unverändert.

Login-Popup und „Auto Battle Complete“ brauchen einen Live-Capture (Hermes). Danach lässt sich
dasselbe Muster wie bei `hall_lines` anwenden.
