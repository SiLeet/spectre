# T117 — Rust-Port Etappe 1 „android-infra“ — 2026-11-05

Plan: `docs/reports/rust-port-plan.md` §E1 (Scope-Tabelle, Exit-Kriterien), §2.2, §4.1, §4.4/4.5, §6.
Branch `feature/T117-e1-infra`, 1 Commit, kein push. Python unverändert. **Live-Smoke macht Hermes** (Checkliste unten).

## Ergebnis in Zahlen

| Prüfung | Ergebnis |
|---|---|
| Vorab: `verify_corpus.py` | 230/230 ok |
| Vorab: `py_tree` (Main `f85b3a9`) | `03cc13204eef9bbf` = Goldens → **nicht STALE** |
| Vorab: `export_goldens.py check` | 1005 Tests (2 fail = Arena-Befund T115, 31 skip), 655 Flows / 10 802 Events, 1362 Calls — gleich den T115-Goldens (keine Python-Drift); Determinismus dieses Laufs nicht aussagekräftig (Befund 10) |
| **Finaler Doppel-Export** (neuer Recorder) | **deterministisch** (`goldens/determinism.json`: 0 Diffs); beide Läufe 1005 Tests, 2 fail, 0 err, 31 skip; 655 Flows / 10 808 Events, 1362 Calls, 290 Synthetik-Frames; 0 `.spectre`-Schreibversuche, Live-Dateiliste vorher/nachher gleich |
| **E1-Infra-Records** (`goldens/infra/`) | **106** (93 `afk_claim_vision`, 13 `_bot_lock`), 64 aufgezeichnete I/O-Events |
| **E1-Replay** `SPECTRE_PARITY=1 … --test parity_e1` | **106/106 identisch, 0 Diff, 0 unsupported, 0 Skip, 0 STALE**; alle 7 Scope-Module belegt; zusätzlich Infra-Aufrufe aus 20 Flow-Modulen mit-replayt |
| je Funktion | `tap_retry` 23, `tap_seq` 13, `tap_mode`-Familie (`_env_tap_mode` 4, `parse_getevent` 5, `sendevent_cmds` 4, `sendevent_device` 5, `_tap_cmd` 3, `tap` 5, `tap_hold` 3, `tap_result` 7), `back` 8, `key_seq` 2, `swipe` 1, `_raw_to_image` 7, `shot` 3, `_bot_lock` acquire 7 / release 3 / describe 3 |
| Lock-Interop mit `_bot_lock.py` | beide Richtungen grün |
| `raw_to_frame` vs. `_raw_to_image` | byte-identisch auf allen Records (7 `_raw_to_image`, 3 `shot`, Header 12 und 16) und per `decode-raw` (Key + CRC gleich) |
| D1-Korpus (strict) | 230/230 Frames byte-gleich zu Pillow |
| Rust-Tests `spectre-afk` | 25 Unit + 2 `main` + 2 `parity` + 2 `parity_e1` grün; `spectre-mcp` 12 grün (unverändert, nur als Lib genutzt) |
| Tooling-Selbsttests | 7/7 |
| `check --workspace` / `clippy --workspace --all-targets` | 0 Fehler / **0 Warnungen** |
| stdout (informativ) | 1 von 106 Aufrufen druckt anders (gemockter `TimeoutExpired`-Text, Befund 4) |

Die Call-Goldens unterscheiden sich von T115 nur im Header (`git_head` `222be8c` → `f85b3a9`, `py_tree` gleich).

## Was gebaut ist (Plan-Tabelle §E1 → Crate `spectre-afk`)

