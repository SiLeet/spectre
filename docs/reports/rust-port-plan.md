# T114 — Rust-Port-Plan für den AFK-Bot (2026-11-05)

Für Hermes und den User. Erarbeitet offline auf Branch `feature/T114-rust-port-plan` (Worktree `spectre-w7-T114`). Es lief kein adb und kein MCP, `.spectre` wurde nur gelesen. Grundlage sind vier Analysen (Python-Inventar, Rust-Fähigkeiten, Specs/Parität, Plattform-Machbarkeit) und zwei Kritik-Runden (Risiko, Parität). Wie die Kritik eingearbeitet wurde, steht in §13. Die Scratch-Artefakte liegen unter `…/scratchpad/wf9/`.

Direktive des Users: **„das muss vollständig in Rust“.** Dieser Plan beschreibt, wie wir dorthin kommen, ohne dass die laufenden Daily-Runs brechen.

## Kurzfassung

- **Ziel:** Alle 16 Bot-Skripte (8302 LOC Python) plus die Bash-Orchestrierung (`afk-bot-watch.sh`, `afk-night.sh`) laufen als **ein eigenes Rust-Binary `spectre-afk.exe`** (`spectre-afk <task>` / `spectre-afk run --scheduled`). Die Ausgaben sind identisch zu Python, belegt durch Goldens. Die 7 Tooling-Skripte (957 LOC) werden **nicht** 1:1 portiert.
- **Neue Crate `spectre-afk`** (Lib mit Layer-Modulen plus eigenes `[[bin]]`). Bot-Flows kommen **nicht** in `spectre-core`, **nicht** in `spectre-bot` und **nicht** als Subcommand in `spectre-cli`. Damit hängt der Daily-Run nicht an Lua/Web/tokio und nicht am `spectre.exe`, das andere Lanes neu bauen. Das Exec-Primitive wird aus der `spectre-mcp`-Lib wiederverwendet, ohne den MCP-Server anzufassen.
- **`spectre bot <task>` geht nicht**, weil `spectre bot <config.yaml>` existiert (YAML-Engine).
- **Etappe 0 kommt vor Etappe 1 und ist zweigeteilt.** E0a friert *jetzt* den Frame-Korpus ein, um weiteren Verlust zu stoppen. E0b exportiert die Goldens: das *aufgezeichnete* Python-Verhalten als **geordneter Event-Strom** (Shots, Taps mit Modus und Wait, Sleeps, Uhr-Lesungen, OCR, adb-argv, Dateiseiteneffekte) unter virtueller Uhr. E0b ist auf Python-Tree-Hash und Pillow-Version gepinnt und wird am Start jeder Etappe neu exportiert. Ohne das ist jede Paritätsaussage aus einem Worktree wertlos (dort laufen 312 Subtests und `test_frame_regression` mit `checked=0` als „grün“).
- **Höchstes technisches Risiko:** `avg()` und das OCR-Preprocessing hängen an Pillows `ImagingResample` (Fixed-Point, BILINEAR/BOX/LANCZOS) in genau der gepinnten Version (System-Python: Pillow 12.2.0). Das muss **bitgenau** nachgebaut werden. Die `image`-Crate scheidet für Vision aus.
- **OCR und Memory in zwei Schritten:** Zuerst ruft Rust `templates/ocr.ps1` bzw. `spectre.exe dump/read-batch` als Subprozess auf wie Python (Parität ohne Aufwand, Kill-Semantik bleibt). Native WinRT bzw. In-Process-Memory folgen erst danach als umschaltbares Backend nach A/B-Lauf.
- **Neue Dependencies (alle brauchen Freigabe, nichts davon wurde in T114 hinzugefügt):** D1 `png` ist Pflicht ab E0b/E1, D2 `windows` ist optional ab E3b, D3 `regex` Default nein.
- **Umschalten:** Pro Task gilt Parität grün → Shadow-Replay grün → Live-Akzeptanz durch Hermes → Default-Flip über **einen** generischen Dispatch-Hook in `watch.sh` (`AFK_RUST_TASKS`). E7a: alle Tasks auf Rust, Bash-Runner unverändert. E7b: erst dann ersetzt der Rust-Runner die Bash-Runner. Das Binary läuft aus einem **installierten, versionierten Pfad**, nie aus `target/release`.
- **Aufwand grob 40–55 Agent-Tage** (±50 %). **Kalender ist live-lane-gebunden** und wird separat geschätzt: realistisch 3–4 Monate (§3.9).

## 1. Ziel und Nicht-Ziele

**Ziel**
1. Alle Bot-Laufzeitpfade in Rust: Infra (adb/Input/Screencap), Vision, OCR, State, die gemeinsamen Flows, 14 Task-Module, Runner (ersetzt die Bash-Watch/Night-Logik) und `device-ready`.
2. Verhaltensparität mit Python als harte Bedingung vor jedem Umschalten. Der Exit-Code-Vertrag bleibt bitgenau, auch in Fehlerpfaden.
3. Am Ende gibt es ein Binary statt `.vbs → .cmd → Git-bash → python+PIL`. Damit entfallen die Fehlerklassen „kein Python/PIL“ (rc 7/9) und die Abhängigkeit vom Hermes-Python (das ohnehin kein PIL hat, PY-NOTE-19).

**Nicht-Ziele**
- Python-Schwächen werden beim Portieren **nicht** gefixt, nur notiert (§9). Rust repliziert das Verhalten. Abweichungen gibt es nur nach der Regel in §9.
- Keine neuen Features und keine neuen Tasks während des Ports. Der laufende Fix-Queue bleibt Python.
- Keine Performance-Arbeit über das hinaus, was ohnehin abfällt. Ausdrücklich ausgeklammert: das native adb-Wire-Protokoll (TCP 5037) und Batch-Optimierungen.
- Kein Port der Tooling-Skripte `speed_profile.py`, `mem_probe.py`, `wallet-hunt-all.py`, `gold-analyze.py`, `adb-bench.py`, `bluestacks-fps.py`, `afk-wall-dash.py` (§10).
- Keine Änderung an der YAML-Bot-Engine (`spectre-bot`), an `spectre-lua`, am MCP-Server (`spectre-mcp`) oder an den Task-Scheduler-Definitionen.
- Kein tokio im Bot. Die Python-Flows sind vollständig synchron, `spectre-mcp` zeigt, dass std-only gut funktioniert.

## 2. Zielarchitektur

### 2.1 Crate- und Binary-Schnitt (Entscheidung)

| Option | Bewertung |
|---|---|
| Module in `spectre-core` (Hermes-Variante) | **Nein.** Core ist eine Memory-Analyse-Lib mit 4 Deps. Bot-Flows, Vision und OCR (später `windows`-Crate) würden jeden Core-Nutzer (CLI, MCP, Web) mitbelasten. |
| Module in `spectre-bot` | **Nein.** Andere Domäne (YAML-Memory-Engine, tokio-Scheduler). Ihr `InputSimulator` (`click() -> ()`) kann weder Tap-Modus-Rückgabe noch Shot oder OCR. |
| Mehrere neue Crates (infra/vision/ocr/tasks) | **Nein.** Hohe Kopplung (Homestead-Familie teilt Privat-Helper, Tasks hängen an Tasks). Für das WinRT-Compile-Gewicht reicht ein Cargo-Feature. |
| Subcommand `spectre afk` in `spectre-cli` | **Nein.** `spectre-cli` zieht spectre-lua (mlua vendored, C-Build auf mingw), spectre-web, spectre-bot und tokio. Jeder Lua-/Web-Build-Bruch würde einen Bot-Hotfix blockieren, und `spectre.exe` wird von anderen Lanes ständig neu gebaut (und von `afk_memory.py` parallel genutzt → Exe-Lock beim Rebuild). |
| **Neue Crate `spectre-afk`: Lib mit Layer-Modulen + eigenes `[[bin]] spectre-afk`** | **Ja.** Eine Kompiliereinheit, Layer über Modulgrenzen und `pub(crate)` erzwungen, WinRT hinter Feature `ocr-winrt`. Abhängigkeiten nur: `spectre-mcp` (Lib, für Exec), `spectre-adb`/`spectre-core` erst ab E4b, serde/serde_json, chrono, anyhow, structopt, D1. |

Name `spectre-afk` ist ein Vorschlag (F1). Er beschreibt die Domäne und kollidiert nicht mit `spectre-bot`. Ein CLI-Alias `spectre afk …` wird nicht gebaut (braucht niemand).

### 2.2 Modulschnitt `spectre-afk`

```
spectre-afk/src/
  main.rs         [[bin]] spectre-afk: Task-Subcommands, run --scheduled|--scheduled-progress|--night,
                  Debug-Kommandos tap/key/shot (nur mit SPECTRE_AFK_LIVE=1 + gehaltenem Lock), AFK_TRACE=<file>
  lib.rs
  env.rs          Pfade/Konstanten: SPECTRE_REPO (Pflicht im geplanten Kontext), .spectre, shots-<pid>,
                  ADB-Pfad (SDK gepinnt), SERIAL, AFK_*-Env
  pystr.rs        py_splitlines/py_strip/py_isdigit/py_int/decode_lossy_py (Python-String-Semantik, §4.3)
  infra/          E1  adb.rs (Adb<R: CommandRunner>), tap.rs (TapChain/TapState, getevent/sendevent),
                      seq.rs (tap_seq/key_seq/back/tap_hold/swipe), screencap.rs (raw + PNG-Fallback, Shot-Persistenz),
                      device.rs (trait Device + AdbDevice), trace.rs (Event-Strom, §4.1)
  img/            E2  frame.rs (RGB-Frame, crop), resample.rs (Pillow-ImagingResample bitgenau), ops.rs (L-Konvert,
                      chops darker/lighter/subtract/multiply/difference/offset, invert/expand, histogram, stat mean, point),
                      png_io.rs (D1, nur IHDR/IDAT/IEND)
  vision/         E2  probe.rs (avg/close_to/lum/_pixels/_median/_clusters/_line/_centre/_ring …),
                      detect.rs (alle is_*/classify/classify_battle INKL. der dr/ar-Detektoren → bricht den Import-Zyklus),
                      coords.rs (BACK, GROUND, CONFIRM_CANCEL, BATTLE_MODES_BTN, DR_*, CARD_CLOSE, BATTLE_BTN …),
                      libm_tables.rs (nur falls nötig, §4.3)
  ocr/            E3  trait Ocr; ps1.rs (Backend A: templates/ocr.ps1), winrt.rs (Backend B, #[cfg(feature="ocr-winrt")]),
                      boxes.rs (parse_boxes, ocr_region/ocr_scaled/_crop_ocr-Preprocessing über img::resample)
  state/          E4  lock.rs (afk-bot.lock-Interop, vorgezogen in E1), idle.rs (GetLastInputInfo-FFI),
                      power.rs (power-state.json, memory_preflight/revalidate; E4a Subprozess, E4b in-proc),
                      metrics.rs (battles.jsonl, wall-report.log), markers.rs (*-last.txt), prune.rs
  flows/          E5  reach_world, open_battle_modes, resolve_startup_popup, gazette_claim, recover_leftover,
                      escape_ladder (normalize), homestead_common (tap_until, rq.read-Polling, Tap-Guards)
  tasks/          E5  claim, normalize, device_ready, arena, dream_realm, stage_push, duras, dailies, daily_gift,
                      hero_level, homestead, homestead_upgrade, homestead_requests, guild  (je 1 Datei = 1 Skript)
  runner/         E6  watch (scheduled/progress), night, Phasen, Marker, rc-Aggregation, Lock-Keeper, Log-Format
  testkit/        FakeDevice (Event-Strom), FakeOcr (name- und sequence-keyed), FakeClock (virtuelle Uhr), FakeRunner
spectre-afk/tests/parity.rs   Golden-Replay (§4)
```

