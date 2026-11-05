# T115 — Rust-Port Etappe 0 (E0a Korpus, E0b Goldens) — 2026-11-05

Plan: `docs/reports/rust-port-plan.md` §E0a, §E0b, §4. Routine/Dateiübersicht: `parity/README.md`.
Freigaben: User „Yes, start E0“ (png-Crate, ~1 GB außerhalb des Repos); Hermes T115 (D1 png = GO).
Branch `feature/T115-e0-freeze-goldens`, 1 Commit, kein push. **STOP für Hermes' Review vor E1.**

## Ergebnis in Zahlen

| Prüfung | Ergebnis |
|---|---|
| Export gegen Main-Checkout `222be8c` (sauber), zweimal | **deterministisch** (0 abweichende Dateien, `goldens/determinism.json`) |
| Suite unter Recorder + Korpus-Overlay | 1005 Tests: 993 ok, 10 skip, **2 fail** (siehe „Befund“) — beide Läufe gleich |
| Schreibzugriffe auf `.spectre` | 0 blockiert; Live-Dateiliste vorher/nachher identisch |
| Korpus `verify_corpus.py` | 230/230 ok |
| D1-Gate: Rust-`png` == Pillow `convert('RGB')` | 230/230 Frames byte-gleich (crc32), `SPECTRE_PARITY=1` |
| `parity.rs` strict auf den Goldens | 2017 Records, 73 Funktionen, py_tree aktuell (nicht STALE), 0 unbekannte Frame-Keys, Coverage 0/73 (erwartet) |
| Tooling-Selbsttests `scripts/tests/parity/test_parity_tools.py` | 7/7 |
| `cargo check --workspace` / `clippy --workspace --all-targets` | 0 Fehler / 0 Warnungen |

## Befund: Python-Regression, die ein Skip verdeckt hat

`test_arena_select.RealFrames.test_normalize_pressed_lobby_skips_the_resolver` und
`test_arena_select.RoundStart.test_real_pressed_lobby_is_waited_not_retapped` skippen in der normalen Suite
(„frame missing: shots-17920/norm_0.png“ — der F16-Prune hat den Ordner nach `.spectre/trash/` verschoben).
Über den Korpus laufen sie wieder und **scheitern**: auf der gedrückten Lobby kommen drei BACK statt zwei
(`[K, K, K]` statt `[K, K]`, bzw. ein zusätzliches BACK vor den Claim-Taps). Die Frames sind sehr
wahrscheinlich die richtigen: `trash/shots-17920` stammt vom 2026-11-04 13:00 (Tag von T95/T96), `norm_0`
liest `UNKNOWN`, `norm_1` liest `POPUP`, genau wie der Testkommentar („pressed lobby … reads POPUP“). Nicht in
T115 behoben (Python bleibt Python, Fix-Queue). In den Goldens stehen beide Tests mit `outcome: fail` —
aufgezeichnet ist, was Python tut.

## Artefakte und Größen

| Was | Wo | Größe |
|---|---|---|
| Korpus: 230 Fixture-Frames, **Original-Bytes**, schreibgeschützt | `C:/Users/Sigi/spectre-parity/frames/<sha16>.png` | 635 MB |
| Von Tests gebaute Frames (205 gespeichert + 82 Aliase `convert('RGB')` eines Korpus-Frames) | `C:/Users/Sigi/spectre-parity/synthetic/<sha16>.png` | 214 MB |
| Große Byte-Payloads (1 Fake-Screencap) | `C:/Users/Sigi/spectre-parity/blobs/<sha16>.bin` | 8 MB |
| Korpus-Manifest | `parity/frames.json` | 132 KB |
| eingefrorene `.spectre`-Dateiliste (2138 Dateien; für E2) | `parity/spectre-filelist.json` | 259 KB |
| Goldens: 45 Flow-Dateien (655 Records, 10 802 Events), 16 Call-Dateien (1362 Records), Ledger-Keim, Synthetik-Liste | `parity/goldens/` | 2,2 MB |
| Tooling | `scripts/tests/parity/{freeze_corpus,verify_corpus,export_goldens}.py` + Selbsttests | — |
| Rust-Skelett | Crate `spectre-afk` (`testkit`: PNG-Loader, JSONL, crc32, py-tree; `tests/parity.rs`) | — |

Gesamt außerhalb des Repos: **~857 MB** (freigegeben: ~1 GB). Die **zweite Kopie als Zip** ist nicht
angelegt: Ort legt der User fest (Plan F3).

Header jeder Golden-Datei: `{v:1, py_tree: 03cc13204eef9bbf, git_head: 222be8c…, python: 3.14.3,
pillow: 12.2.0, windows_build: 10.0.26300, ocr_ps1_sha: 3c592d504cec2781}`. `py_tree` = sha16 über
`git ls-tree -r HEAD -- scripts templates` **ohne** `scripts/tests/parity/` — das Tooling ändert den Pin nicht,
nach dem Merge dieses Branches bleibt er gleich.

## Wie E0b reproduziert wird

