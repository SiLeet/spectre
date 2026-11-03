# Wave 3 — „Voll-Auto & Voll-Optimiert" (+ Hacking-Lane)

> Zielbild: Der Bot spielt **alle** täglichen + Event-Quellen des Accounts
> vollständig, **optimiert** Entscheidungen anhand von Daten, läuft **24/7
> selbstständig** (inkl. Emulator-/Spiel-Management) und nutzt das **maximale
> legale Tempo** — sicher, ohne Client-Modifikation.
>
> Stand-Referenz: Wave-2 gemergt (main, 147 Tests). Der ehrliche Abstand:

## 0. Ist/Soll-Gap (brutal ehrlich)

| Achse | Ist | Soll | Lücke |
|---|---|---|---|
| Abdeckung | Chest, Quests, Mail, Gift, Arena(4), Dream(tlw.), Push | ALLE Quellen: Dura's, Legend Trial, Honor Duel, Battle Drills, Events (Primal Lord/Clash…), Guild (Store-Letter 210💎/Tag!), Friends, Homestead-Assists, Shop-Freebies, Lucky-Flip-Picks, Season-Quests, Gear/Skills | ~5 von ~20 Systemen |
| Entscheidungen | fixe Teams, keine Records, keine Policies | Team-Optimizer, Records-Replays, Counter/Formationen, Kauf-/Spar-Regeln je Ressource | Intelligenz fehlt |
| Robustheit | Screens gefixt, Gates, kein Blind-Tap | Selbststart (PC-Boot→Spiel→Bot), Update-Survival, kompletter Self-Heal | Auto-Device fehlt |
| Tempo | Button-2×, Nacht-Push-Fenster | FPS/Client-Speed-Mods falls wirksam; Push in jedes freie Fenster (idle-gated) | ungemessen/ungenutzt |
| Daten | nur `team_power` aus Memory | Memory-Map: Helden-Stats, Level, Keys/Chances, Timer, Counter; + Battle-Wall-Time-Metriken | Messbasis fehlt |
| Zeitsteuerung | feste Scheduler-Zeiten | Season-/Event-Kalender, Arbitrage-Fenster automatisch | Detektor fehlt |

## 1. Leitplanken (wie §0 Wave-2, plus)

1. Offline (Claude) ≠ Live (Hermes). Gerät, Emulator, adb gehören Hermes.
2. Jede Hacking-Stufe wird nach **Risiko klassifiziert** (siehe §2) und
   erst nach Live-Beweis in den Daily-Pfad eingebaut. Kein harter Einbau
   von Spekulativem.
3. Messen vor Optimieren: Jede Speed-Maßnahme wird gegen die Wall-Time-Baseline
   gemessen (C1) — erst dann Urteil.
4. 1 Brief = 1 Branch = lokale Commits (Claude); Merge+Verify Hermes.
5. Queue-Disziplin: neue Ideen werden angehängt, nicht quer eingeschoben.

## 2. Safety-Matrix (Hacks — „alles sicher")

| Stufe | Mechanik | Risiko | Persistenz | Ban-Risiko |
|---|---|---|---|---|
| L0 | ADB-Input/UI (heute) | keins | — | keins (Standard-Emulator) |
| L1 | Emulator-Setting (FPS) | keins | lokal (conf) | keins |
| L2 | Memory **Read** (spectre) | keins | flüchtig | keins |
| L3 | Memory **Write** / Frida (z. B. timeScale) | niedrig (client-only, Server rechnet nach; worst case Anzeige) | flüchtig (bis App-Neustart) | sehr niedrig |
| L4 | Uhrzeit/Emulator-Zeit | niedrig | lokal | keins, solange nur Client-Timer |
| L5 | Netz/Paket (Sniffing, ggf. Requests) | niedrig | — | keins |
| L6 | APK-Mod | bisher keins | — | — |

Regeln: immer **erst loggen, dann schreiben**; Schreib-Kandidaten mit
Vor/Nach-Beweis dokumentieren; Frida **nach** dem Login attachen (Anti-Debug
minimieren); alle conf-Edit mit Backup.

## 3. Arbeitspakete

### W3-1 Coverage (Rest-Systeme vollmachen) — je RECON(Hermes)→CODE(Claude)→LIVE(Hermes)
- B1 Dura's Trials, B2 Dream-Tiers+Skip, B3 Arena-Kette, B4 Friends/Homestead,
  B5 Season-Detektor, B6 Legend-Trial-Sonntag (Briefs stehen, RECON-Blöcke offen)