Die Zuordnung **1:1 Skript → Task-Modul** gilt nur für die Tasks. `afk_claim_vision.py` ist ein God-Modul. Es wird nach Layern zerlegt, nur `main`/`claim_round` landet als `tasks/claim.rs`. Die Detektoren aus `afk_dream_realm`/`afk_arena`, die `recover_leftover` und `afk_normalize` per Lazy-Import ziehen, wandern nach `vision/detect.rs`, ebenso `sp.classify_battle`/`BATTLE_BTN` (von `afk_duras` genutzt). Damit gibt es keine Task→Task-Kante. Die privaten Homestead-Helper (`hs._pixels/_median/tap_until`, `hu._line/_centre/_tap`, `rq.read/OPEN_POLLS`) werden zu `vision::probe` bzw. `flows::homestead_common`. Die Tap-Guards (hu: kein COMPLETE_NOW, rq: kein GIVE_UP) werden **explizite Guard-Prädikate** mit eigenen Tests, denn sie sind Sicherheitsregeln.

Prozessglobaler Zustand (`TAP_MODE`, `_TAP_DEAD`, `_SENDEVENT`, die Caches von `afk_memory`, `_shot_fails`, `TMP` pro PID) wird zu einer expliziten `Session`, die der `AdbDevice` hält.

Panics: Das Workspace-Profil darf kein `panic = "abort"` für `spectre-afk` setzen. `main` fängt Panics (`catch_unwind`) und mappt sie auf den Python-rc für eine ungefangene Exception (rc 1, §4.4), nie auf 101.

### 2.3 Wiederverwendung (statt Duplikat)

| Bestehend | Verwendung |
|---|---|
| `spectre-mcp` Lib: `CommandRunner`/`SystemRunner`/`Output`/`RunError` + Fake-Runner (`lib.rs` ~L60–150) | **`spectre-afk` hängt von der `spectre-mcp`-Lib ab** (deren einzige Deps sind serde/serde_json). Binary-safe, synchron, harter Timeout mit Kill, begrenzter Pipe-Drain. Der MCP-Server wird **nicht** geändert: Er ist während des ganzen Ports der live laufende, serialisierte adb-Owner aller Sessions, und ein Lift nach `spectre-adb` würde ihm tokio und die Core-Kette aufzwingen. Ein Umzug in eine std-only Mini-Crate `spectre-exec` ist frühestens nach E7 ein eigenes Ticket. |
| `spectre-adb` `AdbReader::read_bytes`, `memory_regions`; `spectre-core` Reader/Scanner/Chain; `spectre-native` Prozessliste | Erst **E4b** (optional): In-Process statt `spectre.exe dump/read-batch` spawnen, mit Watchdog-Thread. Bis dahin (E4a) spawnt Rust das Binary wie Python. |
| `spectre-adb` `AdbReader::run_adb_shell` | **Nicht** für Input/Screencap: privat, text-only, ohne Timeout, und bei leerem stdout retryt es mit `su -c` → ein `input tap` würde doppelt ausgelöst. |
| `spectre-adb` `multi::adb_path()` | **Nicht** für den Bot: bevorzugt PATH-`adb` bzw. `HD-Adb.exe`; eine Versionsmischung startet den adb-Server neu (faktisch `kill-server`). Der Bot pinnt wie Python `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` + `-s 127.0.0.1:5555`. |
| `spectre-bot::InputSimulator`, `CliInputSimulator` | Bleiben unverändert. Optional, später, nicht im Scope: `impl InputSimulator for AdbDevice`. |
| Win32-FFI-Konvention (`wininput.rs`, `spectre-native/windows.rs`) | Für idle (`GetLastInputInfo`/`GetTickCount`). Handdeklariertes `extern "system"`, keine Dependency. |
| serde/serde_json, chrono, anyhow, tracing, structopt | Vorhanden und reichen für JSON-State, Metrics, Goldens, Zeit, CLI und Logging. |

## 3. Etappen

Jede Etappe bekommt einen eigenen Branch `feature/T1xx-…` und genau **einen lokalen Commit** (kein push). Ausnahme **E5**: **ein Branch und ein Commit pro Task-Modul** (`feature/T1xx-afk-<task>`), denn 14 Tasks auf einem langlebigen Branch wären nicht reviewbar, nicht einzeln rücknehmbar und eine Merge-Naht wie bei `af367b3`.

DoD jeder Etappe nach CLAUDE.md: `check --workspace` 0 errors, Tests der Crate grün, `clippy --workspace --all-targets` 0 warnings (Baseline heute sauber: ~274 Tests grün, 0 Warnings). Dazu **Paritätslauf `SPECTRE_PARITY=1` für den Scope der Etappe (`parity/scope/E<n>.toml`) mit 0 Fails, 0 Skips, 0 STALE** (§4). Echte Testausgabe gehört in den Bericht.

Reihenfolge: **E0a Korpus (jetzt)** → **E0b Harness/Goldens** → E1 android-infra → E2 Vision inkl. Bild-Kern → **Tracer-Bullet-Task** → E3 OCR (erst ps1, dann WinRT) → E4 State (parallel zu E2/E3 möglich) → E5 Tasks → E6 Runner → E7a Task-Flips abschließen → E7b Runner-Umschaltung.

OCR muss hinter Vision kommen, weil das OCR-Preprocessing (LANCZOS 2×/3×, Graustufen, Invert, Expand) denselben Pillow-Port braucht.

### E0a — Korpus-Snapshot (jetzt, parallel zur Queue, F3)

- **Warum jetzt:** Der Frame-Bestand schrumpft laufend. 22 referenzierte Frames sind bereits überall verloren (F16-Prune, Hermes-Überschreibungen, Storage Sense).
- **Inhalt:** Ein kleines Python-Skript (stdlib+PIL, Test-Tooling) sammelt jedes Bild, das die Suite als Fixture referenziert, plus die Dateiliste von `.spectre` (Pfad, Größe, sha16) für den späteren Differential-Lauf (E2). Jedes Bild wird verlustfrei als `<sha16 über mode+size+RGB-Bytes>.png` abgelegt.
- **Ablage außerhalb jedes Repos:** `C:/Users/Sigi/spectre-parity/frames/` (Pfad per `SPECTRE_PARITY_DIR`), nach dem Export schreibgeschützt. Kein `git clean` einer Lane und kein vergessener `.gitignore`-Eintrag kann ihn treffen. **Zweite Kopie** als Zip an einem Ort, den der User festlegt (F3). Committet werden nur `parity/frames.json` (sha16, Ursprungspfad, Größe) und `parity/spectre-filelist.json` (eingefrorene Liste für E2).
- **Prüfung:** `scripts/tests/parity/verify_corpus.py` (Python, berechnet sha16 neu) meldet fehlende oder veränderte Dateien gegen `frames.json` als FAIL. Es läuft vor jedem Paritätslauf unter `SPECTRE_PARITY=1`.
- **Schreibt nichts nach `.spectre`, braucht kein Gerät.** Größe ~0,5 Tag.

### E0b — Harness und Goldens (nach der Queue, vor E1)

- **Exporter** `scripts/tests/parity/export_goldens.py` (neues Python-Test-Tooling, F6). Die bestehende Suite bleibt unverändert. Er installiert die Recorder und läuft danach `unittest discover`, im Main-Checkout, unter Windows, ohne die Bash-Wrapper-Tests (die laufen in E6 getrennt).
  - **Virtuelle Uhr:** `sleep(s)` rückt sie vor; `time.time`/`monotonic`/`datetime.now` in den Bot-Modulen lesen daraus. Jede Lesung ist ein `now`-Event. Tests mit eigener `side_effect`-Liste werden als Clock-Skript übernommen, sonst `manual`. Vorab: Suite unter virtueller Uhr grün, Abweichler explizit gelistet.
  - **Flow-Recorder** (Hook auf FakeDevice und auf `afk_claim_vision.adb/shot/tap`): schreibt pro Device **einen geordneten Event-Strom** (Schema §4.1), dazu Entry-Fn, argv, Overrides, `fs_after` (alle Pfade auf eine Sandbox-Wurzel gebogen: battles.jsonl, wall-report.log, `*-last.txt`, power-state.json, Lock), vollständiges stdout mit Liste der Vertragszeilen, rc.
  - **Call-Recorder** für reine Funktionen (`classify*`, `is_*`, `find_*`, `read_*`, `parse_*`, `avg`, `lum` …). Er wrappt in **allen** geladenen Bot-Modulen jedes Attribut, das per `id()` auf die Funktion zeigt (auch `from … import f`). Selbsttest per `sys.setprofile`: Recorder-Zähler == Profil-Zähler, sonst FAIL mit Funktionsname. Argument-Hash vor/nach dem Aufruf: Bei Mutation, oder wenn die Funktion intern tap/shot/ocr aufruft, geht der Record nach `flows`, nicht nach `calls`.
  - **OCR-Recorder:** Bild-sha16, argv, **rohe stdout-Bytes (base64)**, rc, Timeout-Flag → `ocr.jsonl` als eingefrorenes Fixture.
  - **argv-Recorder** für gemockte `subprocess.run`/adb-Aufrufe der Infra-Tests → `argv.jsonl`.
  - **Fault-Injection** pro Task-Entry: FakeDevice wirft an Event k `OSError`/`TimeoutExpired`/`CalledProcessError` bzw. liefert adb rc≠0; dazu „Lock gehalten“ (rc 7) und „Idle-Skip“ (rc 5) → `faults.jsonl` {Task, Fehlerart, Position → rc, Vertragszeilen}.
  - **libm-Tabellen:** Ausgaben von `afk_homestead_upgrade.py` L432 (`round(r*cos/sin)`), L518 (`round(atan2/(pi/4))%8`) und `afk_homestead_requests.py` L476 (`math.dist`) über die gesamte ganzzahlige Eingabedomäne → `libm.jsonl`.
  - **String-Semantik-Tabelle:** synthetische Bytes (GBK-Umlaute, CR-only, `\x0c`, `\x85`, `²`, `-0`, Leerzeilen) durch `ocr_png`-Dekodierung und `parse_boxes` → `pystr.jsonl`.
  - **Ledger** `parity/ledger.json`: Jede Test-ID zeigt auf `{records}` | `{manual: rust_test, asserts: n}` (per AST extrahiert) | `{dead: Grund}` | `{out_of_scope}`. Zweigabdeckung der Bot-Module per stdlib `trace`/`sys.settrace`; unbelegte Zweige werden Shadow-Replay-Ziele.
  - **Determinismus-Guard:** zweimal exportieren (mit virtueller Uhr ist das jetzt aussagekräftig), abweichende Records markieren.