| Plan | Datei | Python-Vorbild |
|---|---|---|
| `CommandRunner`/`SystemRunner` als Lib-Dependency | `Cargo.toml` (`spectre-mcp` per Pfad, nicht verschoben) | `spectre-mcp/src/lib.rs` |
| `env.rs`: `adb_bin()`, `SERIAL`, `repo_root()` (SPECTRE_REPO Pflicht → rc 2), `validate_repo()`, `shots_dir(pid)`, `tap_mode_env()` | `src/env.rs` | `REPO`, `ADB`, `SERIAL`, `TMP`, `_env_tap_mode` |
| `infra/adb.rs`: `Adb<R>::run(args, timeout)` (immer `-s SERIAL`, kein connect/devices), Timeouts 30/60/10 s | `src/infra/adb.rs` | `adb()` |
| `infra/tap.rs`: `TapMode`, `TAP_CHAIN`, `TapState`, `parse_getevent`, `sendevent_cmds` (MT B und A, `round_ties_even`), `sendevent_device` (Root-Check 1×), `tap_cmd`, `tap_retry`, `tap_result` | `src/infra/tap.rs` | L490–635 |
| `infra/seq.rs`: `press`, `tap`, `tap_hold`, `run_seq` (`&&`-Kette, `sleep {:g}`, Timeout int(Σwaits)+15), `tap_seq`, `key_seq`, `back`, `swipe` | `src/infra/seq.rs` | L589–691 |
| `infra/screencap.rs`: `raw_to_frame` (Header 12/16, fmt 1, len-Check, 0<w,h≤8192, RGBA→RGB), `shot` (raw → `-p`-Fallback, `TMP/<name>.png` nur IHDR/IDAT/IEND) | `src/infra/screencap.rs` | L694–734 |
| `img/frame.rs` minimal | `src/img.rs` (`Frame`, `crop` wie PIL, `key()`, PNG in/out, Chunk-Liste) | PIL `Image` |
| `infra/device.rs`: `trait Device` + `AdbDevice` (jede Methode ein Event, Uhr injiziert) | `src/infra/device.rs`, `src/infra/clock.rs` | Modul-Globals von `v` |
| `infra/trace.rs` nach §4.1, `AFK_TRACE=<file>` live | `src/infra/trace.rs` | Recorder-Schema |
| `state/lock.rs` (vorgezogen aus E4), byte-kompatibel, TOCTOU wie Python | `src/state/lock.rs` | `_bot_lock.py` |
| `testkit`: `FakeDevice`, `DeadTapDevice`, `FakeClock` (gleiche Guards; kein `_SPEC`-Renderer) | `src/testkit/fake.rs`, `src/infra/clock.rs` | `fake_vision.py` |
| `main.rs`: `tap`, `key`, `shot` nur mit `SPECTRE_AFK_LIVE=1` + Lock, sonst rc 2; offline `decode-raw` | `src/main.rs` | – |
| Python-String-Semantik, Hash ohne Dependency | `src/pystr.rs` (`{:g}`, `split()`, `strip()`, `splitlines()`, repr, `int()`), `src/hash.rs` (SHA-256, CRC-32) | – |

**Design:** Die Python-Modul-Globals (`adb`, `tap`, `TAP_MODE`, `_TAP_DEAD`, `_SENDEVENT`, …) sind *ein*
`Device`-Objekt. Low-Level-Hooks (`adb`, `exec`, `sleep`, `print`, Tap-Zustand) liefert jede
Implementierung; die High-Level-Methoden (`tap`, `tap_hold`, `tap_seq`, `key_seq`, `back`, `swipe`, `shot`,
`sendevent_device`) sind Default-Methoden auf den 1:1 portierten freien Funktionen und überschreibbar. Interne
Aufrufe laufen über `self` — wie in Python über die Modul-Globals, die die Tests patchen. `tap_retry` ruft
also `dev.tap(...)`/`dev.tap_hold(...)`, und ein FakeDevice oder Replay sieht das wie ein gepatchtes `v.tap`.

## Wie die Parität geprüft wird

- **Infra-Recorder** (neu in `export_goldens.py`): jeder *direkte* Testaufruf in die E1-Funktionen
  (`afk_claim_vision.adb … shot`, `_bot_lock.acquire/release/describe`) wird mit Argumenten, Tap-Zustand
  vorher/nachher (`TAP_MODE`, `_TAP_DEAD`, `_SENDEVENT`, `AFK_TAP_MODE`, `sleep_patched`), allen I/O-Events
  dazwischen (gepatchtes `adb`/`subprocess.run` inkl. Antwort, `time.sleep`, Fake-/Stub-Aufrufe), Ergebnis
  oder Exception, stdout und (bei `shot`) der geschriebenen Datei aufgezeichnet → `parity/goldens/infra/*.jsonl`.
