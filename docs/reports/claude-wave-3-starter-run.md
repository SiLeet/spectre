# Claude Wave-3 Starter Run (C1–C5) — Abschlussbericht (2026-11-03)

Auftrag: C1 → C5 aus `docs/claude-wave-3-plan.md` §4, je ein Branch, offline, kein push.
Ergebnis: **alle fünf Bausteine gebaut, nichts blockiert.** Kein adb/BlueStacks live;
einzige Berührung des echten Systems: ein **lesendes** `bluestacks-fps.py --show`
auf die echte `bluestacks.conf` (unverändert, kein `.bak` angelegt).

## Git

Worktree `C:\Users\Sigi\spectre-w3` (**ohne** `.spectre`-Junction). Die Branches sind
unabhängig (keine gemeinsamen Dateien) und mergen einzeln konfliktfrei in `main`
(`1eab299`, `git merge-tree` geprüft).

| Baustein | Branch | Commits | Tests auf dem Branch |
|---|---|---|---|
| C1 / T61 | `feature/T61-battle-metrics` | `5ab4969` + Merge `46a6bfe` | `Ran 157 tests … OK (skipped=22)` |
| C2 / T62 | `feature/T62-bluestacks-fps` | `316f989` | `Ran 156 tests … OK (skipped=22)` |
| C3 / T63 | `feature/T63-frida-kit` | `1f59be0` | `Ran 158 tests … OK (skipped=22)` |
| C4 / T64 | `feature/T64-adb-bench` | `492dc12` | `Ran 155 tests … OK (skipped=22)` |
| C5 / T65 | `feature/T65-device-ensure` | `cfecee6` (+ dieser Bericht) | `Ran 157 tests … OK (skipped=22)` |

`main` (`1eab299`) selbst: `Ran 150 tests … OK (skipped=22)` (der Prompt nannte 147; Hermes
hat seitdem 3 ergänzt). Alle fünf gemergt: 150 + 7 + 9 + 8 + 5 + 7 = **186 Tests**.
Die 22 Skips sind die Real-Frame-Tests (`.spectre` leer, R13).

**Merge-Hinweis T61:** `main` bekam während des Laufs `73ea8aa` (Start-Tap-Budget,
Per-Fight-Prune in `afk_dream_realm.py`), das dieselben Zeilen wie T61 berührt. Ohne
rebase/reset habe ich `main` in T61 gemergt (`46a6bfe`) und beide Seiten behalten.

## C1 / T61 — Battle-Wall-Time-Instrumentierung

- `afk_claim_vision`: `METRICS` (`.spectre/metrics/battles.jsonl`), `append_metric(rec, path=None)`
  (eine Zeile = ein `os.write` auf `O_APPEND`, `ts` automatisch, wirft nie),
  `battle_metric(mode, result, wall_s, stage=None)` → schreibt `{ts, mode, stage, result, wall_s}`
  und liefert `wall=NN.Ns`, `wall_summary(mode, walls)`.
- Wall = `time.monotonic()` vom (bestätigten) Battle-Tap bis zur Ende-Erkennung:
  - **stage_push** Single-Modus je Kampf (`victory/defeat/stall`); ein Re-Tap startet die Uhr neu.
  - **dream** je Kampf (`ended/timeout`); auch der A8-Re-Arm-Tap startet die Uhr neu.
  - **arena** je Kampf (`changed/unchanged`) — **keine Ende-Erkennung**: wall ≈ `--wait-fight`.
  - Summary-Zeile `metrics[<mode>]: N battle(s), wall mean … (min …, max …)` je Lauf.
- Nur Messpunkte, keine Ablaufänderung. `FakeDevice` biegt `v.METRICS` nach
  `scripts/tests/.artifacts/` um — Tests schreiben nie nach `.spectre`.
- Tests: `scripts/tests/test_metrics.py` (7, gepatchte Zeit).
- Offen: **Auto-Modus** (stage_push `--auto`) nicht je Kampf gemessen — Kämpfe werden dort
  per Skip sofort aufgelöst, eine Wall-Time wäre bedeutungslos. Für den FPS/Frida-Vergleich
  den Single-Modus (`--battles N`) oder Dream nehmen. `stage` bleibt `null` (kein OCR im Loop).

## C2 / T62 — `scripts/bluestacks-fps.py`

- `--show` / `--set N` / `--restore`, `--instance` (Default `Pie64` / `BS_INSTANCE`), `--conf`.
- Conf: `BLUESTACKS_CONF` oder `%ProgramData%\{BlueStacks_nxt, _msi5, _msi2, BlueStacks}\bluestacks.conf`
  (auf diesem PC: `C:\ProgramData\BlueStacks_nxt\bluestacks.conf`).
- Fasst **nur** `bst.instance.<I>.max_fps="N"` an (Layout vom echten Conf gelesen; Byte-genau,
  Zeilenenden bleiben). Erstes `--set` legt `.bak` an, weitere überschreiben es nie;
  `--restore` legt `.bak` zurück. Atomares Schreiben, Vor/Nach-Ausgabe, Restart-Hinweis.
- Warnt, wenn `HD-Player.exe` läuft (BlueStacks kann die Conf beim Beenden zurückschreiben) und
  wenn N > 60 bei `enable_high_fps` ≠ `"1"` (wird gemeldet, nie geändert).
- Exit 0 / 2 Conf fehlt / 3 Key oder Wert / 4 kein Backup. Tests: `test_bluestacks_fps.py` (9, synthetische Fixture).
- Echter Stand (lesend): `Pie64.max_fps = 60`, `enable_high_fps = 0`, `enable_vsync = 0`.

## C3 / T63 — Frida-Kit `hack/frida/`

