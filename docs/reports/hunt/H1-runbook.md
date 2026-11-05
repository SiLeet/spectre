# H1 — Fahrplan: Homestead-Gold, Amber, Bau-Queue (live, Hermes)

Stand 2026-11-05 (T113). Antwort auf Hermes' Rückfrage: exakte Befehlsfolge + Ergebnisformat.
Arbeitsteilung: **Hermes** fährt live und legt Logs/States/Dumps ab; **Claude** wertet aus und
schreibt die Relokation + `offsets.yaml` (erst nach dem Neustart-Check). Ersetzt den H1-Abschnitt
in `docs/reports/memory-first-audit.md`.

## GOLD: DONE (Slot + Offsets) — T116, 2026-11-05 (1 Prozess, Neustart-Check offen)

Homestead-Gold ist gefunden (Hermes live, pid 4039; Gold aus dem Requests-Panel bzw. dem Spire-Dialog,
**nicht** das Helden-Gold 8,57M):

- **Slot:** `0x7607b07518c8` = Region `0x7607b0000000` (eigene RW-Region, nicht die Power-Region
  `0x7607E0000000`) + Offset `0x7518C8`. Typ u32; live als u64 gelesen derselbe Wert (oberes Dword 0).
- **Beweis-Kette:** (1) `search u32 653198` (Requests-Panel) → genau 1 Kandidat `0x7607b07518c8`;
  (2) späterer Direkt-Read → 654398 = Spire-Dialog „654.398" (Gold war live gestiegen);
  (3) `search --continue u32 654398` → der Kandidat bleibt der einzige Treffer.
- **Umgebung (64 B):** `3e fc 09 00 | 00 00 00 00 | 03 44 | …` (Record mit `0x4403`-Marker).
  Die Nachbar-u32 `0x02e6bd` (190141) und `0x05f5e121` (100000033) sind Amber-/Power-Kandidaten
  für die nächste Runde.
- **Eingetragen:** `offsets.yaml` → `Homestead.gold` (U32, min 0, max 1e9);
  `scripts/afk_memory.py` → `gold(pid, gold_base)` (u32 und u64 müssen gleich sein und im Bereich
  liegen, sonst `invalid`), `gold-state.json` `{offset, base?, pid?}`, `--show --gold-base`.
- **Offen:** Neustart-Check (gleicher Offset `0x7518C8` in der neuen Gold-Region nach einem neuen PID)
  und wie die Gold-Region ohne Suche gefunden wird. Bis dahin: Region-Base pro Prozess per
  `search` + `gold-state.json` setzen; OCR bleibt Fallback.

## Was sich gegenüber dem Audit-Plan ändert

- **Felder stehen auf 16/16** → „genau 1 Field bauen (−100 Gold / −10 Amber)" geht nicht mehr.
  Stattdessen gilt für jeden Wert: **vorher und nachher exakt vom Bildschirm ablesen** (v0 → v1) und
  mit diesen Zahlen suchen — egal welcher Auslöser. Kein fester Kostenbetrag mehr in den Befehlen.