- **Replay** (`spectre-afk/src/testkit/replay.rs`, Test `tests/parity_e1.rs`): die Rust-Funktion läuft gegen
  das aufgezeichnete Skript. Jeder adb-Aufruf muss das nächste `adb`/`run`-Event mit gleichem argv und gleichem
  Timeout verbrauchen und bekommt dessen Antwort (rc/stdout/stderr bzw. `TimeoutExpired`); Device-Events
  (`tap`/`hold`/`seq`/`key`/`swipe`/`shot`/Stubs) werden an der Methode beantwortet — dort, wo der Python-Test
  gepatcht hatte — mit Vergleich *aller* aufgezeichneten Argumente (inkl. `tolerate`/`dry`, übergebener vs.
  genutzter Tap-Modus). Bei gepatchtem `time.sleep` muss jeder Rust-Sleep ein aufgezeichnetes Sleep treffen.
  Danach müssen Ergebnis, Exception-Typ, Tap-Zustand, „kein Event übrig“ und (bei `shot`) die Datei (Existenz,
  Pixel, nur IHDR/IDAT/IEND) stimmen. Lock-Records laufen gegen eine Temp-Datei mit aufgezeichnetem Inhalt/Alter.
- **Scope** `parity/scope/E1.toml`: Pflicht-Shards, 7 Spec-Module (je ≥ 1 Record), `test_adb_bench`
  out_of_scope (Python-Dev-Tool, plan §10, keine `afk_claim_vision`-Infra-Records).
- **Lock-Interop** in beide Richtungen gegen das echte `_bot_lock.py` (Python legt an → Rust sieht fremden
  frischen Lock; Rust übernimmt stale → Python sieht fremden Lock, lässt ihn beim release stehen; geerbter
  Wrapper-Lock).

## Abweichungen vom Plan / Befunde

1. **`;` vs. `&&`:** Plan und Brief nennen `;`-Ketten, `_run_seq` verkettet seit dem wave-6-Review mit ` && `
   (ein fehlschlagender Mittelschritt bricht ab). Der Port folgt dem Code.
2. **`tap()` gibt in Rust den genutzten Modus zurück** (Plan: „Device.tap → genutzter Modus“); Python gibt None.
   Der Replay vergleicht das Python-Ergebnis (None) und den Modus getrennt.
3. **`faults.jsonl` existiert nicht** (Fault-Injection ist E0b-2) — Exit-Kriterium 3 „faults 0 Abweichungen“
   ist damit nicht nachweisbar. Die Fehlersemantik ist über die Records belegt, die Python-Tests selbst
   erzeugen: rc≠0 „device offline“ toleriert (`tap_seq` tolerate=True) bzw. RuntimeError (tolerate=False,
   `_press`), `TimeoutExpired` in der Discovery, Screencap rc 1 → RuntimeError, Fallback raw→`-p`.
4. **stdout** wird pro Infra-Aufruf aufgezeichnet und informativ verglichen (Vertragszeilen gibt es noch nicht,
   §4.3/E0b-2): 1 Abweichung — der Text einer vom *Test* gemockten `TimeoutExpired('adb', 10)`; Rust druckt
   „adb timed out“.
5. **Keyevent-4-auf-WORLD-Guard** im Rust-FakeDevice braucht `classify` (E2): als injizierte Funktion
   (`with_world`), im Python-FakeDevice dasselbe Prädikat.
6. **pystr-Abkürzungen** (im Code markiert): `int()` ohne Unicode-Ziffern, `repr()` escapet Nicht-ASCII nicht
   wie CPython — beides nur in Log-Zeilen/Env-Werten.
7. **Recorder-Erweiterungen in dieser Etappe** (nur Tooling, `scripts/tests/parity/`, ändert `py_tree` nicht):
   Infra-Recorder; Device-Events stehen jetzt *vor* den Events, die in ihnen passieren, und der Tiefen-Guard
   wirkt nur pro Methode (vorher gingen die adb-Aufrufe in `real_seq`-Batches verloren: +8 Events); gefeuerte
   Test-Guards (`AssertionError`) bleiben im Strom; `mode_arg`, `tolerate`/`dry`, `stdout_file` (Inhalt bei
   `screencap -p` in eine Datei), `sleep_patched`. Deshalb sind die Goldens neu exportiert.
8. **Review** (unabhängig, 3 Linsen, nur lesend): keine Verhaltensabweichung des Ports gefunden. Behoben wurden
   Lücken im Replay (zu lockere Intercepts, Sleeps nur bei vorhandenen Events geprüft, Shot-Datei ungeprüft,
   fehlende Blobs → leere Daten, Lock-Exception-Typen, Vollständigkeit) und Live-Sicherheit (Punkt 9).
