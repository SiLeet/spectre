# Claude Wave-4 Run (D1–D4) — Sammelbericht (2026-11-03)

Auftrag: D1 → D4 laut Wave-4-Prompt, je ein Branch, offline, kein push, keine neuen
Dependencies. Ergebnis: **alle vier Tasks umgesetzt, nichts blockiert.** Kein adb/BlueStacks
live; `.spectre` nicht angefasst.

## Git

Worktree `C:\Users\Sigi\spectre-w4` (ohne `.spectre`-Junction), alle Branches ab `main` (`7a78078`).

| Task | Branch | Commits | Suite auf dem Branch |
|---|---|---|---|
| D1 | `feature/T66-zombie-recovery` | `8ad681d` | `Ran 202 tests … OK (skipped=22)` |
| D2 | `feature/T67-daily-leveling` | `a61deed` | `Ran 203 tests … OK (skipped=22)` |
| D3 | `feature/T68-device-ensure-wiring` | `24da02c` | `Ran 197 tests … OK (skipped=22)` |
| D4 | `feature/T69-duras-trials` | `24c0aa3`, `7e9f87e` (+ dieser Bericht) | `Ran 201 tests … OK (skipped=22)` |

- **Probe-Merge** aller vier Branches auf `main` (detached, nichts gepusht/verändert):
  konfliktfrei, Gesamtsuite **`Ran 230 tests … OK (skipped=22)`** (191 + 11 + 12 + 6 + 10).
  Dafür wurden die D4-Testframes ans Ende von `_SPEC` verschoben (`7e9f87e`, sonst Konflikt mit D1).
- **Namenskollision:** `feature/T66-tray-icon` (Tray-Icon, früher heute) existiert bereits;
  D1 heißt daher `feature/T66-zombie-recovery`. Ggf. Tray auf eine andere T-Nummer umbuchen.
- 22 Skips = Real-Frame-Tests (`.spectre` leer, R13).

## D1 / T66 — Zombie-Recovery

Referenz (Nachtlog 03.11.): arena „could not reach a fight (STUCK)", steps 0=SELECT, 1..5=RESULT ·
dream „could not reach the world view" nach normalize 0..4 POPUP · stage „initial battle screen
state: BATTLE" → „not on a battle screen".

- **a) `afk_normalize`:** 5 POPUP-Reads in Folge → `escape_ladder()`: Login-Resolver → BACK →
  Leerraum (300,250) → BACK×2; nach jedem Schritt `classify`; Confirm-/Kauf-Dialog wird gecancelt;
  Ground-Tap entfällt bei Kauf-Wörtern im OCR; 2 Zyklen. Marker: `ESCAPE: recovered …` /
  `ESCAPE: gave up after 2 cycle(s) …`. UNKNOWN-Serien lösen die Leiter nicht aus.
- **b) `afk_arena.advance_to_fight`:** 2 Steps mit gleichem State + gleicher Screen-Signatur →
  1× Card-Dismiss (480,300) + neuer Select-Versuch; zweite Stagnation → `STUCK` sofort.
- **c) `afk_stage_push`:** Start-„BATTLE", das nicht animiert (2 Shots im 3-s-Abstand,
  mittlere Grau-Differenz < 3) → 1× BACK + Kartenmitte (R12-Baustein), neu klassifizieren;
  weiter statisch → Exit 1 statt minutenlangem Warten.
- **d) `afk_dream_realm.run`:** Welt nicht erreichbar → Escape-Leiter (2 Zyklen) + ein weiterer
  `reach_world`, erst dann Abbruch.
- Schwellen mit `LIVE:` (POPUP_STREAK 5, ESCAPE_CYCLES 2, STAGNANT_STEPS 2, STAGNANT_DIST 40,
  STATIC_DIFF 3.0). Geänderte Test-Erwartung: F5-Arena-Test (der Stuck-Pfad endet jetzt mit der
  Zombie-Recovery, Exit 1 unverändert).
- Tests: `test_zombie_recovery.py` (11).

## D2 / T67 — Tages-Leveling (Regel T33: genau 1 Charge/Tag)

- `afk_hero_level.py --level`: alle 5 Hände scannen (antippen, Level-OCR, zurück, Hall-Re-Verify),
  niedrigste wählen; Scan ohne Ergebnis → letzte bekannte Hand aus `.spectre/level-last-hand.txt`
  (`LIVE:`-Meldung). OCR-Gate: Level lesbar + „have/need"-Kostenzeilen (K/M-fähig, kleine Zähler wie
  `3/4`/`0/1` ignoriert). **Genau ein** Tap auf `LEVEL_X1` (`LIVE:`), Kauf-Dialog → Cancel,
  Read-back muss +1 sein. Exit 0 geladen / 4 heute übersprungen (zu wenig, keine Wirkung, Dialog) /
  1 Fehler. Nur Gold/EXP, nie Diamanten.