- **Golden-Header** in jeder Datei: `{v:1, py_tree (git tree-hash scripts/+templates/), python, pillow, windows_build, ocr_ps1_sha}`.
- **Goldens werden committet**, pro Modul gesharded und dedupliziert, damit sie als JSONL reviewbar bleiben (keine gz-Variante, sonst würde flate2 direkte Dependency). Regeneriert wird nur absichtlich; ein Golden-Diff gilt als Python-Verhaltensänderung.
- **Re-Export-Regel:** am Start jeder Etappe und nach jedem Queue-Merge, der `scripts/` oder `templates/` ändert. Der Golden-Diff ergibt die Liste der betroffenen Rust-Module (Follow-up). **Freeze-Regel:** Ist ein Task in Rust grün, geht eine Python-Änderung daran nur mit gleichzeitigem Rust-Patch durch, sonst wird die Parität des Tasks als ungültig markiert.
- **Rust-Skelett:** Crate `spectre-afk` (leer bis auf `testkit` und `tests/parity.rs`). Der Loader liest die JSONL, prüft jeden Frame auf Existenz, Größe und Pixelmaße gegen `frames.json` und dispatcht über eine Tabelle `py-fn → rust-fn`. Nicht gemappte Funktionen zählen als *unported* → Coverage pro Modul.
- **Exit:** Export zweimal deterministisch; Bericht mit Records pro Datei, Ledger-Bilanz (records/manual/dead/out_of_scope), Ziel **< 20 `manual`-Tests**, Dead-Specs, Zweigabdeckung. `parity.rs` lädt alles und meldet die Coverage (anfangs 0 %).
- **Größe:** 6–8 Tage (Recorder über ~900 Tests, Konflikte mit selbst patchenden Tests, virtuelle Uhr, Fault-Injection, Ledger). **Gate:** D1 (der Rust-Loader liest PNG).

### E1 — android-infra

**Scope:** Alles zwischen Python und `adb.exe`, ohne Vision und OCR. Python-Referenz: `scripts/afk_claim_vision.py` L486–L720 (`adb`, Tap-Modi L493–635, `_run_seq/tap_seq/key_seq` L637–670, `back` L672, `tap_hold`, `swipe`, `_raw_to_image` L697, `shot` L709).

| Rust (Datei → Funktion/Typ) | Python-Vorbild | Anmerkung |
|---|---|---|
| `spectre_mcp::{CommandRunner, SystemRunner, Output, RunError}` + Fake-Runner | `spectre-mcp/src/lib.rs` L60–150 | Als Lib-Dependency genutzt, **nicht verschoben**. MCP bleibt unberührt. |
| `env.rs`: `adb_bin()`, `SERIAL`, `repo_root()`, `shots_dir(pid)`, `tap_mode_env()` | `REPO`, `ADB`, `SERIAL`, `TMP`, `AFK_TAP_MODE` | `repo_root`: Env `SPECTRE_REPO`, im geplanten Kontext **Pflicht** (fehlt sie → rc 2 mit klarer Meldung). Keine `current_exe()`-Heuristik, weil das Binary aus einem Install-Pfad läuft (E7). |
| `infra/adb.rs`: `Adb<R>::shell(args, timeout)`, `exec_out(args, timeout)` | `adb()` (Timeout 30 s, Screencap 60 s) | Immer `-s SERIAL`, **kein** `adb connect` und **kein** `adb devices` pro Aufruf. |
| `infra/tap.rs`: `enum TapMode {Tap, Touchscreen, Sendevent}`, `TAP_CHAIN`, `TapState`, `parse_getevent()`, `sendevent_cmds()`, `tap_cmd()`, `tap()`, `tap_retry()`, `tap_result()`, `fmt_g()` | gleichnamig | Reine Funktionen 1:1. `fmt_g` = Pythons `{:g}`. `round()` = Banker's Rounding → `f64::round_ties_even`. MT-Protokoll B und A. Root-Check `su -c id` einmal pro Session. |
| `infra/seq.rs`: `run_seq()`, `tap_seq()`, `key_seq()`, `back()`, `tap_hold()`, `swipe()` | gleichnamig | Eine `adb shell`-Zeile mit `;`-verketteten Befehlen und `sleep W` (Timeout = Summe der Waits + 15 s). Argv-Form exakt wie Python: `_press` übergibt `*line.split()`, `_run_seq` **ein** Argument. |
| `infra/screencap.rs`: `raw_to_frame(&[u8]) -> Option<Frame>`, `shot(name)` | `_raw_to_image`, `shot` | Header 12 oder 16 Byte, nur `fmt==1`, `len == hdr+w*h*4`, `0<w,h<=8192`, RGBA→RGB wie PIL. Fallback `exec-out screencap -p` → PNG-Decode. Shot-Persistenz `shots-<pid>/<name>.png`; nur Pixel müssen gleich sein, PNG nur mit IHDR/IDAT/IEND (kein gAMA/sRGB/iCCP/cHRM, wie PIL). **Braucht D1.** |
| `img/frame.rs` (minimal): `Frame {w, h, rgb}`, `crop()` | PIL `Image` (RGB) | Rest in E2. |
| `infra/device.rs`: `trait Device` + `AdbDevice` | Modul-Globals von `v` | Methoden folgen den Python-Signaturen: `shot`, `tap` (→ genutzter Modus), `tap_seq`, `key_seq`, `tap_hold`, `swipe`, `back`, `sleep`, `now`. `sleep`/`now` laufen über die injizierte Uhr. Jede Methode erzeugt ein Event (§4.1); `AFK_TRACE=<file>` schreibt es live mit. |
| `testkit`: `FakeDevice`, `DeadTapDevice`, `FakeClock` | `scripts/tests/fake_vision.py` | Gleiche Guards (ungescripteter Shot = Fail, Key 4 auf WORLD = Fail). Der synthetische `_SPEC`-Renderer wird **nicht** portiert; die materialisierten PNGs des Korpus sind die Fixture. |
| `main.rs`: `spectre-afk tap <x> <y> [--mode]`, `key <code>`, `shot <name>` | – | Nur für den Live-Smoke durch Hermes. Laufen nur mit `SPECTRE_AFK_LIVE=1` und nehmen `afk-bot.lock`; ohne beides rc 2. Kein bequemer dritter adb-Client für beliebige Sessions. |

**Vorgezogen aus E4:** `state/lock.rs`. Jeder Live-Aufruf muss den Lock respektieren. Byte-kompatibel: gleicher Pfad, PID als Text, mtime-Staleness `AFK_LOCK_STALE` = 3600, `AFK_BOT_LOCK_HELD` erben, Release nur bei eigener PID. TOCTOU bleibt wie in Python, **kein** `create_new` (PY-NOTE-06).

**Tests (Specs):** alle Records aus `test_tap_mode`, `test_tap_seq`, `test_input_robustness`, `test_fast_shots` (RAW_HEADERS 12/16), den Infra-Teilen von `test_adb_bench`, `test_zombie_recovery`, `test_review_fixes` und `test_bot_lock`. Dazu Rust-Unit-Tests für `fmt_g`, `round_ties_even`, die Grenzen von `raw_to_frame`, PNG-Chunk-Liste, Lock-Interop in beide Richtungen (Python legt an → Rust erkennt, Rust legt an → `_bot_lock.py` erkennt) und Exec-Timeout/Kill mit dem Fake-Runner.

**Exit-Kriterium E1:**
1. 100 % der E1-Records gleich: argv-Sequenzen exakt (inkl. sendevent-Batches und Fallback-Kette tap → touchscreen → sendevent mit `_TAP_DEAD`), Event-Strom exakt.
2. `raw_to_frame` liefert auf denselben Bytes RGB byte-identisch zu PIL.
3. Gleiche Fehlersemantik (rc≠0 „device offline“ wird toleriert), Fault-Records der Infra grün.
4. **Live-Smoke durch Hermes** (nicht Claude), in einem reservierten Fenster der Live-Lane bei gestopptem MCP-adb-Verkehr (F9): Hermes schneidet einmal die Raw-Bytes mit (`exec-out screencap` in eine Datei) plus `-p` vom selben statischen Screen. Offline wird `raw_to_frame` gegen `_raw_to_image` byte-exakt verglichen; live geprüft werden Header-Form und Größe. Pixelgleichheit raw vs. `-p` wird nur gefordert, wenn zwei aufeinanderfolgende Raw-Captures identisch sind (sonst Animation). N=20 Taps pro Modus: Moduswahl und Fallback werden über die Traces (`AFK_TRACE` vs. Python-Recorder, F5) verglichen. Damit ist der bisher „LIVE: header unverified“ markierte Raw-Pfad belegt.
- Python wird nicht verändert.

**Größe:** 3–4 Tage.

### E2 — Bild-Kern und Vision

