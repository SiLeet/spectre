# Claude Code — Spectre Wave 4.5 (E1–E5: Nachzügler & Test-Härtung)

> Paste-fertiger Prompt. Stand: 2026-11-03 abends. Basis: aktueller main (Suite grün, ~252 Tests).
> Quellen: Wave-4-Reviewer-Befund (R19), Tap-Lock-Follow-up des Queue-Driver, Live-Lauf-Erkenntnisse.

---

```
WORKSPACE: C:\Users\Sigi\spectre

STAND: Wave 4 ist gemergt, reviewt (Reviewer: kein FAIL) und die Leveling-Kette wurde
heute live end-to-end verifiziert (two-tap preview-confirm, slot-level read-back,
blocked-skip). Der Queue-Driver hat u. a. den Tap-Lock (_bot_lock.py, exit 7) in
4 Einstiegspunkte verdrahtet und afk_hero_level.py BEWUSST ausgelassen (Follow-up).
Wave 4.5 schließt die review-notierten Test-Lücken + drei kleine Nachzügler.
KEIN Verhalten der live-verifizierten Pfade ändern, nur absichern/ergänzen.

LIES ZUERST (komplett):
  1. docs/claude-wave-2-plan.md §0 — Spielregeln + Fallback-Tabelle (gelten 1:1).
  2. TODOS.md, Abschnitt "Race-Fund-Fix (a): Tap-Lock" — Semantik + Wrapper-Bypass.
  3. Die betroffenen Skripte + scripts/tests/fake_vision.py + test_bot_lock.py.

AUFTRAG: E1 → E2 → E3 → E4 → E5. Je 1 Branch (feature/T70-… bis feature/T74-…),
KEIN push, keine neuen Dependencies, Tests im fake_vision-Stil, `.spectre` read-only.

E1/T70 — REVIEW-TESTLÜCKEN SCHLIESSEN (nur Tests, Quelle: Reviewer-Mutationen):
  a) afk_dream_realm.py:516 — die 2-Zyklen-Grenze der world-Recovery pinnt kein
     Test: Szenario mit 2 vollständigen Zyklen (frames), assert Exit 1 + 'gave up'.
  b) afk_arena.py:115-117 — der In-Chain-Dialog-Return 'DIALOG' ist ungetestet:
     Dialog-Dialog taucht in der fight chain (arena_f*_step0) auf → genau EIN
     'STOP: purchase dialog during the fight chain'-Log + Rückgabe 'DIALOG'.
  c) afk-bot-watch.sh:73 + afk-night.sh:46 — ensure-timeout nicht gepinnt:
     Hang-Stub (ensure antwortet nie) → assert, dass der Timeout-Wert (600) als
     Argument übergeben wird (nicht nur 'timeout' ohne Wert).
  d) afk_duras.py:149-153 (Sweep nur wenn 'Sweep' im OCR → sonst sauberer Stop),
     :110-111 (Challenge-Dialog → Return), :189-191 (No-Token-Pfad) — je 1 Test.
  e) afk-bot-watch.sh:261 — Once-per-Day-Gate nicht über zwei Läufe getestet:
     Wrapper-Szenario: zweiter Lauf im selben Temp-Root/Tag → genau 1 Leveling-Aufruf.
  Keine Produktionslogik ändern — nur falls die Tests echte Lücken aufdecken.

E2/T71 — afk_hero_level.py IN DEN TAP-LOCK VERDRAHTEN (Driver-Follow-up):
  Muster exakt wie die 4 bereits verdrahteten Scripts (siehe TODOS + test_bot_lock.py):
  acquire() in main() VOR dem ersten Tap; Fresh-Lock → Exit 7 + describe()-Zeile;
  release_at_exit() (PID-guarded). AFK_BOT_LOCK_HELD-Bypass gilt automatisch
  (Wrapper exportieren die Variable — nichts tun). ACHTUNG: die heutigen Live-Fixes
  (two-tap, slot_level-Crop, blocked-skip) NICHT anfassen. test_bot_lock.py um
  Wiring-Source-Check + Verhaltenstest fürs 5. Script erweitern. Test-Suite der
  Leveling-Tests muss unverändert grün bleiben. docs/agent-workflow.md: den
  Caveat-Absatz ("bewusst NICHT verdrahtet") auf den neuen Stand bringen.

E3/T72 — HAND-SCAN-ROBUSTHEIT (aus dem Live-Lauf: einzelne Hände lesen sporadisch None):
  scan_hands(): wenn ein Level nicht lesbar ist → genau 1 Retry (kurz warten,
  erneut snap+lesen), bounded + geloggt. HAND_XS präzisieren: gemessene
  Kartenmitten ~ [730, 850, 970, 1090, 1210] (Vision-Messung 2026-11-03, als
  LIVE-Kommentar; aktuelle Werte weichen bis ~20 px ab) — HANDS_Y=460 blieb gültig.
  Tests: fake-Szenario 'erst None, dann Wert' (Retry greift), 'dauerhaft None'
  (sauber übersprungen, kein Absturz).

E4/T73 — MCP SEARCH-REFINE-TOOLS (YAGNI-optional, klein):
  spectre-mcp (crate existiert, ist gebaut + connected) um 1-2 Tools für
  `search --continue`/Refine erweitern (Semantik aus spectre-cli übernehmen).
  Klein halten: nur wenn im bestehenden Tool-Muster ohne Umbau machbar; sonst
  1 Zeile Report warum nicht. Tests analog bestehender spectre-mcp-Tests.

E5/T74 — LOG-ROTATION (Check zuerst, dann bauen):
  Prüfe, ob .spectre/logs eine Rotation hat (vermutlich nicht). Wenn nicht:
  simple Funktion — afk-bot-*.log über ~5 MB → <name>.log.1 (EINE Generation,
  LIVE-Marker fürs Limit), Aufruf am Anfang von afk-bot-watch.sh + afk-night.sh,
  pure Funktion + Tests. Wenn doch vorhanden: 1 Zeile Report.

DoD je Task: Gesamtsuite grün (~252+, Basis aktueller main), 1 Task = 1 Commit,
kurzer deutscher Report je Task, Sammelbericht docs/reports/claude-wave-45-run.md.
SafeGuard-Blockade → Fallback-Tabelle §0.

NICHT in dieser Welle (brauchen erst Live-Recon durch Hermes): T29 (Legend Trial /
Labyrinth / Honor-Duel-Einstieg), T45h (Friend Favors / Homestead-Assists),
Dura's-Koordinaten-Feinschliff nach Live-Test.
```