```bash
python scripts/tests/parity/export_goldens.py check --repo C:/Users/Sigi/spectre
```

Zwei Exporte (~2 × 13 min) gegen den Main-Checkout, Vergleich; nur ein identisches + grünes Paar ersetzt
`parity/goldens/` (sonst bleiben beide Läufe im Temp-Ordner, `--force` übernimmt Lauf 1). Verweigert bei
schmutzigem `scripts/`/`templates/`. Für diesen Commit: identisches Paar mit den 2 Fails oben, Lauf 1
übernommen (= `--force`). Routine (Etappenstart und nach jedem Merge, der `scripts/`/`templates/` ändert),
Korpus-Nachzug und Prüfbefehle: `parity/README.md`.

## Wie die Goldens entstehen

- **Korpus-Overlay:** Der Export liest Fixture-Frames nur aus dem eingefrorenen Korpus, nie live aus
  `.spectre` (Hooks auf `open`/`io.open`/`os.stat`/`os.path.exists|isfile|getsize`; jeder `*.png`-Pfad unter
  `.spectre` → `frames.json`; nicht abgebildete gelten als fehlend). Ohne das waren zwei Exporte
  verschieden: Die Live-Lane hat während eines Laufs 417 Dateien nach `trash/` verschoben (Skips 105 → 128).
  Deshalb hält der Korpus die **Original-Bytes** (Datei-Hash-Prüfungen wie `test_frame_regression`:
  checked=62/62). Live gelesen wird nur noch `shots-43184` (ein Verzeichnis-Check).
- **Flows** (pro Test, je FakeDevice ein Record, plus ein `dev: null`-Record für I/O ohne Device —
  128 solcher Records): `shot` (3666), `ocr` (3576), `tap` (1692), `sleep` (589), `ret` (411: rc + echte
  argv von `main()`, Exceptions als `raise` + rc 1), `key` (360), `adb` (159), `stub` (138: von Tests ersetzte
  Bot-Funktionen samt Rückgabe), `run` (87: gemockte `subprocess.run`-argv), `now` (41, nur wo Tests die Uhr
  patchen), `swipe`, `seq`, `hold`; dazu `overrides` (gepatchte Modul-Konstanten) und stdout.
- **Wie gefangen:** FakeDevice-Methoden auf Klassenebene (alle Unterklassen, Tiefen-Guard) und ein Hook auf
  `unittest.mock`-Patches: Was ein Test auf ein Bot-Modul, auf FakeDevice, auf
  `time.sleep/monotonic/time/perf_counter` oder `subprocess.run` patcht, läuft durch einen transparenten
  Proxy (2626 Patches; `assert_called…` usw. erreichen weiter den Mock). Ein unabhängiges 3-Linsen-Review
  fand in der ersten Fassung verlorene Events (Tests, die `hl.key`/`v.ocr_region` nach dem Device patchen),
  falsche argv in `ret` und fehlende rc bei Exceptions — alle behoben, per Smoke-Läufen belegt.
- **Calls:** äußerste Aufrufe von `classify*/is_*/find_*/read_*/parse_*` mit Frame-, Zeilen- oder
  Tupel-Argumenten, dedupliziert (1362); unrein (I/O im Aufruf) → kein Call (111).
- **Ledger-Keim** `tests.json`: alle 1005 Test-IDs mit Ergebnis und Record-Zählern: 639 mit Flows,
  361 mit Calls, **220 grüne Tests ohne Record** (u. a. 49 `test_afk_daily_exit_code` = Bash-Wrapper, E6;
  `test_bot_lock`, `test_wall_dash`, `test_frida_kit` = Tooling) → Kandidaten für `manual`/`out_of_scope`.

## Dead Specs

Von den 64 Frames, die beim Sammeln fehlten, holt der Korpus **28** aus `.spectre/trash/` zurück (F16-Prune
hatte sie verschoben). **36 fehlen überall** — sie stehen in `goldens/tests.json` → `overlay.hidden`
(u. a. `shots-77952/fix_intro_0..3`, `shots/arena_*` (3), `shots-49936/sp_auto_*` (2),
`shots-76112/dg_cam_3|4`, `world_now.png`, `world_banner_frame.png`, `game_boot.png`, `hall.png`). Ersatz
nur, wenn Hermes Frames derselben Screens liefert.

**Vorsicht bei den 28 zurückgeholten:** `shots-<pid>`-Ordner können bei PID-Wiederverwendung denselben
Namen tragen. Für die zwei Fails oben spricht alles für den richtigen Frame; für statisch referenzierte
Frames aus `trash/` gibt es aber keinen Hash im Test, der das beweist (`frames.json`: `found_at` mit `/trash/`).

## Abweichungen vom Plan / noch offen (E0b-2, vor oder mit E1)

1. **Virtuelle Uhr fehlt.** `now`-Events nur, wo Tests die Uhr patchen. Im stdout werden Uhrzeit/Datum und
   Battle-Metrik-Dauern (`wall=…s`, `wall mean/min/max …s`) als `<TIME>/<DATE>/<DUR>` maskiert, Temp-Pfade
   überall als `<TMP>`. Exakt wird das erst mit der virtuellen Uhr.
