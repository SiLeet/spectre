# parity/ — Python-Spezifikation für den Rust-Port (E0a/E0b, T115)

Plan: `docs/reports/rust-port-plan.md` §E0a, §E0b, §4. Bericht: `docs/reports/rust-port-E0.md`.

| Pfad | Inhalt | Erzeugt von |
|---|---|---|
| `frames.json` | Korpus-Manifest: sha16 → referenzierte Pfade (+ Fundort, Bytes, file_sha16), w, h, mode, crc32 (RGB-Bytes), alpha_min, rgb_sha16, wie gefunden | `freeze_corpus.py freeze` |
| `spectre-filelist.json` | eingefrorene Dateiliste von `.spectre` (Pfad, Größe, sha16 der Bytes) für den E2-Differential-Lauf | `freeze_corpus.py freeze` |
| `goldens/flows/<test_modul>.jsonl` | pro Test: ein Record je FakeDevice (+ einer für I/O ohne Device): geordneter Event-Strom, Overrides, stdout | `export_goldens.py` |
| `goldens/calls/<bot_modul>.jsonl` | äußerste reine Aufrufe (Frame / OCR-Zeilen / Tupel → Ergebnis), dedupliziert | `export_goldens.py` |
| `goldens/tests.json` | pro Test-ID Ergebnis + Record-Zähler (Ledger-Keim), Laufsumme | `export_goldens.py` |
| `goldens/synthetic.json` | von Tests gebaute Frames (PNG in `$SPECTRE_PARITY_DIR/synthetic/`; `alias_of` = `convert('RGB')` eines Korpus-Frames, nicht doppelt gespeichert) und große Byte-Payloads (`blobs/`) | `export_goldens.py` |
| `goldens/determinism.json` | Vergleich der zwei Exporte | `export_goldens.py check` |

Die Bilder selbst liegen **außerhalb jedes Repos** unter `$SPECTRE_PARITY_DIR`
(Default `C:/Users/Sigi/spectre-parity/`): `frames/<sha16>.png` (Korpus: **Original-Bytes** der Quelldatei,
schreibgeschützt), `synthetic/<sha16>.png`, `blobs/<sha16>.bin`. sha16 = `sha256(f"{mode}|{w}x{h}|" + RGB-Bytes)[:16]`.

**Overlay:** Der Export liest Fixture-Frames **nur aus dem Korpus**, nie live aus `.spectre`: jeder `*.png`-Pfad
unter `.spectre` wird über `frames.json` auf `frames/<sha16>.png` abgebildet (Original-Bytes, damit auch
Datei-Hash-Prüfungen wie `test_frame_regression` stimmen); nicht abgebildete PNGs gelten als fehlend. So ist
der Export unabhängig davon, was die Live-Lane währenddessen prunt oder nach `trash/` verschiebt.

## Prüfen

```bash
python scripts/tests/parity/verify_corpus.py                 # Korpus gegen frames.json (sha16 neu berechnet)
python -m unittest discover -s scripts/tests/parity -p "test_*.py"   # Selbsttests des Toolings (nicht Teil der Bot-Suite)
SPECTRE_PARITY=1 cargo +stable-x86_64-pc-windows-gnu test -p spectre-afk --test parity   # Rust: alle Frames dekodieren (crc32 == Pillow), STALE, Frame-Keys
```

## Re-Export (Routine am Start jeder Etappe und nach jedem Merge, der `scripts/` oder `templates/` ändert)

Voraussetzungen: Main-Checkout `C:/Users/Sigi/spectre` mit `.spectre/`, `scripts/` + `templates/`
sauber (sonst verweigert der Exporter), kein adb nötig. Der Export schreibt nichts nach `.spectre`
(Audit-Hook blockt und listet jeden Versuch; der Shot-Ordner `v.TMP` zeigt auf ein Temp-Verzeichnis).

```bash
# 1) (nur wenn neue Fixture-Frames dazugekommen sind) Korpus nachziehen
python scripts/tests/parity/freeze_corpus.py collect --repo C:/Users/Sigi/spectre --refs %TEMP%/refs.json
python scripts/tests/parity/freeze_corpus.py freeze  --repo C:/Users/Sigi/spectre --refs %TEMP%/refs.json
python scripts/tests/parity/verify_corpus.py

# 2) Goldens: zwei Exporte, Vergleich; nur ein identisches, grünes Paar ersetzt parity/goldens
python scripts/tests/parity/export_goldens.py check --repo C:/Users/Sigi/spectre

# 3) Diff lesen: jede geänderte Zeile in goldens/ ist eine Python-Verhaltensänderung
git diff --stat parity/
```

`collect` läuft die Suite einmal (~15 min), `check` zweimal (~2 × 20 min). Ein Golden-Diff ergibt die
Liste der betroffenen Rust-Module (Follow-up); ist ein Task in Rust schon grün, gilt die Freeze-Regel
aus §E0b. Stand der Goldens = `header.py_tree` (sha16 über `git ls-tree -r HEAD -- scripts templates`
ohne `scripts/tests/parity/`); `export_goldens.py py-tree` zeigt den aktuellen Wert, `parity.rs`
meldet STALE, wenn beide abweichen.

`collect` und `check` laufen beide mit dem `.spectre`-Schreibschutz (der E0a-Lauf selbst lief noch
ohne ihn, siehe Bericht).