- Auslöser (nur ohne Diamanten, kein „Complete Now"): ein Level Up eines Gebäudes, dessen Dialog
  Homestead-Gold/Amber verlangt (Spire/Küche/Refinery, Kosten auf der Karte), oder ein Bau einer
  weißen Kachel (T105). Ein Level Up startet zugleich einen Bau-Timer → die Queue geht q0 → q0+1
  (Hammer oben rechts, z. B. 0/2 → 1/2): **ein Auslöser liefert G, A und q zusammen.**
- Kleine Werte (Queue, Amber falls zu häufig) über den neuen **Slot-Modus von `dumpdiff`** (T113):
  `--value-type u32 --from v0 --to v1` listet direkt die Slots mit genau diesem Übergang.
  Dafür die CLI aus diesem Branch bauen (`cargo +stable-x86_64-pc-windows-gnu build --release -p spectre-cli`).

## Vorbedingungen

- PC idle, kein Bot-Lauf (Bot-Lock frei), nichts anderes auf adb; spectre-mcp bzw. die CLI ist
  allein auf adb (nie parallel).
- `PID` und `BASE` aus `.spectre/power-state.json` (zuletzt pid 4039, base `0x7607E0000000`);
  nach jedem Spiel-Neustart neu.
- Ablage: `SP=%TEMP%/spectre-hunt` (alle Dateien unten mit Präfix `h1_`).
- Werte ablesen und notieren: `G0` (Gold, Ressourcenleiste oben, z. B. 653,402 → 653402),
  `A0` (Amber, z. B. 3848), `q0` (Queue-Zähler, z. B. 0 aus „0/2").

## Befehlsfolge

```bash
# 0) Regionen sichern + Heaps wählen: die 8 größten unbenannten rw-Regionen (wie `spectre hunt`)
#    plus die Region, die BASE+0x4A728 (team_power-Slot) enthält. Je Heap k: START_k, SIZE_k
#    (SIZE_k = min(Regionsgröße, 64 MiB)).
spectre regions $PID --adb --filter rw --json > $SP/h1_regions.json

# 1) Vorher (v0)
spectre search $PID u32 $G0 --adb --state $SP/h1_gold_u32.json
spectre search $PID i64 $G0 --adb --state $SP/h1_gold_i64.json
spectre search $PID f64 $G0 --adb --state $SP/h1_gold_f64.json
spectre search $PID u32 $A0 --adb --limit 20000 --state $SP/h1_amber_u32.json
#    -> meldet die Amber-Suche das Limit (20000), Amber NICHT weiter per search, nur per Dump-Diff (Schritt 4)
for k in 1..9: spectre dump $PID $START_k $SIZE_k --adb --format raw --output $SP/h1_${k}_0.dump

# 2) Auslöser (ein Level Up / ein Bau, keine Diamanten), dann G1, A1, q1 exakt ablesen

# 3) Nachher (v1)
spectre search $PID u32 $G1 --continue --adb --state $SP/h1_gold_u32.json
spectre search $PID i64 $G1 --continue --adb --state $SP/h1_gold_i64.json
spectre search $PID f64 $G1 --continue --adb --state $SP/h1_gold_f64.json
spectre search $PID u32 $A1 --continue --adb --state $SP/h1_amber_u32.json   # nur wenn Schritt 1 unter dem Limit blieb
for k in 1..9: spectre dump $PID $START_k $SIZE_k --adb --format raw --output $SP/h1_${k}_1.dump

# 4) Dump-Diff im Slot-Modus (offline, kein adb nötig)
for k in 1..9:
  spectre dumpdiff $SP/h1_${k}_0.dump $SP/h1_${k}_1.dump --base $START_k --value-type u32 --from $q0 --to $q1 --json > $SP/h1_${k}_queue.json
  spectre dumpdiff $SP/h1_${k}_0.dump $SP/h1_${k}_1.dump --base $START_k --value-type u32 --from $A0 --to $A1 --json > $SP/h1_${k}_amber.json
  spectre dumpdiff $SP/h1_${k}_0.dump $SP/h1_${k}_1.dump --base $START_k --value-type u32 --from $G0 --to $G1 --json > $SP/h1_${k}_gold.json

# 5) Stabilität: 60 s nichts tun, dann dieselben --continue-Läufe mit G1 / A1 noch einmal (Werte unverändert)

# 6) Kontext je Überlebendem (Adresse X): 96 Bytes ab X-32
spectre dump $PID $((X-32)) 96 --adb > $SP/h1_ctx_<X>.txt

# 7) Später, nach einem Spiel-Neustart: neuer PID/BASE, Werte neu ablesen, Schritt 1 für G erneut,
#    und prüfen, ob der Abstand der Treffer zu BASE / zum team_power-Slot gleich geblieben ist.
```

Hinweise: `$((X-32))` u. Ä. vorher ausrechnen (die CLI rechnet nicht). `search --continue` liest jeden
Kandidaten einzeln über adb (~0,15 s pro Kandidat) — bei > ~10 000 Kandidaten nach Schritt 1
abbrechen und nur den Dump-Diff nutzen. Ein Wert, der zwischen Schritt 1 und 3 nebenbei weiterläuft
(z. B. Einnahmen), fällt aus `--continue` heraus — dann den Auslöser schneller hinter Schritt 1 legen.

## Ergebnisformat (pro Wert eine Datei)

`docs/reports/hunt/H1-<wert>.md` (gold, amber, queue), Vorlage: `docs/reports/hunt/TEMPLATE.md`.
Rohdateien bleiben unter `%TEMP%/spectre-hunt/` (Pfade in der Datei nennen).

## Danach (Claude)

Aus den Ergebnisdateien: Typ + Offset relativ zur Region/BASE, Vergleich mit dem Neustart-Check,
Relokationskette wie bei team_power (`afk_memory.power()`: Slot-Datei + Drift-Guard), Eintrag in
`offsets.yaml` mit `min`/`max`, OCR bleibt Fallback. Ohne Neustart-Check kein yaml-Eintrag.
