# Claude Code — Spectre Wave-3 Starter (C1–C5)

> Paste-fertiger Prompt. Aktualisiert: 2026-11-03. Plan: `docs/claude-wave-3-plan.md`.

---

```
WORKSPACE: C:\Users\Sigi\spectre

STAND: Wave-2 (A1–A8) ist KOMPLETT in `main` gemergt (147 Tests grün). Wave 3
startet mit 5 offline-baubaren Bausteinen (C1–C5), die später Live-Tempo-,
Hacking- und Selbstbetrieb-Features tragen. Details + Kontext: docs/claude-wave-3-plan.md.

LIES ZUERST (komplett):
  1. docs/claude-wave-3-plan.md — Zielbild, Gap, §4 = deine Briefs C1–C5, §2 Safety-Matrix.
  2. docs/claude-wave-2-plan.md §0 — Spielregeln + Fallback-Tabelle (gelten 1:1 weiter).

AUFTRAG: C1 → C2 → C3 → C4 → C5, je 1 Branch (feature/T61-… bis feature/T65-…),
1 Baustein = 1 Commit (oder wenige klar benannte), KEIN push.

KURZBRIEFS (Details in §4 des Wave-3-Plans):
  C1/T61  Battle-Wall-Time-Instrumentierung in stage_push/dream/arena
          (wall=NN.Ns je Kampf, JSONL .spectre/metrics/battles.jsonl, Summary,
          v.append_metric() atomar; Tests mit gepatchter Zeit).
  C2/T62  scripts/bluestacks-fps.py (--show/--set N/--restore, bluestacks.conf
          auto-finden, .bak, nur fps-Key, Vor/Nach-Ausgabe, Restart-Hinweis; Fixture-Tests).
  C3/T63  hack/frida/ Kit (README mit Setup für DIESEN Host, attach.py tolerant,
          probe_timescale.js log-only, set_timescale.js; frida-tools ist als
          EINZIGE neue Abhängigkeit erlaubt — attach.py muss aber auch ohne
          installiertes frida klar melden).
  C4/T64  scripts/adb-bench.py (Tap-/Screencap-Latenz p50/p90/p99, je 50×,
          harmlose Tap-Stelle (300,250); leichte Tests).
  C5/T65  scripts/device-ensure.sh (bluestacks-ensure.sh nutzen; Spiel per
          monkey starten; bis WORLD pollen; Titel-Tap + Login-Popup via
          afk_normalize-Logik; klare Exit-Codes; Nutzung noch nicht verdrahten).

REGELN (wie Wave-2):
  - OFFLINE ONLY (kein adb/BlueStacks live — Gerät gehört Hermes); `.spectre/`
    read-only Input, Artefakte nach scripts/tests/.artifacts/.
  - DoD: volle Suite grün — `python -m unittest discover -s scripts/tests`
    (Baseline 147 Tests + deine neuen). Keine neuen Deps AUSSER C3 (frida-tools).
  - TODOS.md nicht editieren. Kein rebase/reset. Rust nur falls nötig (GNU-Toolchain).
  - Append-only; bestehende Abläufe nicht ändern. C1 darf Messpunkte ergänzen,
    aber keine Ablauf-Logik umbauen.
  - Wenn etwas Live-Wissen fehlt (z. B. genaues bluestacks.conf-Layout, frida-Version):
    tolerant/defensiv bauen + im Bericht als „LIVE zu prüfen" markieren.

WENN DU BLOCKST: Fallback-Tabelle §0 (Wave-2-Plan); sonst dokumentieren + weiter.

ENDE: Bericht `docs/reports/claude-wave-3-starter-run.md` + Antwort: pro Baustein
Branch/Commits, geänderte Dateien, ECHTE Testausgabe, LIVE-Check-Liste für Hermes
(was er am echten System prüfen muss), offene Punkte.
```

---

## Hinweise für Sergej (nicht mitkopieren)

- **Was das schaltet:** C1 = Messbasis („messen vor optimieren" — ohne die kein
  Urteil über Speed-Hacks). C2 = FPS-Test-Werkzeug. C3 = der Frida-Koffer für die
  Speed-/Memory-Hacks. C4 = adb-Latenz. C5 = Selbststart-Kette (Bot holt sich
  Emulator+Spiel selbst). Danach kommen die Live-Tests (meine Lane) und die
  Ergebnisse der zwei Research-Agents in den Plan.
- Nach dem Lauf wie immer: „Claude ist durch" → Review/Merge/Verify + dann die
  Live-Recon-Runde (Frida, timeScale, FPS, A8-Checks).