- **NEU:** Guild-Store-Letter (210💎/Tag) + Shop-Freebies/Refresh-Policy;
  Events-Sweeper (generisches „alle Event-Tabs nach Claimables scannen");
  Honor Duel (Badge-Farming-Regeln); Team-/Formations-Optimizer (braucht W3-3-Map);
  Gear/Skill-Management (equip/better-gear auto).

### W3-2 Speed & Hacking (die „hacking sachen")
- **H1 FPS-Test:** BlueStacks-FPS hochsetzen (conf, C2) → Battle-Wall-Time vor/nach
  messen (C1). Erwartung: Wirkung nur falls Frame-gebunden. Risiko L1.
- **H2 Frida/timeScale:** frida-server auf BlueStacks, il2cpp/Unity-Speed:
  Time.timeScale finden (log-only), dann testweise ×1.5/×2 setzen; Wirkung auf
  Battle-/Animations-Wall-Time messen. Wenn wirkt: „Speed-Profil" im Bot.
  Risiko L3, größter Hebel-Kandidat.
- **H3 Memory-Map-Ausbau** (spectre + OCR-Kreuzvalidierung): Helden-Level/Stats,
  Chances, Keys, Chest-Timer, Quest-Counter, Wallet-Anzeigen. Zweck: robuste
  Entscheidungen ohne OCR-Flakiness + Grundlage Team-Optimizer.
- **H4 Netz-Sniffing:** mitmproxy gegen BlueStacks — ist AFJ-Traffic lesbar
  (Pinning?)? Wenn ja: State-Readback (Timer/Currencies) und ggf. spätere
  API-Aktionen. Erst Recherche/Recon, dann bewerten.
- **H5 Uhrzeit-Experimente:** Emulator-Uhrzeit ±, welche Client-Timer bewegen
  sich (Chest? Shop-Refresh? Event-Timer?) → ggf. „Doppel-Claim"-Fenster.
- **H6 Feinheiten:** adb-Latenz-Benchmark (C4), Tap-Flood-Grenzen,
  Eingabe per `sendevent` vs `input tap` (Präzision), Multi-Instanz-Ausblick.

### W3-3 Daten & Optimierung
- Battle-Metriken (C1) → Dashboard-Erweiterung; Team-Optimizer (Daten aus H3);
  Records-Replay-Integration (B2-nah); Arena-Zielwahl per Power-OCR→Memory;
  Policies: Gold/EXP/Diamanten/Keys als Regel-Tabelle im Repo (mit Freigabe-Flags).

### W3-4 Robustheit / Selbstbetrieb
- **C5 device-ensure**: Bot startet bei Bedarf BlueStacks + Spiel selbst, räumt
  Login/Titel-Popups (Aufsatz auf `bluestacks-ensure.sh`), watch/night nutzen es.
- PC-Boot→alles hoch (Task-Kette), Update-Survival (Spiel-Update → Erst-Start-
  Assistent), Log-Rotation/Restore-Test (Backup der Runtime-States).

## 4. SOFORT für Claude (offline baubar, Branch feature/T61–T65)

> Vorlage exakt wie Wave-2 (DoD, Regeln, Fallback-Tabelle §0 dort): keine neuen
> Deps (Ausnahme dokumentiert bei C3), Tests im fake_vision-Stil, kein push.

- **C1 / T61 — Battle-Wall-Time-Instrumentierung.** stage_push/dream/arena:
  Sekunden je Kampf (Start=bestätigter Battle-Tap → Ende=Result-Erkennung) als
  Logfeld `wall=NN.Ns` + JSONL `.spectre/metrics/battles.jsonl`
  {ts,mode,stage,result,wall_s}; Summary je Lauf. Helper `v.append_metric()`
  (atomar). DoD: Tests mit gepatchter Zeit.
- **C2 / T62 — `scripts/bluestacks-fps.py`.** --show/--set N/--restore für das
  fps-Setting der Instanz in `bluestacks.conf` (Pfad automatisch suchen,
  `%ProgramData%`-Kandidaten), Backup `.bak`, nur den fps-Key anfassen,
  Vor/Nach-Ausgabe, Hinweis „Neustart der Instanz nötig". Tests mit Fixture-conf.
- **C3 / T63 — Frida-Kit `hack/frida/`.** README (Setup: frida-tools Version
  passend zu frida-server, adb push, Start), `attach.py` (list/spawn/attach/
  script-run; ruft frida-CLI wenn vorhanden, sonst klare Fehlermeldung),
  `probe_timescale.js` (log-only: Kandidaten für Time-Scale/Vsync finden),
  `set_timescale.js` (Wert setzen). Ausnahme: frida-tools erlaubt (nur Kit,
  nicht Tests). Tolerant gegen API-Unterschiede schreiben.
- **C4 / T64 — `scripts/adb-bench.py`.** Latenz-Perzentile für `input tap`
  (harmlose Stelle) und `screencap` (je 50×), Tabelle p50/p90/p99. Tests leicht.
- **C5 / T65 — `scripts/device-ensure.sh`.** Nutzt `bluestacks-ensure.sh`,
  zusätzlich: Spiel per `monkey` starten, bis WORLD pollen, Titel-Tap +
  Login-Popup-Claim (nutzt `afk_normalize`-Logik, Python-Helper erlaubt),
  Exit-Codes klar. Wird später von watch/night optional aufgerufen.

## 5. Meine Lane (parallel, live)

- **R-A/R-B Research-Agents laufen** (Speed-/Hack-Landschaft; bestehende
  AFJ-Projekte + API-Sniff + Trick-Liste). Ergebnisse fließen hier ein.
- **Live-Recon L1–L8** (nächste Live-Fenster, idle-gated):
  L1 Frida-Frisibility auf DIESEM Setup (frida-server push/attach, AFJ-Anti-Debug-Check)
  L2 timeScale-Kandidaten suchen (probe.js) + Effekt messen
  L3 FPS-Test + Messung via C1
  L4 Memory-Map Runde 1 (Chances/Keys/Timer) mit OCR-Kreuzvalidierung
  L5 A8-Live-Checks (R15) + F1/F7-Gegenproben
  L6 B1–B6 RECON-Blöcke füllen (Dura's zuerst)
  L7 Frame-Manifest-Regen (R13) nach Frames
  L8 mitmproxy-Sichtung (liest überhaupt was mit?)

## 6. Workflow

Wie Wave-2: Claude codet C-Briefs offline (Branches T61–T65) → Hermes Review/
Merge → Hermes Live-Verifikation + Messung → erst dann Adoption in Daily/Night.
RECON-abhängige Pakete (B/H3/H4) ziehen, sobald die Blöcke gefüllt sind.