- `README.md`: Setup für **diesen** Host — frida-tools/frida-server-Versionsgleichheit, ABI per
  `getprop`, **Root ist aktuell AUS** (`bst.feature.rooting="0"`, `Pie64.enable_root_access="0"`),
  push/chmod/start, Reihenfolge Probe → Messen → Setzen, Undo = Spiel-Neustart.
- `attach.py`: `ps` / `attach` / `spawn`, findet das Spiel über `igame` (wie `spectre find igame`),
  `--pid`, `--params` (JSON → `frida -P`), `--dry-run`. **Ohne frida-tools:** klare Meldung, Exit 3
  (geprüft: auf diesem PC ist frida nicht installiert → `ERROR: frida-ps not found …`, rc=3).
- `probe_timescale.js`: **nur lesen** — `timeScale`, `fixedDeltaTime`, `targetFrameRate`,
  `vSyncCount` über `il2cpp_resolve_icall`, loggt `set_timeScale`-Aufrufe; meldet ARM-Übersetzung
  (`libhoudini`/`libndk_translation`).
- `set_timescale.js`: setzt nur mit explizitem `scale` (geklemmt auf (0, 4]), optional `repeat_ms`,
  `rpc.exports.get/set`.
- Frida 16/17-API-tolerant. Tests: `test_frida_kit.py` (8; brauchen weder frida noch Gerät;
  `node --check` für die JS-Dateien, Node 26 vorhanden).

## C4 / T64 — `scripts/adb-bench.py`

- `--n 50`, `--only tap|screencap`, `--force`. Misst `input tap 300 250` und `exec-out screencap -p`
  über `v.adb` (gleicher Pfad/Serial wie der Bot), Tabelle p50/p90/p99/max in ms (Nearest-Rank).
- Sicherung: der Tap-Benchmark läuft nur, wenn ein Screenshot WORLD ist ((300,250) ist nur dort
  harmlos), sonst Exit 1; `--only screencap` braucht kein Gate. Exit 2 bei adb-Fehler.
- Tests: `test_adb_bench.py` (5, adb + Uhr gemockt).

## C5 / T65 — `scripts/device-ensure.sh` (+ `scripts/afk_device_ready.py`)

- Ruft `bluestacks-ensure.sh` (Exit 2/3/4/5 durchgereicht; `--force`/`--min-idle` weitergegeben),
  findet das Paket per `pm list packages | grep igame` (`AFK_PACKAGE` überschreibt), startet per
  `monkey -p <pkg> -c android.intent.category.LAUNCHER 1`, wartet auf eine pid (60 s).
- `afk_device_ready.py` pollt `classify()` bis WORLD/PANEL: Login-Popup → Resolver (sonst 1× BACK),
  Titelbild → Tap (960,540) **nur** bei OCR „tap to start“/„touch to start“/…, Ladebilder werden
  abgewartet (kein BACK — am Titel öffnet BACK den Beenden-Dialog). Nach dem Timeout einmal
  `afk_normalize`.
- Exit 0 bereit / 6 nicht installiert / 7 kein Prozess / 8 Welt nicht erreicht / 9 kein python+PIL / 64.
- **Nicht** in watch/night verdrahtet (Brief). Tests: `test_device_ensure.py` (7; Python-Teil mit
  FakeDevice, Shell-Exitpfade mit Stub-`adb`/Stub-`bluestacks-ensure`).

## LIVE-Check-Liste für Hermes

1. **C1 Baseline:** `afk_stage_push.py --battles 3` und ein Dream-Lauf → Logzeilen mit `wall=…s`,
   Summary-Zeile, `.spectre/metrics/battles.jsonl` mit plausiblen Werten.
2. **C2 FPS:** Instanz stoppen → `bluestacks-fps.py --show` → `--set 120` → Instanz starten →
   im BlueStacks-Menü prüfen, ob 120 aktiv ist (oder wegen `enable_high_fps=0` bei 60 bleibt) →
   Wall-Time-Vergleich mit C1 → `--restore`. Prüfen, ob BlueStacks die Conf beim Beenden zurückschreibt.
3. **C3 Frida:** frida-tools installieren, `frida --version` → passender frida-server; ABI
   (`getprop ro.product.cpu.abilist`); Root für Pie64 einschalten; Server starten;
   `attach.py ps` findet `…igame…`; `probe_timescale.js` nach dem Login: wird `libil2cpp.so`
   gesehen (oder ARM-Übersetzung)? Werte der vier Größen; Anti-Debug (Disconnect?).
   Erst danach `set_timescale.js` mit 1.5 + Wall-Time-Vergleich.
4. **C4:** `adb-bench.py --only screencap` (gefahrlos), dann in der Welt `adb-bench.py` → Tabelle.
5. **C5:** Spiel schließen → `device-ensure.sh --force` → Start per monkey, Titel-Tap (OCR-Wort
   des echten Titelbilds prüfen, ggf. `TITLE_WORDS`/`TITLE_TAP` anpassen), Login-Popup, Exit 0.
   Paketname aus `pm list packages | grep igame` notieren.

## Offene Punkte

- Alle Live-Annahmen oben sind ungeprüft: Titeltext + Tap-Punkt, `enable_high_fps`-Wirkung,
  ob BlueStacks die Conf überschreibt, `frida -P`-Support der installierten Version,
  il2cpp-Sichtbarkeit unter ARM-Übersetzung.
- C1 Auto-Modus ohne Per-Kampf-Messung (s. o.); Arena-Wall ist nur die Wartezeit.
- Shell-Skripte landen mit `autocrlf=true` als CRLF im Checkout (wie `bluestacks-ensure.sh`);
  der hiesige bash verarbeitet das (Stub-Tests liefen). Eine `.gitattributes`-Regel
  `*.sh text eol=lf` wäre robuster — nicht angefasst (repo-weit, nicht im Brief).
