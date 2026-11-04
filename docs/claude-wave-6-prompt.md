# Claude Code — Spectre Wave 6 (F1–F5: Fast-Path-Rollout, Memory-Konsolidierung, Dura's-Aktivierung, Frida-Härtung)

> Paste-fertiger Prompt. Stand: 2026-11-04 früh. Basis: aktueller main.
> Wave 5 ist gemergt UND live belegt: `read-batch` + `afk_memory` liefern am Gerät
> „team_power: ok" (Drift-Re-Location greift nach ASLR-Wechsel). `.spectre` enthält
> wieder echte Frames (Queue-Driver-Regen) — crop-Messungen sind jetzt möglich.
> Wave 6 rollt die Wave-5-Bausteine in die Praxis: überall dort, wo sie sicher sind.

---

```
WORKSPACE: C:\Users\Sigi\spectre

STAND: Waves 1–5 gemergt, reviewt; Leveling + read-batch + afk_memory live
verifiziert. Wave 6 = ROLLOUT (kein neues Paradigma): die gebauten Fast-Paths
(tap_seq, ocr_region, afk_memory) konsequent auf die restlichen Pfade anwenden,
Dura's aktivieren, Frida betriebsreif machen. Jede Umstellung EINZELN + mit
Tests; Verhalten unverändert, nur schneller/robuster. Alles offline baubar;
LIVE-Marker für Unverifiziertes. `.spectre` darf READ-ONLY gelesen werden
(Frames!), nie geschrieben.

LIES ZUERST (komplett):
  1. docs/claude-wave-2-plan.md §0 — Spielregeln + Fallback-Tabelle (gelten 1:1).
  2. docs/reports/claude-wave-5-run.md — was bewusst NICHT umgestellt wurde
     (deine Liste) = Rollout-Vorrat.
  3. scripts/afk_memory.py + v.tap_seq/key_seq + v.ocr_region (die Werkzeuge).
  4. scripts/afk_duras.py — Einhäng-Kandidat (v1 von dir, noch nicht verdrahtet).

AUFTRAG: F1 → F2 → F3 → F4 → F5. Je 1 Branch (feature/T81-… bis feature/T85-…),
KEIN push, keine neuen Dependencies, Tests im fake_vision-Stil.

F1/T81 — afk_memory-ROLLOUT (ein Ort für Memory-Werte):
  Alle verbleibenden direkten Power/Offset-Leser auf afk_memory umstellen
  (die 4 Skripte aus deiner Wave-5-Notiz + was ein grep noch findet). Muster:
  bestehende Guard-Semantik NICHT ändern, nur den Bezug zentralisieren.
  Regel im Modul-Docstring verankern: „kein Skript liest Offsets direkt, wenn
  afk_memory reicht". Tests: die bestehenden Guard-Tests bleiben unverändert
  grün; 1-2 neue Wiring-Checks. Laufzeit-Ersatz per grep-Assert dokumentierbar.

F2/T82 — REGION-OCR-ROLLOUT (mit den jetzt vorhandenen echten Frames):
  Die in Wave 5 ausgelassenen Voll-OCR-Checks: für JEDEN Check zuerst prüfen,
  ob in C:\Users\Sigi\spectre\.spectre\shots-*\ ein passender ECHTER Frame liegt
  (read-only; Dateinamen wie hl_entry/stage_*/claim_* usw.). Wenn ja: Crop-Box
  am Frame messen (Frame-Pfad + Box als Kommentar), v.ocr_region nutzen; wenn
  nein: Check unangetastet lassen. EINZELN umstellen, bestehende Tests grün.
  Ziel: mindestens entry/claim/stage-prep-Hot-Checks; Messnotiz (Zeitersparnis
  grob) in den Run-Report.

F3/T83 — TAP_SEQ-ROLLOUT II:
  a) afk_hero_level: die zwei Tap-Aufrufe (Panel+Confirm) über tap_seq bündeln
     NUR wenn zwischen ihnen nichts gelesen wird (bleibt: read dazwischen NICHT
     verlieren); Detail-Navigation (BACK-Ketten) prüfen.
  b) dailies/gift/claim-Ketten: blinde Mehrfach-Taps bündeln (immer erst nach
     der OCR-Gate-Entscheidung; nie Gate+Taps in einen Batch mischen).
  Tests je Umstellung; bestehende Suiten unverändert grün.

F4/T84 — DURA'S AKTIVIEREN (Tageslauf):
  afk_duras.py in scripts/afk-bot-watch.sh einhängen: NACH den Claims, VOR dem
  Stage-Push; eigener Tagesmarker (.spectre/duras-last.txt, Gate wie beim
  Leveling: genau 1 Versuch/Tag, Marker nur bei rc 0/4 = sauber); weich (Fehler
  killen die Kette nicht, Exit unverändert); Schalter AFK_DURAS=1 (default an).
  NICHT Token kaufen (bestehender Pfad). Dazu kleiner Hardening-Pass im Skript
  nur wo nötig. Hinweis: Koordinaten tragen LIVE-Marker; Hermes spielt
  Korrekturen als kleines Folge-Update ein — baue so, dass das nur die
  Konstanten oben betrifft. Tests: Einhängung (2-Läufe-Gate, weich, Schalter).

F5/T85 — FRIDA/Speed-Profil BETRIEBSREIF:
  speed_profile.py: Port-/Versions-Konsistenz mit dem Hermes-Live-Setup
  absichern (HERMES-SETUP: frida-server wird von Hermes eingerichtet; Ports als
  Konstanten mit LIVE-Marker), `status --json` für Skripte, klare rc-Semantik
  (3 = frida fehlt, 4 = server tot), README-Abschnitt „Speed-Profil" in
  hack/frida/README. NICHT in den Tageslauf einbauen (env-gated, bis live
  bewiesen). Tests: alle Pfade gemockt.

DoD je Task: Gesamtsuite grün (Basis aktueller main), 1 Task = 1 Commit,
deutscher Kurzreport je Task, Sammelbericht docs/reports/claude-wave-6-run.md.
SafeGuard-Blockade → Fallback-Tabelle §0.

NICHT in dieser Welle: T29 (Legend Trial/Labyrinth/Honor-Duel) + T45h
(Friend Favors/Homestead) — Live-Recon durch Hermes läuft; OpenSpeedy-Politur
(Host-GUI) = Wave 7; B-Welle-Modi-Bau nach Recon.
```