9. **Live-Sicherheit** (`main.rs`): `SPECTRE_REPO` muss der Bot-Checkout sein (`.spectre/` +
   `scripts/_bot_lock.py`, kanonisiert) — ein falscher Pfad hätte sonst einen eigenen Lock angelegt und am
   echten vorbei getappt; Lock-Release per RAII-Guard (auch bei Panic) und Ctrl-C-Handler (std-FFI auf
   `SetConsoleCtrlHandler`, keine neue Dependency); `AFK_BOT_LOCK_HELD=1` nur mit existierender Lock-Datei;
   `--mode sendevent` ohne Gerät meldet „via tap (sendevent unavailable)“; Shot-Namen ohne Pfadanteile.
   Belegt: ohne `SPECTRE_AFK_LIVE=1` rc 2; Worktree als `SPECTRE_REPO` rc 2 (kein `.spectre` angelegt);
   ohne `SPECTRE_REPO` rc 2 — jeweils ohne einen adb-Aufruf.
10. **Pre-Check-Determinismus** nicht aussagekräftig: Ich habe den Exporter während des Pre-Check-Laufs
    erweitert (Lauf 1 und 2 mit verschiedenen Exporter-Ständen). Seine Zahlen stimmen mit den T115-Goldens
    überein (keine Python-Drift). Der erste finale Doppel-Export war wegen einer **fremden Dateisperre** nicht
    deterministisch: `scripts/tests/.artifacts/battles.test.jsonl` im Main-Checkout war in Lauf 1 von einem
    anderen Prozess belegt (`WinError 32`, ein paralleler Testlauf) → 1 Error in einem Arena-Test und
    Folge-Diffs. Wiederholt: siehe Zahlen.

## Unbelegte Zweige (Zeilenabdeckung der E1-Spec-Module über die Python-Referenz)

Die 7 Spec-Module (163 Tests) führen in `afk_claim_vision.py` L486–734 **116/127** Anweisungen aus, in
`_bot_lock.py` **30/44**. Nicht belegt (ohne Modulkonstanten und `global`-Zeilen, die beim Import laufen):

| Zeile | Was | Rust-Absicherung |
|---|---|---|
| `adb()` L487 | der echte `subprocess.run`-Aufruf (Tests patchen immer `adb`) | `Adb::argv`-Unit-Test, `SystemRunner`-Kill-Test |
| `swipe` L691 | `time.sleep(wait)` nach erfolgreichem Swipe | `trace_follows_the_recorder_schema` (Sleep nur nach Erfolg) |
| `shot` L719 | `except (SubprocessError, OSError, ValueError)` auf dem Raw-Pfad | Code-Review; ein Raw-Fehler geht in den `-p`-Fallback |
| `_bot_lock` L52/54/74/76/94 | Default-Lock-Pfad und `env=None` (`os.environ`) | `main.rs` nutzt genau diesen Weg (`default_lock`, `os_env`) |
| `_bot_lock` L83 | `release` auf eine verschwundene Datei | Unit-Test `semantics_like_bot_lock_py` |
| `_bot_lock` L102 | `describe`: Datei verschwindet zwischen read und stat | – (Race) |

Diese Zweige sind Shadow-Replay-Ziele (§4.5) bzw. Live-Smoke-Punkte.

## Live-Smoke-Checkliste (Hermes, §E1 Exit 4)

Voraussetzungen: reserviertes Fenster der Live-Lane, **MCP-adb-Verkehr gestoppt** (F9), Bot-Lock frei,
Spiel auf einem statischen Screen (nicht WORLD für `key 4`).

```bash
cargo +stable-x86_64-pc-windows-gnu build --release -p spectre-afk     # -> target/release/spectre-afk.exe
export SPECTRE_AFK_LIVE=1 SPECTRE_REPO=C:/Users/Sigi/spectre AFK_TRACE=C:/Users/Sigi/spectre-parity/e1-live-trace.jsonl
spectre-afk shot e1_smoke_0                  # Raw-Pfad: druckt Pfad, 1920x1080, key
spectre-afk tap 960 540                      # Modus aus AFK_TAP_MODE (Default tap)
spectre-afk tap 960 540 --mode touchscreen
spectre-afk tap 960 540 --mode sendevent     # "via tap (sendevent unavailable)" = Discovery fand kein Gerät
spectre-afk key 4                            # nur auf einem Nicht-WORLD-Screen
```