- **Inhalt:** `img/resample.rs` portiert Pillows `ImagingResample` der gepinnten Version (horizontaler und vertikaler Pass, `precompute_coeffs`, `normalize_coeffs_8bpc`, 22-Bit-Präzision, clip8) für BILINEAR, BOX und LANCZOS, ~150 LOC, nur std. `img/ops.rs` enthält genau die genutzten Operationen (`convert('L')` = `(r*19595+g*38470+b*7471+0x8000)>>16`, ImageChops, Invert, Expand, Histogramm, Stat-Mittelwert, `point`, `split`). `vision/*` enthält alle Probes und Detektoren. `lum()` und Ratios in f64 mit derselben Operationsreihenfolge.
- **libm:** Die drei libm-Stellen (s. E0b) werden gegen `libm.jsonl` getestet. Bei auch nur einem Diff (mingw/UCRT-libm vs. MSVC-CRT) nutzt Rust die exportierte Tabelle als `const` mit `py-parity`-Notiz.
- **Specs:** `calls.jsonl` aller Vision-Funktionen, die 62 Einträge von `frame_manifest.json`, alle A/B-Detektortests.
- **Exit:**
  1. 100 % der Vision-Records gleich. Strings, Bools, Ints, Koordinaten exakt; **Floats bit-exakt** (repr-Roundtrip), weil gleiche Operationsreihenfolge IEEE-gleiche Werte liefert. `libm.jsonl` 100 %.
  2. **Korpusweiter Differential-Lauf** über die in E0a eingefrorene `.spectre`-Dateiliste (fehlende Dateien werden gezählt, nicht still übersprungen): alle reinen Vision-Funktionen der Dispatch-Tabelle (alle `is_*`/`find_*`/`read_*`, `avg` an jeder Probe-Koordinate jedes Detektors) sowie das OCR-Preprocessing (`ocr_scaled`, `_crop_ocr`, ocr_region-Crop; verglichen per sha16 der Ausgabebilder). Ergebnis: Diff-Zähler pro Funktion, Exit = 0.
- **Größe:** 6–8 Tage. Der Resample-Port allein braucht 2–3 Tage und ist das größte Paritätsrisiko.

### Tracer-Bullet (direkt nach E2)

Portier- und Flip-Reihenfolge werden getrennt. Direkt nach E2 wird **ein Task ohne OCR und ohne Memory** end-to-end bis zur Live-Akzeptanz gebracht, bevor E3/E4 fertig sind. Kandidat ist `arena` (0 OCR-Treffer); falls der Ledger dort Memory/Power-Abhängigkeiten zeigt, `normalize` oder `device_ready` (je 1 `ocr`-Treffer, der dann über E3a nachgezogen wird). Er durchläuft den kompletten E5-Exit (unten) und validiert Harness, Trace-Schema, Shadow-Replay und Dispatch-Hook früh. `claim` wird früh **portiert** (die `flows/*` hängen daran), aber **zuletzt geflippt**, weil es jeden Daily-Run eröffnet und den größten Blast-Radius hat.

### E3 — OCR

