# Claude Code — Spectre Wave-2 FOLLOW-UP (A8 / Runtime-Fixes)

> Paste-fertiger Prompt für den A8-Batch. Aktualisiert: 2026-11-03.
> Stand: Wave A1–A7c ist gemergt (main, 107 Tests grün). Es fehlt nur A8.

---

```
WORKSPACE: C:\Users\Sigi\spectre

STAND: Wave A1–A7c ist KOMPLETT in `main` gemergt und reviewed (kein FAIL; 107
Tests grün via `python -m unittest discover -s scripts/tests`). Dein Job ist der
Folge-Batch A8 — die Runtime-Fixes für afk_stage_push.py + afk_dream_realm.py.

LIES ZUERST (komplett):
  1. docs/claude-wave-2-plan.md §0 (Spielregeln + Fallback-Tabelle) und
     §A8 (a/b/c-Liste) — die Briefs.
  2. docs/reviews/2026-11-03-runtime-review.md — der Report MIT Messwerten
     und Frame-Beweisen (Quelle für Koordinaten/Profile).
  3. TODOS.md Eintrag R14 — die offene Liste (nur lesen, nicht editieren).
  4. scripts/tests/test_review_fixes.py + scripts/tests/fake_vision.py —
     Teststil, den du für deine Fixes übernimmst.

AUFTRAG: A8a → A8b → A8c komplett, 1 Finding = 1 Commit, Finding-/Item-Nr
(z.B. "A8a-1", "doc2 F3") in die Commit-Message. Branch: feature/T60-runtime-fixes.
afk_dream_realm.py ist von Wave A UNBERÜHRT — alle seine Items sind offen.

KURZFASSUNG DER ITEMS (Details + Zeilennummern im Report; nichts erfinden):
  A8a-1  dream start_fight: schwarze Übergangs-Frames nicht als "Kampf läuft"
         akzeptieren; positiver Fight-Marker (aus dem Report: (960,1040) weder
         weiß noch grün; lum((1280,1010)) < 120) — dunkle Frames weiter pollen.
  A8a-2  dream wait_for_fight_end: Ready-Re-Arm (>=3 is_ready-Frames ohne
         Fight-Marker → einmal PREP/BOSS re-tappen, weiter pollen).
  A8b    stage_push LAUNCHER/LOADING-Kreuzklassifikation (Gate verschärfen bzw.
         nach BATTLE prüfen; LOADING = "keine Info" im Strike-Counting; LOADING
         in die wait-Sets); dream _dim_probes vs. Transitions (Debounce/lum<40);
         back_to_ready Unknown-Toleranz (4→~20 bzw. End-Polling); 2x-Tap erst
         auf Fight-Marker; Chance-Bookkeeping ("Chances: N/7" per OCR, Fight nur
         bei Marker zählen, bei leerem Pool sauber stoppen); dream_realm ruft
         den Prune auf (v.prune_shot_dirs); stale-RESULT-Phantom-Win;
         PREP-Debounce nur bei "st2 immer noch PREP" als Wand werten;
         einheitliches try_shot (Backoff, kein FATAL mid-chain, adb-rc nach ~5
         Fails); Popup-Fallback (OCR 'Level/Perk/Tap to close' → (960,540),
         Strike-Reset).
  A8c    reach_world: bei UNKNOWN erst pollen statt sofort exit 1; HERO_PROBE-
         Marge (171 vs 170 → >=180 oder Punkt verschieben); toten doppelten
         POPUP-Check löschen; Summary-Close primär (960,540) statt (960,1000);
         parse_power aufwärts scannen + Anchor ^Battle; wall_report: erste
         Fehlermeldung erhalten (log_error getrennt) + OCR-Erstaufruf-Warmup (~30 s).

WICHTIGER KONTEXT:
  - .spectre wurde beim Worktree-Teardown geleert (TODOS R13) → Real-Frame-
    Tests skippen aktuell (checked=0 ist NORMAL). Schreibe deine Tests nach dem
    fake_vision-Muster (synthetische Frames) + optional Real-Frame-Asserts, die
    bei fehlenden Frames skippen. Kalibrier-Werte aus dem Report verwenden.
  - NEVER live: kein adb/BlueStacks. Gerät gehört Hermes.

REGELN (unverändert scharf):
  - KEIN git push, KEIN rebase/reset. Commit(s) lokal auf dem Branch.
  - DoD: volle Suite grün — `python -m unittest discover -s scripts/tests`
    (Baseline 107 Tests; deine neuen kommen dazu, alle müssen grün sein).
  - Keine neuen Dependencies (stdlib + PIL). TODOS.md nicht editieren.
  - Rust/cargo nur wenn nötig, dann `cargo +stable-x86_64-pc-windows-gnu`.
  - Append-only wo möglich; keine Big-Bang-Refactors.

WENN DU BLOCKST: Fallback-Tabelle §0; sonst Task als BLOCKIERT dokumentieren und
weiter. Nicht auf Antwort warten.

ENDE: Abschlussbericht als Datei `docs/reports/claude-wave-2-a8-run.md` + Antwort:
pro Item Status (FIXED/BLOCKIERT + Commit), geänderte Dateien, ECHTE Testausgabe,
offene Punkte, Live-Check-Liste für Hermes (was er auf dem echten Screen
gegenprüfen muss).
```

---

## Hinweise für Sergej (nicht mitkopieren)

- Das ist der **A8-Folge-Batch** (die zwei HIGH-Findings + MED/LOW des zweiten
  Reviews, die beim Wave-2-Lauf außerhalb des Auftrags lagen).
- Danach ist Code-seitig alles abgearbeitet; es bleiben nur noch die
  **Live-Gegenproben** (F1/F7 + A8-Gates am echten Screen) und **Wave B** (B1–B6,
  brauchen meinen Live-Recon vorab).
- Nach dem Lauf wieder: "Claude ist durch" → ich reviewve, merge, verifiziere live.