- `afk-bot-watch.sh` (Daily, `--scheduled`): weiche Phase nach Dream Realm, vor dem Stage-Push,
  einmal pro Tag (`level-last.txt` bei rc 0/4); andere rc nur Log-Zeile, Daily-Exit-Code unverändert.
  Schalter `AFK_DAILY_LEVEL=0`. Aufruf `--level` (= der „Schalter --level" aus dem Brief).
- Hinweis: `scripts/_level_hands.py` existiert nicht mehr (in T48 gelöscht); dessen Scan
  („Hand tippen, Level lesen, zurück") ist jetzt `scan_hands()`.
- Tests: `test_daily_leveling.py` (8) + 4 Wrapper-Fälle in `test_afk_daily_exit_code.py`.

## D3 / T68 — device-ensure verdrahtet

- `afk-bot-watch.sh` + `afk-night.sh`: Schritt 0 **nur**, wenn `spectre find igame` kein Spiel findet:
  einmal `timeout ${AFK_ENSURE_TIMEOUT:-600} bash scripts/device-ensure.sh …`, danach erneute pid-Suche.
  Idle unverändert: geplante Läufe/Night geben `--min-idle` weiter (rc 4 = „skipped (idle gate)"),
  manuelle watch-Läufe `--force`. Jeder Fehler = `WARN`-Zeile; danach entscheidet der bisherige Check
  („game process not found", Exit 2). Erreichbares Spiel → kein ensure (kein Doppelstart, keine Taps).
  Schalter `AFK_DEVICE_ENSURE=0`. `device-ensure.sh` (inkl. cygpath-Fix) unverändert.
- Tests: `test_device_ensure_wiring.py` (6: ok / fail / skipped / Spiel da / aus / manuell --force,
  beide Wrapper); bestehende Night-/Daily-Exit-Code-Integrationen grün.

## D4 / T69 — Dura's Trials v1

- Neues `scripts/afk_duras.py`: Welt → Battle Modes → Dura's-Karte (OCR-Gate „dura"); höchster Floor
  per OCR „Floor N", gecleart = „Sweep" sichtbar, Token „N/6". Nicht gecleart → genau 1 Kampf
  (Challenge → Battle → Ergebniskarte via `classify_battle`), Niederlage = Token-Refund → max. 3
  Versuche; danach Sweep des höchsten Floors, bis der Zähler 0 zeigt (jeder Sweep muss genau −1
  ergeben). Confirm-/Kauf-Dialoge immer Cancel; Sweep nur mit „Sweep" auf dem Screen (Sweep- und
  Challenge-Knopf teilen dieselbe Stelle). Marker `.spectre/duras-last.txt` nur bei sauberem Ende.
  Exit 0 / 1 / 4 (First Clear nicht geschafft, Token bleiben) / 5. `--dry-run` liest nur.
- Alle Koordinaten/OCR-Wörter als Konstanten oben mit `LIVE:` (`DURAS_CARD`, `CHALLENGE_BTN`,
  `FIGHT_BTN`, `SWEEP_BTN`, `RESULT_CLOSE`, `DURAS_WORD`, `SWEEP_WORD`, `MAX_FIGHTS`).
  **Nicht** in watch/night eingehängt.
- Tests: `test_duras.py` (10).

## LIVE-Check-Liste für Hermes

1. **D1 normalize:** Zombie-Popup provozieren → Log `normalize: 5x POPUP in a row — escape ladder`,
   dann `ESCAPE: recovered …`; prüfen, dass der Ground-Tap (300,250) auf dem Popup harmlos ist.
2. **D1 arena:** Gegner-Detailkarte (N2) → `zombie: 2 steps without progress -> card dismiss +
   re-select`; schließt (480,300) die Karte wirklich? Sonst bleibt N2 (Challenge! auf der Karte) offen.
3. **D1 stage:** Start auf einem stehenden „BATTLE"-Screen → `still screen … one dismiss retry`;
   STATIC_DIFF 3.0 gegen echte Kampf-/Standbilder prüfen.
4. **D1 dream:** Welt-Fehlschlag → Leiter → Dream läuft weiter.
5. **D2 Leveling:** `afk_hero_level.py --level` einmal manuell: Scan-Log aller 5 Hände, gewählte
   Hand = niedrigste, **genau +1 Level**, Gold/EXP sinken, keine Diamanten. Prüfen, ob `LEVEL_X1`
   (1460,1065) wirklich +1 (nicht +10) gibt; Kostenzeilen-OCR → `resources_ok` (True/False/None).
6. **D3:** BlueStacks/Spiel schließen → geplanter Lauf startet ensure (Log `game not reachable —
   device-ensure (--min-idle 180)` → `device-ensure ok`); bei PC-Nutzung `skipped (idle gate)`.
7. **D4 Dura's:** `afk_duras.py --dry-run` → Karte gefunden? Floor/Token korrekt gelesen?
   Dann Koordinaten `DURAS_CARD/CHALLENGE_BTN/SWEEP_BTN/FIGHT_BTN/RESULT_CLOSE` eintragen, ein
   echter Lauf; prüfen, ob ein Sweep einen Bestätigungsdialog zeigt (der wird aktuell gecancelt →
   dann `SWEEP_WORD`/Flow anpassen).

## Offene Punkte

- Alle neuen Schwellen/Koordinaten sind ungeprüft (`LIVE:`), besonders `LEVEL_X1` (x1 vs. x10)
  und die komplette Dura's-Navigation.
- N2 (Arena-Gegnerkarte mit „Challenge!") ist nur abgefedert, nicht gelöst.
- Branch-Nummer T66 doppelt belegt (Tray + Zombie-Recovery).