1. **Raw vs. Pillow, byte-exakt (offline):** einmal Rohbytes und PNG vom selben statischen Screen ziehen:
   `adb -s 127.0.0.1:5555 exec-out screencap > raw.bin` und `… exec-out screencap -p > p.png`, dazu ein
   zweites `raw2.bin` direkt danach. Dann `spectre-afk decode-raw raw.bin` und
   `python -c "import sys,zlib; sys.path[:0]=['scripts','scripts/tests/parity']; import afk_claim_vision as v, freeze_corpus as fc; im=v._raw_to_image(open('raw.bin','rb').read()); print(im.size, fc.frame_key(im), zlib.crc32(im.tobytes()))"`
   → key/crc32 müssen gleich sein (offline vorgeprüft: 4×3-Raw mit 16-Byte-Header, beide Seiten
   `a698690b150a92f0` / crc32 1367794175). Header-Form (12/16) und Größe zeigt `decode-raw`. Pixelgleichheit
   raw vs. `-p` nur fordern, wenn `raw.bin == raw2.bin` (sonst Animation).
2. **N = 20 Taps pro Modus** (tap / touchscreen / sendevent) auf eine harmlose Stelle; Moduswahl und Fallback
   stehen im `AFK_TRACE` (`tap`-Event mit `mode`, `adb`-Event mit argv/rc). Der Python-Live-Recorder
   (`AFK_RECORD`, F5) existiert noch nicht — Vergleich bis dahin gegen die erwartete argv-Form
   (`input tap X Y` / `input touchscreen tap X Y` / `su -c "sendevent …"`).
3. `AFK_TRACE`: eine JSON-Zeile pro Event (append). Schema-Projektion für den späteren Vergleich mit dem
   Python-Recorder: Rust schreibt `adb {fn, argv, kwargs.timeout, rc|raise}` und `run {argv voll, …}` ohne
   stdout (Screencaps sind MB groß).
4. Danach darf `spectre-afk` keinen Lock hinterlassen (`.spectre/afk-bot.lock` gehört wieder dem Bot).

## Ledger-Bilanz (E1-Scope)

Spec-Module aus §E1 (Ergebnis ok/skip/fail; Testanzahl mit Infra-, Flow-, Call-Records; ohne jeden Record):

| Modul | Tests | ok/skip/fail | infra | flows | calls | ohne Record |
|---|---|---|---|---|---|---|
| `test_tap_mode` | 16 | 16/0/0 | 16 | 10 | 4 | 0 |
| `test_tap_seq` | 11 | 11/0/0 | 8 | 10 | 1 | 0 |
| `test_input_robustness` | 10 | 10/0/0 | 8 | 10 | 3 | 0 |
| `test_fast_shots` | 8 | 8/0/0 | 5 | 5 | 0 | 1 |
| `test_review_fixes` | 91 | 84/7/0 | 10 | 60 | 25 | 15 |
| `test_zombie_recovery` | 14 | 14/0/0 | 7 | 12 | 3 | 1 |
| `test_bot_lock` | 13 | 13/0/0 | 10 | 3 | 1 | 3 |
| `test_adb_bench` (out_of_scope) | 5 | 5/0/0 | 0 | 4 | 2 | 1 |

E1-relevant sind die Infra-Records (alle 106 grün). Flows/Calls dieser Module gehören zu E2 (Vision) bzw. E5
(Flows). Die Tests „ohne Record“ sind Kandidaten für `manual`/`out_of_scope` im AST-Ledger (E0b-2):
`test_fast_shots` 1 (OCR-Region-Crop → E3), `test_bot_lock` 3 (Verdrahtungs-Greps der Skripte/Wrapper),
`test_review_fixes` 15 (Memory-Guard/Tooling, E4), `test_zombie_recovery` 1 (`is_static`, E2).

## Offene Punkte

1. Live-Smoke (Hermes) — Exit-Kriterium 4.
2. `faults.jsonl` / Fault-Injection (E0b-2) — Exit-Kriterium 3 formal offen.
3. Vertragszeilen-Liste für stdout (§4.3, E0b-2), danach stdout-Vergleich scharf schalten.
4. Python-Live-Recorder `AFK_RECORD` (F5) für den Trace-Vergleich.
5. Arena-Befund aus T115 (2 Tests, 3× BACK statt 2×) liegt weiter in der Python-Fix-Queue; die Goldens
   zeichnen das aktuelle Python-Verhalten auf.
