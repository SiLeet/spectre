# Claude Code — Spectre Wave 4 (D1–D4: Härtung, Tagesbetrieb, Dura's v1)

> Paste-fertiger Prompt. Stand: 2026-11-03 13:1x. Basis: main `f1211ab` (Gesamtsuite 191+ grün).
> Auslöser: ECHTER Nachtlauf — Zombie-Screens; sowie freigegebene T33-Regel.

---

```
WORKSPACE: C:\Users\Sigi\spectre

STAND: Wave 2 + 3 sind komplett in main gemergt (CI grün). Wave 4 schließt
Lücken aus dem echten Daily-Lauf vom 03.11. (Zombie-Screens, aus denen sich der
Bot nicht selbst befreit), setzt die freigegebene Leveling-Regel um (exakt
1 Charge/Tag), verdrahtet den fertigen Emulator-Selbststart (C5) und baut den
ersten Coverage-Modus: Dura's Trials (Mechanik research-verifiziert).

LIES ZUERST (komplett):
  1. docs/claude-wave-2-plan.md §0 — Spielregeln + Fallback-Tabelle (gelten 1:1).
  2. docs/claude-wave-3-plan.md — §3 (W3-1/W3-4 Arbeitspakete), §6a (Research-Ergebnisse).
  3. Die betroffenen Skripte unten + scripts/tests/fake_vision.py.

AUFTRAG: D1 → D2 → D3 → D4. Je 1 Branch (feature/T66-… bis feature/T69-…),
mindestens 1 Commit pro Task, KEIN push. Keine neuen Dependencies.
`.spectre` bleibt read-only (außer in Live-Kommentaren). Alles Unverifizierte
bekommt einen konsistenten `LIVE:`-Marker (Muster wie bisher).

D1/T66 — ZOMBIE-RECOVERY (Basis: echter Nachtlog 2026-11-03, siehe unten):
  a) scripts/afk_normalize.py: Wenn 5× in Folge „POPUP" erkannt wird (heute:
     Aufgabe ohne Wirkung), neue bounded Escape-Leiter:
     afk_claim_vision.resolve_startup_popup() → BACK → Leerraum (300,250) → BACK×2,
     Schritte OCR-gated wo möglich, max. Zyklen begrenzt, jeder Schritt geloggt,
     Ende mit klar benanntem Marker (recovered/aufgegeben).
  b) scripts/afk_arena.py: Opponent-Select-Zombie („select-opponent signature"
     erkannt, danach 5 Steps ohne Fortschritt, nie Challenge erreicht) →
     nach 2 stagnierenden Steps: 1× Card-Dismiss (480,300) + erneuter
     SELECT-Versuch; danach bounded Abbruch (kein Endlos-Loop).
  c) scripts/afk_stage_push.py: Start-Zustand „BATTLE", der laut eigener Prüfung
     keiner ist → einmaliger Dismiss-Retry (die A8-R1/R2-Bausteine wiederverwenden)
     bevor abgebrochen/neu getippt wird.
  d) scripts/afk_dream_realm.py: „could not reach the world view" → bounded
     Escapes wie (a) statt Sofort-Abbruch (max. 2 Zyklen), dann erst Abbruch.
  LOG-AUSZUG (IST-Zustand, als Referenz einbetten):
    arena: "could not reach a fight (STUCK)"; steps 0=SELECT, 1..5=RESULT
    dream: "could not reach the world view"; normalize 0..4: POPUP
    stage: "initial battle screen state: BATTLE" → "not on a battle screen"
  TESTS: je Leiter ein fake_vision-Szenario (POPUP→Welt, Select→Challenge-Wechsel,
  Fehlzustand→Dismiss, world-fail→recovered). Schwellen mit LIVE:-Marker.

D2/T67 — TAGES-LEVELING (T33-Regel FREIGEGEBEN: exakt 1 Charge/Tag):
  scripts/afk_hero_level.py in den Daily-Lauf (scripts/afk-bot-watch.sh, nach den
  Claims, vor stage_push) einhängen; Schalter --level; im Daily-Task aktiv.
  Regel: GENAU EINE Level-Charge (x1-Button) pro Tag; Ziel: die niedrigste Hand
  des Main-Teams (Hand-Scan-Logik aus scripts/_level_hands.py nutzen; wenn Scan
  scheitert → letzte bekannte Hand + LIVE:-Marker). Nur Gold+EXP (nie Diamanten).
  Vorher OCR-Gate (Level + Ressourcen), nachher read-back (Level+1). Weich:
  Fehler/„resources out" überspringen die Phase, ohne die Kette zu killen.
  Das Skript behandelt „resources out" + „x10 wirkungslos" schon — bau darauf auf.
  TESTS: fake_vision (Gate greift, exakt 1 Charge, weich bei Fehler).

D3/T68 — DEVICE-ENSURE VERDRAHTEN (C5 ist fertig + live getestet):
  scripts/afk-bot-watch.sh + scripts/afk-night.sh: als Schritt 0, VOR dem
  idle-gate, bounded `scripts/device-ensure.sh` aufrufen — aber nur, wenn
  Emulator/Spiel nicht erreichbar (ensure prüft das selbst; kein Doppelstart).
  ensure-Fehler = Warnung + normaler Ablauf (kein harter Abbruch). Idle-Skip-
  Verhalten der Läufe bleibt unverändert; Phasen starten weiterhin nur bei
  erreichbarer Welt. Ein ensure-Lauf darf NIE Ressourcen im Spiel tippen außer
  Titel/Popup (bestehende Gates). Der aktuelle Live-Fix in device-ensure.sh
  (cygpath) ist in main — nicht überschreiben.
  TESTS: bestehende Night-Exit-Code-Integration bleibt grün; neue Fälle:
  ensure ok / ensure fail / ensure skipped.

D4/T69 — B1 DURA'S TRIALS v1 (Mechanik research-verifiziert; Navigation LIVE):
  Neues scripts/afk_duras.py: Entry über Battle Modes → Dura's Trials (Karte).
  Ablauf: höchsten freigeschalteten Floor per OCR bestimmen; ist er noch nicht
  gecleart → genau 1 Kampf (Prep→Fight; Failure refundet Token → bounded Retry);
  danach SWEEP-Loop auf den höchsten Floor, bis Token leer (OCR „N/6").
  Wichtig: Token resetten TÄGLICH (nicht sparen); Sweep droppt 2-Klassen-Essenz.
  Marker-File nach Erfolg; bounded; Abbruch bei UNKNOWN (Non-blind-Prinzip).
  Alle Koordinaten als benannte Konstanten oben im Skript schreiben
  (Hermes korrigiert live). Noch NICHT in watch/night einhängen.
  TESTS: fake_vision-Kette (Entry, Floor-OCR, Sweep bis 0, sauberer Abbruch).

DoD je Task: Gesamtsuite grün (Basis f1211ab, 191+), 1 Task = 1 Commit mit
klarem Namen, kurzer deutscher Report je Task, am Ende Sammelbericht
docs/reports/claude-wave-4-run.md. SafeGuard-Blockade → Fallback-Tabelle §0.
```