- **E3a (Pflicht):** `ocr/ps1.rs` ruft `templates/ocr.ps1` wie Python auf (`powershell -NoProfile -ExecutionPolicy Bypass -File … -Path <png> [-Boxes]`, Timeout 20 s, `[]` bei Fehler bzw. die `check_rc`-Variante für stage_push). Dekodierung über `pystr::decode_lossy_py` (Ersetzungsverhalten wie Pythons `errors='replace'`, belegt durch `pystr.jsonl`), dann `py_splitlines`/`py_strip`, `parse_boxes` mit `py_isdigit`/`py_int` statt std (`str::lines`, `char::is_whitespace`, `is_ascii_digit` weichen still ab). Preprocessing (`ocr_region`, `hs.ocr_scaled`, `hero_level._crop_ocr`) über `img::resample`.
- **E3b (optional, nach Freigabe von D2):** `ocr/winrt.rs` hinter Feature `ocr-winrt`, `TryCreateFromUserProfileLanguages` (de-DE), SoftwareBitmap. Zuerst das gespeicherte PNG dekodieren wie ps1, In-Memory-Bitmap erst nach A/B. Boxes mit `round_ties_even` (.NET `[int]` ist Banker's Rounding), w/h aus Float-Extents. **Spike zuerst:** Baut die `windows`-Crate auf der GNU-Toolchain? Indizien dafür (windows-link/raw-dylib baut schon), getestet ist es nicht.
- **Specs:** `ocr.jsonl` (eingefrorene Roh-Bytes), `pystr.jsonl` und die O-Tests (hall_direct, homestead RealCounter, build_all RealQuest/Queue/TileName, upgrade OCR, level_preview cost_pairs).
- **Exit E3a:**
  1. **Byte-exakt, ohne Normalisierung**, deterministisch gegen FakeRunner auf den eingefrorenen stdout-Bytes: 100 % von `ocr.jsonl` und `pystr.jsonl`.
  2. Preprocessing pixelgleich zu PIL.
  3. ps1-OCR auf dem Rust-PNG == ps1-OCR auf dem PIL-PNG derselben Pixel (Text und Boxen exakt) auf ≥ 20 OCR-Korpus-Frames.
  4. Separater Tier `SPECTRE_PARITY_OCR_LIVE=1`: ruft `ocr.ps1` neu auf und meldet Engine-Drift (Windows-Build, Sprachpaket, Codepage). Das ist ein Umgebungsbefund mit Golden-Regeneration, kein Rust-Fail. Hermes belegt den Codepage-Pfad einmal live im echten `.vbs`-/Task-Scheduler-Kontext.
- **Exit E3b (Entscheidungsebene):** Alle OCR-Konsumenten (Parser für Zähler, Kosten, Tile-Namen, Quests) und alle Flows mit OCR-Events laufen einmal mit ps1- und einmal mit WinRT-Ausgabe über Korpus und Flows. Gefordert: **0 Diffs in geparsten Werten und im Event-Strom.** Rohtext-Diffs sind informativ; ±1 px bei Boxen ist erlaubt, solange keine abgeleitete Tap-Koordinate abweicht. Erst dann wird B Default; ps1 bleibt Fallback und Orakel.
- **Gewinn mit B:** 1,6–3,5 s pro OCR-Aufruf (gemessen, fast nur PowerShell-Start) → geschätzt 0,1–0,5 s, bei ~55 Call-Sites.
- **Größe:** E3a 1–2 Tage, E3b 2–3 Tage.

### E4 — State/Misc (parallel zu E2/E3 möglich)

- **E4a (Pflicht):** `idle.rs` (`GetLastInputInfo` + `GetTickCount`, `wrapping_sub`, `None` bei Fehler → fail-open wie Python), `power.rs` (power-state.json atomar mit tmp+rename, `drift_window`, `scan_slots`, `revalidate_power_offset`, `memory_preflight`; `afk_memory.snapshot/power` **spawnt `spectre.exe dump/read-batch/find/regions` wie Python** mit gleicher Fallback-Kette, gleichen Timeouts und Kill), `metrics.rs` (battles.jsonl, wall-report.log mit identischen Keys und Typen, weil Tray und wall-dash sie lesen), `markers.rs` (UTC-Datum), `prune.rs` (30 behalten, 14 Tage Trash).
- **E4b (optional, nach A/B):** In-Process über `spectre-adb`/`spectre-core` mit Watchdog-Thread (ein hängender Read lässt sich in-process nicht abbrechen; der Nested-tokio-Workaround in `AdbReader` ist ein Warnsignal). Erst Default nach A/B-Lauf gleicher `power`-Werte auf denselben Dump-Files.
- **Specs:** `test_metrics`, `test_hero_timing`, Idle-Teile von `test_review_fixes`, Marker-Teile von `test_duras`/`test_review_gaps`, `test_afk_memory` (Subprozess-argv in E4a, DumpFileReader in E4b), `fs_after`-Teile der Flow-Goldens.
- **Exit:** `calls.jsonl` und `fs_after` mit virtueller Uhr gleich (JSON/JSONL nach Key-Set, Typen und Werten exakt). JSON-Dateien lassen sich mit Python wechselseitig lesen.
- **Größe:** E4a ~2 Tage, E4b 1–2 Tage.

### E5 — Flows und Task-Module

- **Portier-Reihenfolge** nach Abhängigkeit: `flows/*` + claim (Port) → normalize → device_ready → arena (falls nicht schon Tracer) → dream_realm → stage_push → duras → dailies → daily_gift → hero_level → homestead → homestead_upgrade → homestead_requests → guild. **Flip-Reihenfolge** nach Risiko: Tracer zuerst, `claim` zuletzt.
- **Pro Task:** eigener Branch, ein Commit, `spectre-afk <task>` mit derselben argv-Schnittstelle und demselben Exit-Code-Vertrag: 0 ok, 1 stuck/ungefangene Exception, 2 adb/preflight, 3 Crash/Gift-WARN, 4 nichts zu tun, 5 Idle-Skip, 7 Lock gehalten. Der Lock wird wie im jeweiligen Python-Skript genommen; `daily-gift` nimmt ihn heute **nicht** (PY-NOTE-04).
- **Exit pro Task:**
  1. Alle Records des Moduls in `flows.jsonl` gleich: **vollständiger Event-Strom** (§4.1), rc, `fs_after`, stdout-Vertragszeilen.
  2. `faults.jsonl` des Tasks: 0 Abweichungen.
  3. Die `manual`-Tests des Moduls sind als Rust-Tests portiert, tragen `// py: <test_id>` und mindestens dieselbe Assert-Zahl wie im Ledger; das Review vergleicht beides.
  4. **Shadow-Replay**: N ≥ 5 aufgezeichnete Live-Python-Runs (§4.5) laufen in Rust als FakeDevice durch, Vergleich des **vollständigen Event-Stroms bis Run-Ende plus rc**, sequence-keyed. 0 Divergenzen. Jede `ocr_region`-Call-Site des Tasks ist in mindestens einem Shadow-Run getroffen oder als bewusstes Risiko gelistet.
  5. **Live-Akzeptanz**: K ≥ 3 Live-Runs `spectre-afk <task>` durch Hermes, mit `AFK_TRACE`. Kriterien: rc im erwarteten Set, 0 Guard-Verletzungen (kein keyevent 4 auf WORLD, kein COMPLETE_NOW-/GIVE_UP-Tap), Endzustand per `classify` WORLD. **Reverse-Shadow:** Jeder Rust-Trace wird offline mit Python-FakeDevice abgespielt, 0 Divergenzen. Erst damit belegt ein Live-Run Parität (Python und Rust laufen nie auf demselben Spielzustand).
  6. Goldens == aktueller Python-Stand (kein STALE).
- **Ohne Live-Recorder (F5 abgelehnt)** fällt Kriterium 4 weg; dann sind Reverse-Shadow-Runs (5) der einzige Live-Paritätsbeleg und K wird auf ≥ 5 erhöht. Das gilt dann ausdrücklich als schwächere Absicherung.
- **Größe:** 15–20 Tage. Homestead-Familie und Guild sind am teuersten (viel OCR, Kamera-Suche, Guards).

### E6 — Runner

- **Inhalt:** `runner/` ersetzt die Logik von `afk-bot-watch.sh` (372 LOC) und `afk-night.sh` (103 LOC):
  - PID über `spectre-native` statt `spectre find`.
  - Heap-Basis = größte anonyme rw-Region mit `s>>44==7` (ersetzt die doppelte Python-Heredoc).
  - Lock-Keeper als Thread mit `set_modified` alle 240 s.
  - `AFK_*`-Env-Gates, Phasenreihenfolge, `record_daily_failure`-rc-Aggregation, `*-last.txt`-Marker, Tageslog `.spectre/logs/afk-bot-YYYY-MM-DD.log` (UTC; `spectre-tray.ps1` parst die `=== … watch start`-Zeilen → Vertrag).
  - device-ensure mit Timeout 600; Exit-Codes 1/2/3/5/6/7/9.
- `device-ensure.sh` und `bluestacks-ensure.sh` bleiben Bash und werden als Subprozess aufgerufen. `device-ensure.sh` ruft `spectre-afk device-ready` erst nach dessen Flip.
- **Specs:** In E0b (Bash-Teil) wird aus den Wrapper-Tests `runner.jsonl` aufgezeichnet: Reihenfolge der Task-Aufrufe mit argv, `AFK_*`-Env und cwd, Log-Vertragszeilen, Marker, aggregierter rc. Dazu eine **generierte Szenario-Matrix** über watch.sh/night.sh: rc jeder Phase in {0,1,2,3,4,5,7} × Idle ja/nein × Lock gehalten × `AFK_*`-Gates (paarweise reduziert, falls das Kreuzprodukt zu groß wird; die Reduktion steht im Bericht). Die Bash-Läufe sind die Goldens.
- **Die Wrapper-Tests werden nicht umgeschrieben**, sondern parametrisiert: Sie laufen gegen **beide** Implementierungen (watch.sh und Rust-Runner mit Fake-Task-Dispatcher), bis E7b grün ist. So bleibt das Bash-Orakel erhalten.
- **Exit:** Matrix und `runner.jsonl` 100 % gleich, Exit-Code-Tabelle identisch, Tray-Vertragszeilen identisch. Andere Prints dürfen sich ändern.
- **Größe:** 3–4 Tage.

### E7 — Umschalten und Archivieren

**Install statt `target/release`:** Das Binary für geplante Runs kommt nie aus `C:\Users\Sigi\spectre\target\release\`. Dort bauen parallele Lanes (stiller Austausch des Binaries; während eines Runs schlägt deren Build am Exe-Lock fehl). Stattdessen kopiert ein Install-Schritt ein getestetes Binary nach `C:/Users/Sigi/spectre-bin/afk/<git-sha>/spectre-afk.exe`. Aufrufer zeigen auf genau diesen Pfad, mit explizit gesetztem `SPECTRE_REPO`. Rollback = vorherigen SHA-Pfad eintragen. (Dasselbe Problem hat heute schon `afk_memory.py:35` mit `REPO/target/release/spectre.exe`, PY-NOTE-20.)

- **E7a — Task-Flips (laufen schon ab dem Tracer):** Der Dispatch-Hook in `watch.sh` (§5) bekommt pro Task nach dessen E5-Exit den Task in `AFK_RUST_TASKS`. Runner bleibt Bash, `.vbs` und `.cmd` bleiben. **Exit E7a:** alle 14 Tasks in `AFK_RUST_TASKS`, danach K ≥ 7 aufeinanderfolgende grüne geplante Runs pro Run-Typ (Daily, Progress, Night).
- **E7b — Runner-Umschaltung:** Erst danach zeigen die 3 `.vbs` (bleiben, weil sie Console-Flackern verhindern) auf `spectre-bin/afk/<sha>/spectre-afk.exe run --scheduled|--scheduled-progress|--night`. Task-Scheduler-Definitionen bleiben unverändert (Interactive Logon ist Pflicht für das Idle-Gate). **Exit E7b:** erneut K ≥ 7 aufeinanderfolgende grüne geplante Runs pro Run-Typ, nur mit diesem einen Wechsel.
- **Erst nach E7b:** `.cmd` löschen, Python nach `scripts/archive/` (nicht löschen), Tests, Goldens und Exporter bleiben als Orakel.
- **Rollback:** E7a: Task aus `AFK_RUST_TASKS` nehmen. E7b: 3 `.vbs`-Zeilen zurück auf die `.cmd` (die bis dahin existieren).
- **Größe:** 1–2 Tage plus Beobachtungszeitraum.

### 3.9 Aufwand und Kalender

| Etappe | Agent-Tage |
|---|---|
| E0a | 0,5 |
| E0b | 6–8 |
| E1 | 3–4 |
| E2 | 6–8 |
| E3a / E3b | 1–2 / 2–3 |
| E4a / E4b | 2 / 1–2 |
| E5 (inkl. Tracer) | 15–20 |
| E6 | 3–4 |
| E7 | 1–2 |
| **Summe** | **~40–55 (±50 %)** |

**Der kritische Pfad ist Live-Lane-Zeit, nicht Agent-Zeit.** Gefordert sind grob 14 Tasks × (N ≥ 5 Shadow + K ≥ 3 Live) ≈ 112 Hermes-Runs. Homestead, Guild und Dream Realm laufen einmal pro Tag, Arena und Duras nur begrenzt oft. E7a und E7b brauchen je ≥ 7 aufeinanderfolgende Tage pro Run-Typ; jeder Fehlschlag setzt den Zähler zurück.
- **Bündeln:** Mit dem Live-Recorder (F5) liefert *jeder* geplante Daily-Run Shadow-Aufnahmen für alle Tasks gleichzeitig. Ab dessen Einbau sammeln sich die N ≥ 5 Shadow-Runs in ~1 Woche nebenher.
- **Live-Akzeptanz:** grob 1–2 Wochen pro Task-Gruppe (Infra/Tracer, Kampf-Tasks, Dailies, Homestead-Familie, Guild, claim).
- **Kalender gesamt:** realistisch **3–4 Monate** ab E0b-Start. Hermes-Budget: ca. 2–4 Live-Fenster pro Woche à 30–60 min für Smoke und Live-Akzeptanz (F7).

## 4. Paritätskriterium und Harness

**Prinzip:** Spezifikation ist das **aufgezeichnete Verhalten** von Python in einem **geordneten Event-Strom**, nicht die Asserts. Asserts prüfen oft nur Teilmengen (`taps[0]`, Substrings), und FakeDevice führt `taps`/`shots` heute als getrennte Listen ohne Waits.

### 4.1 Event-Schema (gemeinsam für Goldens, Shadow-Replay und `AFK_TRACE`)

```
events: [
  {shot, name, frame}             {tap, x, y, mode, wait}       {seq, steps: [[x, y, w], …]}
  {key, code, w}                  {hold, x, y, ms, wait}        {swipe, …}
  {sleep, s}                      {now, src, val}               {ocr, fn, name, box?, img?, out}
  {adb, argv, rc}
]
```

Verglichen wird **exakt auf diesem Strom**; `taps`/`shots` sind nur abgeleitete Sichten. Ein Live-Python-Run mit Recorder und ein Rust-Run mit `AFK_TRACE` erzeugen dasselbe Schema, ein Live-Trace **ist** damit ein Flow-Record.

### 4.2 Dateien

| Datei | Inhalt | Rust-Gegenstück |
|---|---|---|
| Header jeder Datei | `{v:1, py_tree, python, pillow, windows_build, ocr_ps1_sha}` | STALE-Prüfung |
| `argv.jsonl` | adb-/powershell-argv-Sequenzen der gemockten Subprozesse | `FakeRunner`-Transkript |
| `calls.jsonl` | `{"fn":"afk_claim_vision.classify","args":[{"img":"<sha16>"}],"kwargs":{},"out":"WORLD","test":"…"}`, dedupliziert, pro Modul gesharded | Dispatch-Tabelle in `tests/parity.rs` |
| `flows.jsonl` | Entry, argv, Overrides, Device-Typ, `events`, `fs_after`, stdout + Vertragszeilen-Liste, rc | `FakeDevice` + Task-Entry |
| `faults.jsonl` | {Task, Fehlerart, Position → rc, Vertragszeilen} | Fault-Injection im `FakeDevice` |
| `ocr.jsonl` | Bild-sha16, argv, stdout-Bytes (base64), rc, Timeout-Flag | `ocr::ps1` gegen FakeRunner |
| `pystr.jsonl`, `libm.jsonl` | Byte→String-Semantik; libm-Ausgaben über die ganze Eingabedomäne | `pystr.rs`, `vision` |
| `runner.jsonl` + Matrix | Task-Aufrufe, Env, Log-Vertragszeilen, Marker, rc | Rust-Runner mit Fake-Dispatcher |
| `ledger.json`, `scope/E<n>.toml` | Test-ID → records/manual/dead/out_of_scope; Scope je Etappe | Vollständigkeitsprüfung |
| `frames.json` + Korpus | sha16 → PNG, außerhalb jedes Repos | Loader über `SPECTRE_PARITY_DIR` |

### 4.3 Vergleichsregeln

- Strings, Ints, Bools, Koordinaten **exakt**. Tupel → Arrays, None → null.
- Floats aus reiner Arithmetik **bit-exakt** (repr-Roundtrip). libm-Ergebnisse über die exportierte Tabelle (§E2).
- OCR in den Offline-Goldens **byte-exakt ohne Normalisierung** (eingefrorene Roh-Bytes). Normalisierung bzw. Entscheidungsebene nur im Live-Tier und für E3b.
- Python-String-Semantik ausschließlich über `pystr.rs` (`splitlines` trennt auch an `\r`, `\v`, `\f`, `\x1c–\x1e`, `\x85`, U+2028/9; `isspace` kennt `\x1c–\x1f`; `isdigit`/`int` akzeptieren Unicode-Ziffern wie `²`).
- `fs_after`: JSON/JSONL nach Key-Set, Typen und Werten exakt (virtuelle Uhr). stdout: Vertragszeilen exakt, Rest informativer Diff.

### 4.4 Modi und Vollständigkeit

- Normales `cargo test`: fehlender Korpus → lauter Skip mit Zählung.
- `SPECTRE_PARITY=1`: **FAIL** bei fehlendem oder in Größe/Maßen abweichendem Frame (sha-Abweichung meldet `verify_corpus.py`), bei *unported* Funktion im Scope, bei Skip > 0, bei einer Scope-Test-ID ohne grüne Zuordnung im Ledger und bei **STALE** (`py_tree` ≠ aktueller Main-Stand).
- Exit-Codes: Python-Exception → rc 1; Rust `main` mappt Panics auf denselben rc. `faults.jsonl` muss 0 Abweichungen haben.
- Jeder Etappenbericht nennt Coverage pro Modul (ported/unported/manual), Ledger-Bilanz und unbelegte Python-Zweige (Shadow-Ziele).

### 4.5 Shadow-Replay und Live

- **Shadow-Replay:** Python-Live-Run mit Recorder (`AFK_RECORD=<dir>`, F5) → Rust spielt Frames, OCR-Antworten (sequence-keyed), Memory-/Power-Reads, Uhr und adb-rc ab → vollständiger Event-Strom-Vergleich bis Run-Ende plus rc.
- **Reverse-Shadow:** Rust-Live-Run mit `AFK_TRACE` → Python-FakeDevice spielt ab → 0 Divergenzen.
- **Live-Runs** sind Akzeptanz (rc-Set, Guards, Endzustand), keine Paritätsprüfung für sich.

**Die Regel „kein Umschalten vor grün“ heißt konkret:** Paritätslauf im Scope mit 0 Fails, 0 Skips, 0 STALE, plus die Live-Kriterien der Etappe (E1 Smoke, E5 Shadow + Reverse-Shadow + Akzeptanz, E7a/E7b je K geplante Runs). Belege sind Zahlen (Record-, Diff-, Event-Zähler, rc), keine Screenshots.

**Dead Specs:** Die 22 überall verlorenen Frames werden im E0b-Bericht gelistet. Ersatz nur, wenn Hermes Frames desselben Screens liefert.

## 5. Umschalt-Strategie (Strangler)

1. **Während der Fix-Queue läuft:** Python bleibt maßgeblich, neue Bot-Arbeit landet erst nach der Queue in Rust. Nur E0a (Korpus-Snapshot, offline, read-only auf `.spectre`) läuft schon jetzt (F3).
2. **Ein generischer Dispatch-Hook statt 14 Edits:** Nach Ende der Queue wird **einmal** eine Funktion `run_py_or_rust <task> <args…>` in `afk-bot-watch.sh` (und `afk-night.sh`) eingebaut. Sie prüft `AFK_RUST_TASKS` (Komma-Liste, Default leer) und ruft dann `spectre-bin/afk/<sha>/spectre-afk.exe <task>` statt Python. Abgesichert durch `bash -n`, einen eigenen Test und einen Snapshot-Test, dass bei leerer Liste exakt derselbe Python-argv entsteht (Matrixzeile in `runner.jsonl`). Danach ändert ein Flip nur den Wert von `AFK_RUST_TASKS` (in einer Env-Datei, die watch.sh liest), nicht watch.sh selbst. Der Live-Recorder `AFK_RECORD` (Opt-in in `afk_claim_vision.adb/shot/tap`, mit Test) wird im selben Zug als letzter Queue-Eintrag oder durch Hermes eingebaut (F5).
3. **Per-Task-Flip ist Plan-Default** (F4, Bestätigung nötig): Jeder Task geht nach seinem E5-Exit per `AFK_RUST_TASKS` in den geplanten Run. Das vermeidet den Big-Bang „14 Tasks + Runner + Binary-Pfad auf einmal“. `.vbs`, `.cmd` und Task-Scheduler-Tasks bleiben dabei unverändert bis E7b. Lehnt Hermes das ab, schaltet E7a alle Tasks in einem Zug über den Hook um, E7b bleibt getrennt.
4. **Gemischter Betrieb:** Python und Rust teilen `afk-bot.lock`, `power-state.json`, Marker und Metrics. Die Interop-Tests (E1/E4) und `fs_after`-Goldens sind deshalb Pflicht.
5. **adb-Ownership:** Rust ruft `adb.exe` direkt auf wie Python. Live-Runs von Rust (Smoke, Akzeptanz) nur in reservierten Live-Lane-Fenstern ohne parallelen MCP-adb-Verkehr (F9). Die Debug-Kommandos sind hinter `SPECTRE_AFK_LIVE=1` und dem Lock.
6. **Rollback:** auf jeder Ebene eine Zeile (Task aus `AFK_RUST_TASKS`; `.vbs` zurück; Install-SHA zurück). Python wird erst nach E7b archiviert, nicht gelöscht.

## 6. Abhängigkeiten (Freigabe nötig, in T114 nichts hinzugefügt)

Geprüft gegen `Cargo.toml`/`Cargo.lock` des Workspace.

| # | Crate | Wofür | Ab | Stand | Empfehlung |
|---|---|---|---|---|---|
| D1 | `png` 0.18.1 (+ fdeflate, flate2, miniz_oxide, crc32fast, adler2, simd-adler32, bitflags) | Korpus/Fixtures lesen (Parity-Loader), Shots speichern, PNG-Fallback dekodieren | **E0b** (Loader) / E1 | im lokalen Registry-Cache → baubar mit `--offline` | **Mit Annahme des Plans freigeben.** `image` ist schwerer und hilft nicht (Resize nicht Pillow-gleich). Rohe `.rgb`-Kopien des Korpus statt PNG wären 5–10× größer und `png` braucht der Live-Pfad ohnehin. |
| D2 | `windows` 0.62.x (Features Foundation, Foundation_Collections, Globalization, Graphics_Imaging, Media_Ocr, Storage, Storage_Streams; transitiv windows-future/-collections) | Native WinRT-OCR | E3b | **nicht** im Cache (Download nötig); passt zu windows-core 0.62.2 im Lock | Freigabe erst nach dem GNU-Build-Spike, hinter Feature `ocr-winrt`. Ohne D2 bleibt ps1 (funktioniert, nur langsam). |
| D3 | `regex` | ~35 `re`-Stellen, meist OCR-Text-Parsing | E5 | nicht vorhanden | **Default: nein.** Handparser pro Pattern mit Golden-Tests (Hauskultur); `regex`-Semantik weicht ohnehin von Python `re` ab. Neu bewerten, falls in E5 mehr als ~10 Patterns unlesbar werden. |
| – | sha2, image, tempfile, walkdir, ctrlc, clap 4, tokio im Bot | – | – | – | **Nicht nötig.** Der Exporter berechnet die sha16; `--verify-corpus` ist deshalb ein Python-Schritt, und Rust prüft beim Laden Existenz, Größe und Pixelmaße gegen `frames.json`. Soll Rust selbst sha-verifizieren, ist `sha2` eine spätere, eigene Freigabefrage. |

Ohne Dependency machbar: idle (FFI), Lock (std), Exec (`spectre-mcp`-Lib), JSON/YAML (serde), Zeit (chrono), CLI (structopt), getevent-Parsing (von Hand), Python-String-Semantik (`pystr.rs`).

## 7. Risiken

1. **Pillow-Resample-Parität** (avg und LANCZOS fürs OCR), versionsgebunden. Eine Abweichung kippt Verdikte an Schwellen. Gegenmittel: bitgenauer Port der gepinnten Pillow-Version, Pillow-/Python-Version im Golden-Header; ein Pillow-Upgrade im Daily-Python gilt bis E7b als Verhaltensänderung (Re-Export + Diff). Korpusweiter Differential-Lauf in E2.
2. **Bewegliches Ziel:** Die Fix-Queue ändert Python weiter. Gegenmittel: E0a/E0b-Schnitt, `py_tree`-Header, STALE-FAIL, Re-Export pro Etappe/Merge, Freeze-Regel für grüne Tasks.
3. **OCR-Drift** (Encoding, Codepage im Task-Scheduler-Kontext, Banker's Rounding, Decode-Pfad, Sprachwahl). Gegenmittel: eingefrorene Roh-Bytes, `pystr.rs`, Live-OCR-Tier, E3b nur auf Entscheidungsebene.
4. **libm-Unterschiede** mingw/UCRT vs. MSVC-CRT an `round()`-Grenzen. Gegenmittel: Tabellen über die ganze Eingabedomäne, notfalls `const`.
5. **`windows`-Crate auf GNU ungetestet.** Gegenmittel: Spike in E3b, notfalls bleibt ps1.
6. **Deploy-Pfad:** Binary aus `target/release` würde von anderen Lanes still ersetzt bzw. blockiert deren Builds. Gegenmittel: eigenes `[[bin]]`, Install nach `spectre-bin/afk/<sha>/`, `SPECTRE_REPO` Pflicht.
7. **adb-Binary-Auswahl / Owner-Konflikt:** Falsches adb startet den Server neu; parallele Clients stören. Gegenmittel: SDK-Pfad pinnen (nie `adb_path()`), MCP unberührt, Live-Fenster, Debug-Kommandos gated.
8. **Live-unverifizierte Pfade** (sendevent auf BlueStacks, Raw-Screencap-Header) bis zum E1-Smoke.
9. **Gemischter Betrieb** auf einem Lock und gemeinsamen State-Dateien. Gegenmittel: Interop-Tests, `fs_after`.
10. **watch.sh-Edits:** Merge-Nähte in der Datei, die jeder geplante Run ausführt (`af367b3`). Gegenmittel: ein einziger Hook nach der Queue, Snapshot-Test, Flips nur über Env-Datei.
11. **Session/Idle:** „unabhängig von Anmeldung“ würde das Idle-Gate brechen. Gegenmittel: Interactive als dokumentierte Bedingung.
12. **Spec-Lücken:** 22 tote Frames, `SkipTest` in Schleifen, `manual`-Tests, ungeprüfte `ocr_region`-Zweige (FakeDevice stubbt `ocr_region` auf `[]`). Gegenmittel: Ledger, Zweigabdeckung, Shadow-Replay als zweite Spec-Quelle.
13. **Kalender** hängt an Live-Lane-Zeit (§3.9), nicht an Agent-Zeit.
14. **Aufwandsschätzung:** Task-Module nur nach Signaturen und Call-Counts geschätzt; Funktionskörper nicht alle gelesen.

## 8. Was am längsten in Python/Bash bleibt

- **Dauerhaft:** die 3 `.vbs`-Launcher (nur die Cmdline ändert sich in E7b), `spectre-tray.ps1`, die Dev- und Forschungs-Tools (§10).
- **Bis E7b:** `afk-bot-watch.sh`, `afk-night.sh` (mit Dispatch-Hook), `.cmd`-Entry-Points.
- **Über E7b hinaus:** `device-ensure.sh` und `bluestacks-ensure.sh`, weil andere Lanes und CLAUDE.md sie referenzieren. Der Rust-Runner ruft sie als Subprozess auf.
- **Bis E3b grün:** `templates/ocr.ps1` (Backend A, danach Orakel).
- **Bis E7b:** Python-Tests, `fake_vision.py`, `frame_manifest.json` und der Exporter als Orakel, danach archiviert, nicht gelöscht.

## 9. Notiz-Konzept für Python-Schwächen

- **Ablage:** Tabelle `PY-NOTE-nn` in diesem Report (Startbestand unten). Jede Etappe hängt im Etappenbericht neue Einträge an. Spalten: ID, Datei:Zeile, Symptom, Beleg, Auswirkung auf den Port.
- **Regel:** Rust **repliziert** Python-Verhalten (Parität vor Schönheit), markiert mit `// py-parity: PY-NOTE-nn`. **Ausnahme:** Fehler, die nur in Fehlerpfaden auftreten und dem dokumentierten Vertrag widersprechen (z. B. NOTE-01). Rust implementiert dann den Vertrag, der Golden-Record wird explizit `known_deviation: PY-NOTE-nn`. Stilles Abweichen gibt es nicht.
- **Gefixt wird in Python nichts** im Rahmen des Ports. Die Notizen gehen an Hermes und den Queue-Driver.

| ID | Wo | Schwäche | Port-Auswirkung |
|---|---|---|---|
| 01 | `afk_claim_vision.py` `ocr_png` ~L387 | `check_rc=False` gibt PowerShell-Fehlertext als OCR-Text zurück, wenn `ocr.ps1` fehlt oder scheitert (Beleg: 17 Fails ohne `templates/`), entgegen „[] on any failure“ | Rust liefert `[]` → known_deviation |
| 02 | `templates/ocr.ps1` + `ocr_png` | stdout kommt als gb2312 (cp936), wird aber als UTF-8 dekodiert → Umlaute werden zu U+FFFD-Paaren | ps1-Backend repliziert das über `pystr::decode_lossy_py`; E3b auf Entscheidungsebene |
| 03 | `templates/ocr.ps1` | `[int]` = Banker's Rounding, w/h aus Float-Extents | ist die Spec; Rust nutzt `round_ties_even` |
| 04 | `afk-daily-gift.py` | nimmt `_bot_lock` nicht (Direktaufrufe können kollidieren) | Rust repliziert; Entscheidung bei E5 |
| 05 | `afk_duras.py` | schreibt `duras-last.txt` selbst, zusätzlich zum Marker von watch.sh | repliziert bis E6 |
| 06 | `_bot_lock.py`, watch/night.sh | Lock-TOCTOU (kein O_EXCL); Bash schreibt die MSYS-`$$` statt der Windows-PID | repliziert; `create_new` erst nach E7b entscheiden |
| 07 | Idle 3× | `idle_seconds`, Heredoc in `bluestacks-ensure.sh`, totes `_idle_probe.ps1` (int32-TickCount, Wrap nach 24,8 d); alle fail-open | Rust: eine Implementierung, fail-open beibehalten |
| 08 | watch.sh / night.sh | Heap-Basis-Heredoc doppelt | Runner: eine Funktion |
| 09 | Tests | `test_frame_regression` ist im Worktree mit `checked=0` grün | `SPECTRE_PARITY=1` |
| 10 | Tests | uneinheitliche Frame-Wurzeln (REPO/.spectre, `parents[3]/spectre`, Hermes, `%TEMP%/now*`), nur teils mit trash-Fallback | Korpus mit einer Wurzel |
| 11 | Tests | Hermes-Frames nicht hash-gepinnt → gleichnamige Überschreibungen ändern Specs still | Korpus friert ein |
| 12 | Tests | `SkipTest` in Frame-Schleifen überspringt die restlichen vorhandenen Frames | Call-Recorder umgeht das |
| 13 | Tests | 22 Frames überall verloren (Dead Specs) | im E0b-Bericht gelistet |
| 14 | OCR | ein PowerShell-Spawn pro Aufruf (1,6–3,5 s gemessen), OCR hängt am PNG auf der Platte | E3b |
| 15 | `wallet-hunt-all.py` | REPO hart auf `C:/Users/Sigi/spectre` | Tooling, nicht portiert |
| 16 | `afk-bot-scheduled.cmd` | Kommentar „every 15 min“ veraltet (Task hat keine Wiederholung) | `.cmd` entfällt nach E7b |
| 17 | `spectre-mcp` (Rust) | `adb_tap`/`adb_key` umgehen `afk-bot.lock` (nur Lane-Regel) | Notiz, außerhalb des Ports; Live-Fenster (§5.5) |
| 18 | `spectre_adb::multi::adb_path` (Rust) | kann PATH-adb/HD-Adb wählen → Server-Neustart | Bot pinnt den SDK-Pfad |
| 19 | `afk-bot-watch.sh` ~L131–140 | Fallback auf Hermes-Python (`python-3.14.9…`) wird nur per `-x` geprüft; dieses Python hat kein PIL → der Fallback endet im PIL-Check und damit in rc 7/9 statt in einem nutzbaren Interpreter | Runner fällt in E7b weg; bis dahin Notiz |
| 20 | `afk_memory.py:35` | ruft `REPO/target/release/spectre.exe`, das parallele Lanes neu bauen (stiller Austausch, Exe-Lock beim Rebuild während eines Runs) | E4a repliziert; Install-Pfad-Konzept aus E7 sollte später auch hierfür gelten |
| 21 | `scripts/tests/fake_vision.py` ~L208 | `ocr_region` hart auf `[]` gestubbt; OCR nach Shot-Name keyed → `ocr_region`-Zweige und wiederholte Namen in Loops sind ungeprüft | Shadow-Replay-Ziele, Coverage-Report |
| 22 | Bot-Module (dream_realm L374–396, stage_push L267/L489–683, device_ready L37, arena L239/L442) | Deadline-Loops auf echter Wanduhr bei gemocktem `sleep`; `int(time.time()-t0)` landet in stdout/wall_report | Exporter mit virtueller Uhr; Rust `FakeClock` mit gleicher Lesezahl |

## 10. Tooling-Skripte (kein 1:1-Port)

- **Archivieren**, ersetzt durch spectre CLI/MCP `hot`/`hunt`/`dump`: `mem_probe.py`, `wallet-hunt-all.py`, `gold-analyze.py`.
- **Als Python behalten** (Dev-Werkzeuge, nicht im Daily-Run): `speed_profile.py` (Frida), `bluestacks-fps.py`, `adb-bench.py` (nach E1 durch `spectre-afk shot`/`tap` weitgehend überholt).
- **`afk-wall-dash.py`** (173 LOC, liest `wall-report.log`) bleibt Python, solange das Tray-Icon `spectre-walls.html` verlinkt. Ein Port ist ein eigenes, kleines Ticket nach E7b (F8).

## 11. Wo der Plan Hermes' Vorschlag ändert

| Hermes | Plan | Grund |
|---|---|---|
| Crate `spectre-bot` oder Module in `spectre-core` | neue Crate `spectre-afk` mit eigenem Binary | Domäne und Dependencies (§2.1); Daily-Run nicht an Lua/Web/tokio und nicht an `spectre.exe` koppeln |
| `spectre bot <task>` | `spectre-afk <task>` | Namenskollision mit `spectre bot <config.yaml>`; eigenes Binary |
| Specs = Python-Tests | Specs = aufgezeichneter Event-Strom unter virtueller Uhr + Fault-/OCR-/libm-/String-Goldens + eingefrorener Korpus; Tests nur als Untergrenze, Ledger als Vollständigkeitsnachweis | Asserts prüfen Teilmengen; Worktree-Läufe skippen 312 Subtests unbemerkt |
| Start mit android-infra | **E0a Korpus jetzt, E0b Harness** davor | ohne Goldens kein Paritätskriterium; Frames gehen laufend verloren; Goldens müssen auf den Python-Stand gepinnt sein |
| infra: Exec neu bauen | Exec aus der `spectre-mcp`-Lib wiederverwenden, MCP unberührt | kein Duplikat, kein Eingriff in den live laufenden adb-Owner |
| OCR: WinRT ersetzt ps1 | E3a ps1 aus Rust (byte-exakt), E3b WinRT nach A/B auf Entscheidungsebene | Encoding-, Rundungs- und Decode-Fallen; `windows` auf GNU ungetestet |
| state/misc: Memory nativ | E4a Subprozess wie Python, E4b in-proc optional | Kill-Semantik bei hängendem Read |
| Vision = crop/classify/colour scans | Vision **inkl. bitgenauem Pillow-Resample-Port** | `avg()` ist kein Mittelwert, sondern Pillows Fixed-Point-Bilinear |
| Task-Module 1:1 zu Skripten | 1:1 nur für Tasks; `afk_claim_vision` nach Layern zerlegt, dr/ar-Detektoren und `classify_battle` nach `vision`, Homestead-Common-Modul | God-Modul, Import-Zyklen, Task→Task-Kante, private Cross-Module-Helper |
| Tasks in Skript-Reihenfolge | Tracer-Bullet ohne OCR/Memory direkt nach E2; `claim` zuletzt geflippt | früher Live-Beleg; kleinster Blast-Radius zuerst |
| ein Commit pro Etappe | ja, außer E5: Branch + Commit pro Task | 14 Tasks in einem Commit/Branch sind nicht reviewbar und nicht rücknehmbar |
| state/misc als Etappe 4 | bleibt E4, aber `lock.rs` in E1 vorgezogen | jeder Live-Smoke muss den Lock respektieren |
| Windows-Tasks umstellen, py archivieren | E7a Task-Flips über einen Hook, E7b Runner allein; Binary aus Install-Pfad | kein Big-Bang; `target/release` ist kein Deploy-Ort |

## 12. Offene Fragen an Hermes und den User

1. **F1 Name:** Crate und Binary `spectre-afk` (`spectre-afk <task>`), einverstanden?
2. **F2 Dependencies:** D1 `png` mit Annahme des Plans freigeben (Gate für E0b/E1)? D2 `windows` erst nach dem Spike? D3 `regex` vorerst nein?
3. **F3 E0a jetzt:** Darf der Korpus-Snapshot schon jetzt laufen (offline, read-only auf `.spectre`, Schreiben nur nach `C:/Users/Sigi/spectre-parity/`, ~1 GB)? Wo soll die zweite Kopie (Zip) liegen?
4. **F4 Flip-Strategie:** Per-Task-Flip über `AFK_RUST_TASKS` vor E7b ist Plan-Default. Bestätigt? Er berührt die Daily-Runs nur über die Env-Liste, nicht über `.vbs`/Task Scheduler.
5. **F5 Live-Recorder:** Darf `AFK_RECORD=<dir>` (Opt-in, Default aus, mit Test) als letzter Queue-Eintrag bzw. durch Hermes in `afk_claim_vision.adb/shot/tap` eingebaut werden? Ohne ihn entfällt Shadow-Replay (E5-Exit 4) und Reverse-Shadow + K ≥ 5 wird der einzige Live-Beleg. Bitte **vor E1** klären.
6. **F6 Regel „neue Arbeit nur in Rust“:** Exporter, Korpus-Skript und Recorder sind neues Python, aber reines Test- und Orakel-Tooling. Ausnahme ok?
7. **F7 Schwellen und Budget:** N ≥ 5 Shadow-Runs pro Task, K ≥ 3 Live-Akzeptanzruns pro Task, K ≥ 7 geplante Runs für E7a und E7b je Run-Typ, Hermes-Budget 2–4 Live-Fenster pro Woche. Passt das?
8. **F8 Tooling:** `mem_probe`/`wallet-hunt-all`/`gold-analyze` jetzt archivieren? `afk-wall-dash` als Python behalten?
9. **F9 adb-Ownership:** Rust-Live-Runs (Smoke, Akzeptanz) nur in reservierten Live-Lane-Fenstern ohne parallelen MCP-adb-Verkehr; Debug-Kommandos nur mit `SPECTRE_AFK_LIVE=1` + Lock. Bestätigen?
10. **F10 Install-Pfad:** `C:/Users/Sigi/spectre-bin/afk/<sha>/` für das geplante Binary, ok? Wer installiert (Hermes nach Live-Grün)?
11. **F11 Testzahl:** Das Inventar nennt 51 Dateien / ~1000 Tests. Gemessen: 49 `test_*.py` mit 897 Tests (552 s, 312 Skips im Worktree). Der Ledger verwendet die gemessenen Zahlen.

## 13. Review — Umgang mit der Kritik

Zwei Kritik-Runden (Risiko, Parität) am Entwurf. Fast alles wurde übernommen. Geprüft gegen den Code: `spectre-adb` zieht tokio, `spectre-mcp` nur serde/serde_json, `spectre-cli` zieht lua/web/bot/tokio, `afk_memory.py:35` nutzt `target/release/spectre.exe`, und watch.sh fällt auf das Hermes-Python zurück.

**Risiko-Kritik**

| Punkt | Entscheidung | Begründung / Umsetzung |
|---|---|---|
| E7 Binary aus `target/release` | **angenommen** (vereinfacht) | Install nach `spectre-bin/afk/<sha>/`, `SPECTRE_REPO` Pflicht, keine `current_exe()`-Heuristik. Keine separate `current`-Zeiger-Datei: Die Zeile in `.vbs` bzw. der Hook-Pfad *ist* der Zeiger (Symlinks brauchen unter Windows Rechte). |
| Subcommand in `spectre-cli` | **angenommen** | Eigenes `[[bin]] spectre-afk`. CLI-Alias abgelehnt, weil ihn niemand braucht. |
| Exec-Lift nach `spectre-adb` riskiert MCP | **angenommen** | `spectre-afk` nutzt die `spectre-mcp`-Lib direkt (nur serde), MCP bleibt unberührt; Mini-Crate `spectre-exec` frühestens nach E7. E1-Exit „MCP-Tests nach Lift“ entfällt. |
| Golden-Drift durch die Queue | **angenommen** | E0a/E0b, `py_tree`-Header, Re-Export pro Etappe/Merge, Freeze-Regel. |
| Oracle-Version (Pillow, Hermes-Python ohne PIL) | **angenommen** | Versionen im Header, Risiko 1 erweitert, PY-NOTE-19. |
| 14 Edits an watch.sh | **angenommen** | Ein Hook nach der Queue, Snapshot-Test, Flips nur über Env-Liste. |
| Big-Bang in E7 | **angenommen** (mit Vorbehalt) | Per-Task-Flip ist Plan-Default, E7a/E7b getrennt, `.cmd` erst nach E7b weg. Bleibt als F4 bestätigungspflichtig, weil es Hermes' Vorgabe „Daily-Runs unberührt“ berührt; Fallback ist beschrieben. |
| Nichts Lauffähiges bis spät | **angenommen** | Tracer-Bullet nach E2, `claim` zuletzt geflippt. Die konkrete Wahl (arena vs. normalize/device_ready) bestätigt der Ledger, weil Memory-Abhängigkeiten von arena nicht geprüft sind. |
| E4 in-process ohne Timeout | **angenommen** | E4a Subprozess, E4b optional mit Watchdog. |
| adb-Ownership der Debug-Kommandos | **teilweise** | (a) Gate `SPECTRE_AFK_LIVE=1` + Lock und (b) Live-Fenster angenommen. (c) Server-Versionsprüfung **abgelehnt**: `adb version` zeigt nur den Client, die Server-Version bräuchte das Wire-Protokoll (Nicht-Ziel). Python prüft das auch nicht, und Python, MCP und Rust pinnen dasselbe SDK-adb. |
| Korpus im Main-Checkout | **angenommen** | `C:/Users/Sigi/spectre-parity/`, schreibgeschützt, `verify_corpus.py`, zweite Kopie. |
| Shadow-Recorder im Live-Pfad | **angenommen** | Opt-in `AFK_RECORD`, mit Test, vor E1 zu klären (F5). Ohne ihn ist die schwächere Absicherung explizit beschrieben. |
| Aufwand/Kalender | **angenommen** | E0 jetzt 6,5–8,5 Tage, Summe 40–55, Kalender separat (3–4 Monate), Bündelung über Daily-Runs, Hermes-Budget in F7. |
| E6-Specs umschreiben | **angenommen** | Wrapper-Tests parametrisiert gegen beide Implementierungen, Tray-Zeilen als Golden. |
| Encoding/Codepage E3a | **teilweise** | Roh-Bytes speichern und Lossy-Semantik testen: angenommen. ASCII-Normalisierung schon in E3a: **abgelehnt** zugunsten des Parity-Punkts P18. Offline sind die eingefrorenen Bytes byte-exakt vergleichbar; die Codepage-Frage gehört in den Live-Tier. |
| D1-Gate | **angenommen** | D1 ist Vorbedingung von E0b/E1. Die `.rgb`-Alternative wurde **abgelehnt**: 5–10× Platz, und `png` braucht der Live-Pfad ohnehin. |
| Branch pro Task in E5 | **angenommen** | — |

**Paritäts-Kritik**

| Punkt | Entscheidung | Umsetzung |
|---|---|---|
| P1 Event-Reihenfolge | **angenommen** | §4.1 Event-Schema, exakter Strom-Vergleich. |
| P2 Uhr nicht deterministisch | **angenommen** | Virtuelle Uhr im Exporter, `now`-Events, `FakeClock` mit gleicher Lesezahl, PY-NOTE-22. |
| P3 OCR in Flows kaum geprüft | **angenommen** | OCR-Events, FakeOcr name-/sequence-keyed, Call-Site-Abdeckung im E5-Exit, PY-NOTE-21. |
| P4 OCR-Specs umgebungsabhängig | **angenommen** | Eingefrorene Roh-Bytes, Live-Tier `SPECTRE_PARITY_OCR_LIVE`. |
| P5 Byte→String-Semantik | **angenommen** | `pystr.rs` + `pystr.jsonl`. |
| P6 Float-Regel | **angenommen** | Bit-exakt für Arithmetik, libm-Tabellen. |
| P7 Seiteneffekte | **angenommen** | `fs_after`, stdout-Vertragszeilen. |
| P8 Exit-Codes nur Gutpfade | **angenommen** | `faults.jsonl`, Panic-Mapping, kein `panic=abort`. |
| P9 Vollständigkeit | **angenommen** | Ledger, Scope-Dateien, Zweigabdeckung per stdlib `trace`. |
| P10 Manual-Tests | **angenommen** (als Review-Hilfe) | Assert-Zahl per AST ist nur ein grober Stellvertreter; sie ersetzt nicht das Review. Ziel < 20 manual. |
| P11 Bewegliches Ziel | **angenommen** | Mit Risiko-Punkt „Golden-Drift“ zusammengelegt. |
| P12 Recorder-Lücken | **angenommen** | `id()`-Wrapping, `setprofile`-Selbsttest, Mutations-Check. |
| P13 Shadow-Replay | **angenommen** | Vollständiger Strom bis Run-Ende, sequence-keyed. |
| P14 Live-Runs ≠ Parität | **angenommen** | Akzeptanzkriterien + Reverse-Shadow. |
| P15 E1-Smoke | **angenommen** | Raw-Mitschnitt offline vergleichen, Modusvergleich über Traces. |
| P16 PNG-Writer | **angenommen** | Chunk-Test, ps1-OCR auf Rust- vs. PIL-PNG. |
| P17 Differential-Lauf zu schmal | **angenommen** | Eingefrorene Dateiliste (E0a), alle reinen Vision-Funktionen + Preprocessing. |
| P18 E3b-Toleranz | **angenommen** | E3a byte-exakt, E3b auf Entscheidungsebene. |
| P19 Runner-Spec | **angenommen** (begrenzt) | `runner.jsonl` + Matrix; bei Explosion paarweise reduziert, Reduktion im Bericht. |
| P20 Golden-/Korpus-Haltbarkeit | **angenommen** | Sharding statt gitignore, keine gz, zweite Korpuskopie, Korpus-Prüfung (`verify_corpus.py` + Rust-Loader) als FAIL. |

---

*Nicht geprüft:* Funktionskörper der Task-Module (nur Signaturen, Imports, Call-Counts), ob `arena` Memory/Power braucht (Tracer-Wahl), die tatsächliche Größe der Goldens, der Build der `windows`-Crate auf GNU, die Python-Suite unter Main-Checkout-Bedingungen (statisch abgeleitet: 289 von 311 fehlenden Frames sind dort vorhanden), ob die Suite unter virtueller Uhr grün bleibt, die Codepage der Task-Scheduler-Sessions, die libm-Abweichung mingw vs. MSVC (nur als Risiko angenommen).