2. **Nicht gebaut:** Fault-Injection (`faults.jsonl`), Ledger per AST (`manual: {rust_test, asserts}`,
   `dead`), `sys.setprofile`-Selbsttest, Zweigabdeckung, `libm.jsonl`, `pystr.jsonl`, rohes OCR (`ocr.jsonl` —
   in der Suite ist OCR durchweg gemockt), getrenntes `argv.jsonl` (argv steckt als `adb`/`run`-Events in den
   Flows), Vertragszeilen-Liste im stdout, `fs_after`, `scope/E<n>.toml`.
3. **Bewusst ausgelassen:** `avg` und `lum` als Calls — Primitive, die Detektoren in Scan-Schleifen auf
   oberster Ebene rufen (`avg` allein 268 694 Records / 58 MB). Abgedeckt durch den korpusweiten
   Differential-Lauf in E2 („avg an jeder Probe-Koordinate“).
4. **Bekannte Lücken:** reine Calls innerhalb eines unreinen Calls fehlen; Pixel-Schreibzugriffe per
   `load()[x, y] = …` in einer Vision-Funktion würden nicht als Mutation erkannt (nur
   ImageDraw/paste/putpixel); `afk-daily-gift.py`, das `test_afk_memory` erst zur Laufzeit lädt, ist nicht
   umhüllt; `afk_daily_gift` / `afk_daily_gift_t104` sind dieselbe Datei unter zwei Lade-Namen;
   `taps_mismatch` (5 Records) ist eine Heuristik — alle 5 sind `real_seq`-Batches über adb.
5. **STALE in Rust** ruft `export_goldens.py py-tree` über `python` auf (eine Definition, keine
   sha2-Dependency); ohne python: Skip bzw. strict FAIL.
6. **Dependencies:** `png 0.18.1` zog 9 Pakete in `Cargo.lock`: adler2, crc32fast, fdeflate, flate2,
   miniz_oxide 0.8.9 + 0.9.1, png, simd-adler32 und **zlib-rs 0.6.8** (Default-Backend von flate2 1.1.10;
   stand nicht in der Plan-Liste D1). Alles offline aus dem Registry-Cache.

## Vorfall: Schreibzugriff in E0a

Der **erste `collect`-Lauf** (Suite im Main-Checkout, noch ohne Schreibschutz) hat kurzzeitig
`.spectre/shots-65504/` (36 von Tests erzeugte Bilder, Prozess-PID) angelegt und wieder entfernt — das macht
die Suite immer so (`v.TMP = .spectre/shots-<pid>`). Netto-Zustand vorher/nachher per Dateiliste geprüft:
identisch, nichts der Live-Lane berührt. Seitdem laufen `collect` und der Export mit `v.TMP` im Temp-Ordner
und einem Audit-Hook, der jeden Schreibversuch unter `.spectre` blockt und listet (alle Exporte: 0).

## Testausgabe

```
$ python scripts/tests/parity/export_goldens.py check --repo C:/Users/Sigi/spectre
export: 1005 tests (2 fail, 0 err, 31 skip) in 785s; 655 flows / 10802 events (5 taps mismatch), 1362 calls, 287 synthetic frames, 0 conflicts, 0 .spectre writes blocked -> …\parity-goldens-wz28rcgl\run1
export: 1005 tests (2 fail, 0 err, 31 skip) in 750s; 655 flows / 10802 events (5 taps mismatch), 1362 calls, 287 synthetic frames, 0 conflicts, 0 .spectre writes blocked -> …\parity-goldens-wz28rcgl\run2
check: NOT copied (0 files differ, run rc [1, 1])          # -> Lauf 1 übernommen, determinism.json: deterministic true
frame regression: checked=62 skipped=0 manifest=62
live .spectre changed lines during run: 0

$ python scripts/tests/parity/verify_corpus.py
verify_corpus: 230/230 ok (C:\Users\Sigi\spectre-parity\frames)

$ SPECTRE_PARITY=1 cargo +stable-x86_64-pc-windows-gnu test -p spectre-afk -- --nocapture
goldens: 2017 records, 73 distinct call fns, py_tree 03cc13204eef9bbf
PARITY: 73 unported fns (expected in E0b)
corpus: 230 frames, 230 decoded, 0 missing, 0 bad
test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 115.50s

$ python -m unittest discover -s scripts/tests/parity -p "test_*.py"
Ran 7 tests … OK
```

(„31 skip“ ist die unittest-Zählung, in der übersprungene Subtests einzeln zählen; im Ledger stehen 10 Test-IDs mit `outcome: skip`.)

## Nächster Schritt

Review durch Hermes. Offen zur Entscheidung: (a) der Arena-Befund in die Python-Fix-Queue?
(b) E0b-2 (v. a. virtuelle Uhr + Ledger) vor E1 oder parallel? (c) Ort der Zip-Kopie (User).
