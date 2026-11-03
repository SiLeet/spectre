# Claude Code — Spectre Wave-2 (autonomer Lauf)

> Paste-fertiger Prompt. Aktualisiert: 2026-11-03. Gehört zu `docs/claude-wave-2-plan.md`.

---

```
WORKSPACE: C:\Users\Sigi\spectre

LIES ZUERST (in dieser Reihenfolge, komplett):
  1. docs/claude-wave-2-plan.md      — Spielregeln (§0), Fallback-Tabelle, Briefs A1–A7, B1–B6
  2. docs/reviews/2026-11-03-scripts-review.md — voller Review-Report mit Frame-Beweisen (für A7)

AUFTRAG: Arbeite Wave A KOMPLETT ab, genau in dieser Reihenfolge:
  A1 (T46 Test-Harness) → A2 (T47 Parser-Tests) → A3 (T51 Mock-ADB-Tests)
  → A4 (T48 Dedup + _level_hands löschen) → A5 (T49 wall-dash) → A6 (T50 Doku)
  → A7a (HIGH-Fixes) → A7b (MED) → A7c (LOW).

REGELN PRO TASK:
  - Neuer Branch (feature/T{NN}-slug laut Plan), Commit(s) lokal, dann nächster Task.
  - KEIN git push, KEIN rebase/reset. Nur add/commit auf deinen Branches.
  - DoD: neue Tests grün — `python -m unittest discover -s scripts/tests -v`
    (Interpreter: `python` in der Shell = 3.14.9, PIL vorhanden).
  - A7: 1 Finding = 1 Commit, Finding-Nr aus dem Report in die Commit-Message.
  - Rust/cargo nur anfassen wenn nötig — dann IMMER GNU-Toolchain
    (`cargo +stable-x86_64-pc-windows-gnu`, MSVC ist auf diesem PC kaputt).

HARTE REGELN (sonst Merge-Bruch mit dem parallel laufenden Queue-Driver):
  - OFFLINE ONLY: nichts startet/berührt BlueStacks oder adb live — das Gerät gehört Hermes.
  - `.spectre/` ist READ-ONLY Input (Screenshots/Logs, gitignored). Artefakte nur nach
    scripts/tests/.artifacts/.
  - Keine neuen Dependencies: Python-Stdlib + PIL. Kein pytest, kein numpy.
  - TODOS.md NICHT editieren (Queue-Driver). CLAUDE-TASKS.md nur lesen.
  - Append-only wo möglich: bestehende Koordinaten/Abläufe nicht ändern, außer der Brief
    sagt es explizit. Keine Big-Bang-Refactors.
  - A1-Manifest: aktueller Stand wird committet (Manifest = kleine Textdatei; die Frames
    bleiben lokal, Tests skippen fehlende Pfade mit Warnung).
  - Frame-Scan in A1 darf ruhig 1–3 Minuten dauern (779 PNGs) — nicht abbrechen.

WENN DU BLOCKST (Safeguard, Zweifel, fehlende Info):
  → Fallback-Tabelle in §0 des Plans anwenden.
  → Trick greift nicht? Task sauber stoppen, im Abschlussbericht als BLOCKIERT
    (Grund + wörtliche Frage) dokumentieren — und mit dem NÄCHSTEN Task weitermachen.
  → Nicht auf Antwort warten, Annahmen kurz dokumentieren.

WAVE B/C: B1–B6 nur bauen, wenn der `> RECON:`-Block im Plan gefüllt ist — sonst
  skippen und im Bericht listen. Wave C ist Hermes-Lane (nicht anfassen).

START: mit A1.
ENDE: Abschlussbericht (Markdown, Datei `docs/reports/claude-wave-2-run.md` + als
  Antwort): pro Task Branch, geänderte Dateien, neue Funktionen, ECHTE Testausgabe
  (Kernzeilen), Blockaden, offene Punkte, Live-Check-Liste für Hermes.
```

---

## Hinweise für Sergej (nicht mitkopieren)

- **Ein Prompt, ganzer Lauf.** Claude arbeitet A1→A7c in einer Session durch. Wenn du
  es kleinteiliger willst: Plan §4 sagt „ein Brief pro Session" — dann diesen Prompt
  kürzen auf „START: mit A1. Danach stoppen." und später „Weiter mit A2." etc.
- **Wenn Claude meckert:** wörtlich mir schicken (Chat), ich re-frame den Brief oder
  baue den Task selbst (Fallback-Lane im Plan §0).
- **Nach dem Lauf:** mir „Claude ist durch" sagen — ich reviewve (Fresh-Eyes-Subagent),
  merge die Branches nach `main` und mache die Live-Verifikation + B-Recon.
- Wave B heißt: Claude braucht vorher meine Live-Koords (RECON-Blöcke) — die fülle ich,
  sobald Wave A steht (oder früher, sag einfach Bescheid).
