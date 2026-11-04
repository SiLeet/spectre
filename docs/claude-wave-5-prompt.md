# Claude Code — Spectre Wave 5 (T75–T80: Memory-first, Speed, Hack-Aktivierung)

> Paste-fertiger Prompt. Stand: 2026-11-04 00:3x. Basis: aktueller main (Suite grün; Drift-Gate, Tap-Lock euer Stand).
> Leitmotiv: **Memory-first** — Zustände wenn möglich aus dem Prozessspeicher lesen statt OCR/Screenshots;
> adb-Roundtrips bündeln; Aktionen in EIN-Session-Batches abarbeiten, damit Abläufe schnell laufen.
> Ziel: der Bot wird spürbar schneller + die Hack-Aktivierung bekommt ihre Steuerungs-Skripte.

---

```
WORKSPACE: C:\Users\Sigi\spectre

STAND: Waves 1–4.5 gemergt und reviewt; Leveling live verifiziert (04.11.). Der
Queue-Driver hat Tap-Lock (_bot_lock.py) + Drift-Gate (team_power-Anker) gebaut.
Wave 5 ist eine reine Speed-/Memory-Welle: JEDE Optimierung darf das Verhalten
NICHT ändern (gemessen an der bestehenden Suite), nur schneller/robuster machen.
Alles offline baubar; live feinjustiert Hermes.

LIES ZUERST (komplett):
  1. docs/claude-wave-2-plan.md §0 — Spielregeln + Fallback-Tabelle (gelten 1:1).
  2. docs/claude-wave-3-plan.md §3 (W3-2) + §6a (Research: Frida realm=emulated
     bestätigt, OpenSpeedy, ABI-Lage) — Kontext der Hack-Pfade.
  3. scripts/afk_claim_vision.py (v-Modul: tap/shot/ocr/classify, Drift-Guard).

AUFTRAG: T75 → T76 → T77 → T78 → T79 → T80. Je 1 Branch (feature/T75-… bis
feature/T80-…), KEIN push, keine neuen Dependencies. Tests im fake_vision-Stil.
`.spectre` read-only. Jede Umstellung EINZELN + begründet (nicht blind alles
umstellen); wo Restrisiko bleibt: Helper bauen, Umstellung mit LIVE:-Marker.

T75 — TAP-/KEY-BATCHING (adb-Roundtrips radikal senken):
  Ein adb-Aufruf kostet ~0.5–1.5 s Overhead; heute feuern wir Taps einzeln.
  Neu in v: `tap_seq([(x, y, wait), ...], tolerate=True)` und `key_seq([...])` —
  EINE `adb shell` mit `input tap X Y; sleep W; …` als Ganzes; Rückgabe ok/fehler,
  bounded; optionaler dry-Modus für Tests (Kommandostring-Assert). Umstellen:
  die heißesten BLINDEN Sequenzen (afk_normalize-Escapes, claim-Ketten,
  hero_level-Detail-Navigation [tap→reads eingestreut], stage_push-Close-Folgen).
  Jede Umstellung: bestehende Tests müssen ohne Änderung grün bleiben.

T76 — SHOT-/OCR-FAST-PATHS:
  a) v.shot: `exec-out screencap` (RAW RGBA) + Image.frombytes statt PNG-Encode/
     Decode; PNG als Fallback bei Fehlschlag (Größenprüfung 1920*1080*4+Header).
  b) v.ocr_region(name, box): Crop+OCR (Muster existiert schon als
     afk_hero_level.slot_level — generisch in v ziehen, slot_level nutzt es dann).
  c) Umstellen: die HÄUFIGSTEN Voll-OCR-Checks, bei denen eine Region reicht
     (entry/hall/detail-Basen, sweep/token-Zeilen) — Kontext-Checks bleiben voll.
  Tests: Region-Bau, Fallback-Pfad, Umstellungs-Regressionen.

T77 — SPECTRE CLI: `read-batch` (Rust; ein Attach, viele Werte):
  Neuer Subcommand `spectre read-batch --offsets <yaml> --json` liest ALLE validen
  Offsets der Datei in EINEM Prozesslauf (1× attach/regionen-cache) → JSON-Array
  [{name, address, value, fmt, valid, note?}]; ein kaputter Offset killt nicht den
  Rest (per-Eintrag-Fehlerfeld); identische Validierungslogik wie `spectre offsets`.
  Tests (Rust): Parser, YAML→Liste, Fehlerpfad, JSON-Form (Werte gemockt).

T78 — afk_memory.py (Snapshot-Layer, Herzstück "Memory-first"):
  Dünnes Modul: `snapshot()` ruft T77 (subprocess, bounded, kurzer Cache ~1.5 s)
  und liefert dict; `power()` nutzt/dupliziert NICHT die Drift-Guard-Logik —
  erst prüfen, was afk_claim_vision schon hat, und konsolidieren (ein Ort!).
  Dazu CLI-Dump `python scripts/afk_memory.py --show` (read-only Diagnose).
  Einen ersten Konsumenten umstellen (z. B. das Power-Gate) + Tests (gemockter
  spectre-Output, Cache, Fehlerpfade). Regel: kein Skript liest Offsets mehr
  direkt per adb, wenn afk_memory reicht.

T79 — mem_probe.py (Werkzeug für die Offsets-Jagd = mehr Memory):
  Generische Offset-Auto-Jagd um spectre hot/scan: Input = bekannter Wert
  (int/float) + Suchraum/Format; Ablauf: Scan → Kandidaten → Wert ändert sich
  im Spiel (oder Delta-Wert) → zweiter Scan → Schnittmenge → Report im
  offsets-yaml-Vorschlagsformat, plus Konfidenz + Kandidatenzahl. bounded,
  log-only, KEINE Schreibzugriffe. Das Tool bedient Hermes live für neue
  Offsets (Chances, Keys, Timer, Quest-Counter). Tests mit Fake-spectre-Ausgaben.

T80 — FRIDA-SPEED-PROFIL + TIMING-HÄRTUNG:
  a) scripts/speed_profile.py: frida-server über adb sicherstellen (push/start,
     Root-Check, eindeutiger Port), attach via hack/frida/attach.py mit
     --params scale=2 (bzw. 1.5/4), Statusprüfung über die Probe, OFF-Modus
     (scale=1); bounded; klare Fehlausgaben (frida fehlt → rc 3 wie attach.py).
     LIVE-Marker: frida-server-Version/Port noch ungeprüft.
  b) afk_hero_level Timing-Härtung (Live-Befund 04.11.: nach Hand-Tap waren
     ERSTE Reads bei 4/5 Händen None, ein SKIP-Race): nach Hand-Tap bounded
     warten BIS is_detail (statt fix 3.0 s; bis ~8 s in 0.5-s-Schritten),
     slot_level-None → bis zu 2 Re-Reads; identisch für pre/after; Scan-Schleife
     profitiert. Keine Koordinaten ändern. Tests (fake: erst UNKNOWN dann detail).

DoD je Task: Gesamtsuite grün (Basis aktueller main), 1 Task = 1 Commit,
kurzer deutscher Report, Sammelbericht docs/reports/claude-wave-5-run.md.
SafeGuard-Blockade → Fallback-Tabelle §0.

NICHT in dieser Welle: T29/T45h (Live-Recon), Dura's-Koord-Feinschliff (nach
Live-Test), OpenSpeedy-Automatisierung (Host-GUI; ggf. Wave 6 nach Live-Befund).
```
