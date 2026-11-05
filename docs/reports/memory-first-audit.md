# T110 — Memory-First-Audit (2026-11-05)

Für Hermes. Offline erarbeitet (Branch `feature/T110-memory-audit`, Worktree `spectre-w7-T110`):
kein adb, kein MCP, `.spectre` nur read-only gelesen. Belege sind gespeicherte Logs, State-Dateien,
Hunt-Logs und Code.

**Regel ab jetzt:** Werte = Memory (Rust, `spectre read-batch` über `scripts/afk_memory.py`),
Navigation = Taps/Vision (Python), neue Logik Rust-first. OCR bleibt für einen Wert nur so lange,
bis ein Offset mit Relokations-Story belegt ist. Danach dient OCR nur noch als Fallback.

## Kurzfassung

- **Belegt im Memory ist genau ein Wert: `team_power`.** Er ist schon verdrahtet (afk_memory.power →
  memory_preflight, read-batch mit Dump-Fallback, Drift-Guard). Es gibt also kein Skript, das heute
  auf Memory umgestellt werden kann. Teil (3) des Briefs hat deshalb keine Umstellung. Erfunden wird
  kein Offset.
- **Rust ausgebaut:** `read-batch` kennt jetzt pro Feld `min`/`max` (inklusiv). Ein Wert außerhalb
  des Bereichs bleibt als `value` sichtbar, kommt aber mit `valid: false` und
  `note: "out of range [min, max]"` zurück. `spectre offsets` / `validate` melden `min > max`, NaN und
  Ranges auf Nicht-Zahlen-Typen (Bool/Pointer/String) als Fehler. `afk_memory.snapshot` ignoriert
  `valid: false` schon heute, deshalb ist auf der Python-Seite keine Änderung nötig.
- **offsets.yaml:** `Resources.team_power` hat jetzt `min: 100000`, `max: 10000000000` (dieselben
  Grenzen wie `GUARD_LO`/`GUARD_HI` in afk_claim_vision). Header und Kommentare sagen klar, was gilt:
  Offsets gelten **pro Prozess**, das statische `0xA578` ist STALE, `gold @0x0` ist **kein** Offset
  (server-side), `afk_pool_*` sind STALE seit dem Neustart am 10-31.
- **README der Offsets korrigiert:** Die Tabelle mit „1.0.45 ✅ Verified“ und der Text zum
  „gold-spend diff“ waren falsch (diesen Diff hat es nie gegeben).
- Alles Weitere ist **needs live hunt** (Plan unten) oder server-side bzw. nicht sinnvoll.

## Grundproblem: Offsets sind pro Prozess

Die Heap-Basis ist ASLR. Zusätzlich wandert der Slot **innerhalb** der Region:

| Zeitpunkt | Form | Offset (rel. Heap-Basis) |
|---|---|---|
| 10-31 / 97b32ee | I64, Hot-Pattern `0a f7 03 00` = 259850 | `0xA578` |
| nach Neustart (T44) | u32-Map-Eintrag `[u32 Wert][u32 Hash][Heap-Ptr]` | `0x2FE8`, später `0x1BD838` (pid 5176) |
| 11-04 19:09 (pid 4039) | u64/I64-Anzeigekopie (width 8, **ohne** Map-Eintrag-Form) | `0x4A728` (= 304936) |

Beleg `.spectre/power-state.json`: `offset 304936, width 8, power 258316, pid 4039,
base 0x7607E0000000, revalidated true, 2026-11-04T19:09:36`. width 8 heißt: `memory_preflight`
(afk_claim_vision) akzeptiert einen 8-Byte-Slot nur, wenn er **keine** Map-Eintrag-Form hat
(`entry_valid = map_entry_shape if width == 4 else not map_entry_shape`). Die Relokation wählt
width 8 nur für eine u64-Anzeigekopie. u32-Map-Eintrag (width 4) sind nur `0x2FE8` und `0x1BD838`.
Logs `.spectre/logs/afk-bot-2026-11-0*.log` enthalten `preflight team_power = 257636` 21×, `= 258316` 18×
und `= 258488` 11×.

Folge: Jeder neue Wert braucht eine **Relokations-Story**, bevor er dem Bot nützt. Das ist entweder
ein konstanter Abstand zu einem Anker (team_power-Slot, player_id-Treffer) oder eine
Byte-Signatur (`spectre hot`). Ein nackter Offset in offsets.yaml gilt nur für einen pid.

## Audit pro Wert

Legende: **MEM** = Memory mit Offset · **OCR** = heute OCR/Pixel (Fallback bleibt) ·
**HUNT** = needs live hunt · **SERVER** = server-side, nicht memory-adressierbar ·
**N/A** = nicht sinnvoll/möglich.

| # | Wert | Gelesen in (Entscheidung) | Heute | Status | Begründung / Beleg |
|---|---|---|---|---|---|
| 1 | Team-Power (HUD „259K“) | `afk_memory.power()` → `memory_preflight`; Aufrufer: afk_claim_vision, afk_dailies, afk-daily-gift, afk_dream_realm, afk_stage_push. `fail` → Exit 2 vor jedem Tap | Memory (read-batch, Dump-Fallback, Drift-Guard) | **MEM** (relokiert) | Einziger verifizierter Wert (siehe oben). Wave-5 R21: read-batch byteidentisch zum Dump. Drift-Gate kam nach dem Fehl-Accept von 108449240 am 11-03 dazu (80b8b43). Jetzt zusätzlich Range in offsets.yaml. |
| 2 | Helden-Gold („8572K/9390“) | `afk_hero_level.cost_pairs/costs_ok` (Kosten nicht gedeckt → Lauf endet mit rc 4, kein Charge heute) | OCR | **SERVER** (mit Vorbehalt) | T23 (10-31, `scripts/wallet-hunt-all.py`): 3-Punkt-Hunt über 625 anon-rw-Regionen + 6 große Heaps (~1 GB), 377631 Rohtreffer, nur Alloc-Muster. T11 negativ als u32/u64/f32/f64. Logs `%TEMP%/spectre-gold/{goldhunt,goldhunt2,walletall}.log`. **Vorbehalte:** T23 ging von ~9.963 Gold aus, echtes Helden-Gold ist 8,57 M (Wave-7-Korrekturen). Im 625-Regionen-Durchgang schloss der Filter 200 ≤ Δ ≤ 20000 Claims von 117k aus, und Regionen < 64 KiB wurden übersprungen. Die 6 großen Heaps (goldhunt A/B/C) wertete `scripts/gold-analyze.py` dagegen bis Δ 5 000 000 aus. Eine verschleierte Speicherung ist möglich. → optionaler Re-Test (H3). |
| 2b | Helden-EXP / Essenz (Kostenzeile „5256K/91K“) | `afk_hero_level.cost_pairs` → `costs_ok`/`no_effect_verdict` (nicht gedeckt → rc 4 Stop; gedeckt + unverändert → rc 1 Retry; „resources exhausted (hero EXP/gold out)“) | OCR | **HUNT** | Eigene Währung, das T23-Urteil deckt nur Gold ab. Nie gehuntet. Gleicher Lauf wie H3 (EXP-Range-Suche). |
| 3 | Homestead-Gold / Amber (Ressourcenleiste „653,402 / 3848“) | `afk_homestead.parse_resources` (< FIELD_COST → Field-Kachel übersprungen) | OCR | **HUNT** | Andere Währung als Helden-Gold. Nie gehuntet. Exakter Wert und exaktes Delta (Field = 100/10) → bestes Differential. Gleichzeitig Kontrollexperiment für das T23-Urteil. |
| 4 | Homestead Bauzähler „N/16“ (Field u. a.) | `afk_homestead.read_counter/tile_counter` (voll → Skip; nach dem Bau muss +1 stehen, sonst ERROR-Stop) | OCR (Multi-Crop-Votes) | **HUNT** | OCR schwach (kurze Zähler „1/1“, „2/2“ lesen None). Gleicher Hunt-Durchgang wie #3. |
| 5 | Homestead Bau-Queue „n/m“ (Hammer 0/2) | `afk_homestead` main, `afk_homestead_upgrade.parse_queue` (voll → kein Bau / kein Level-Up) | OCR | **HUNT** | Kleine Zahl → viele Starttreffer. Mit Bau-Differential 0→1 im selben Durchgang wie #3. |
| 6 | Homestead-Stamina „3000/3000“ | `afk_homestead_requests.stamina` (< 1000 → kein Kochen) | OCR | **HUNT** | `Resources.energy @0x10` ist Platzhalter. Nicht beim Cap starten (3000 = Konstante). |
| 7 | Küche Stock / Request | `afk_homestead_requests.deck_counts` (Make solange stock < req) | OCR | **HUNT** (niedrige Prio) | Kleine Zahlen, pro Rezept eigener Slot. Erst nach #3/#6. |
| 8 | Upgrade-Requirement „(5/7)“ | `afk_homestead_upgrade.parse_requirement` (met < total → kein Level-Up) | OCR + Pixel | **OCR** (vorerst) | Abgeleiteter Wert, ändert sich nur bei Gebäude-Level-Ups. Hunt lohnt erst, wenn die Gebäude-Level-Struktur gefunden ist (#8b). |
| 8b | Gebäude-Level (Radiant Spire, Küche usw.) | `afk_homestead_upgrade` (Pixel `level_icons` / Level-Up-Scheibe; das Label „Level N“ wird übersprungen, nicht geparst) | Pixel | **HUNT** | +1 pro Level-Up als Differential, gleicher Durchgang wie #8. |
| 9 | Dream-Realm-Chancen „N/7“ | `afk_dream_realm.parse_chances` (0 → Stop vor start_fight) | OCR | **HUNT** | Log 11-04: `fight 1: chances left = 7` … `fight 7: chances left = 1` und einmal `unreadable`, also fragile OCR. Ideale monotone Folge 7→1. |
| 10 | Arena-Freiversuche | `afk_arena` (Erschöpfung nur über Kaufdialog → CANCEL + Stop) | Pixel (kein Zähler) | **HUNT** | Ein Memory-Zähler würde das riskante Dialog-Gate ersetzen. Log 11-04: `STOP: daily arena attempts exhausted (purchase dialog cancelled)`. |
| 11 | Arena-Rating | nirgends | – | **HUNT** (optional) | Kein Skript liest es. Kein Entscheidungswert. |
| 11b | Arena-Gegner-Power (Select Opponent) | nirgends (immer linke Karte; shortcut-Kommentar in `afk_arena.py`) | – | **N/A** für Memory | Transient pro Refresh wie die Gegner-Power in #15. Falls die Wahl je nötig wird: OCR. Die Entscheidungslücke ist bekannt. |
| 11c | Tickets (Recruit 1 260 / Honor-Duel / Arena-Kauftickets) | nirgends (kein Skript nutzt sie) | – | **HUNT** (optional) | Kein heutiger Konsument. Arena-Tickets sind derselbe Zähler wie #10 (TODOS: 5 frei + 5 kaufbar). |
| 12 | Helden-Level je Hand („Level 85/100/110“) | `afk_hero_level.slot_level/shown_level` (niedrigste Hand; nachher == vorher+1) | OCR | **HUNT** | Log 11-04: Hand 730 `not readable`. `HeroInfo @0x3A4B5C00` ist Platzhalter. Resonanz-Cap „Level 100“ ≠ Helden-Level (R22). |
| 13 | Resonanz-Level („Resonance Level: 80“) | `afk_hero_level` main (nur Log, Navigations-Gate über Textpräsenz) | OCR | **OCR** (nur Log) | Keine Entscheidung hängt am Wert. |
| 14 | Homestead-Quest-Text („Build Field x2“) | `afk_homestead.quest_text`, `afk_homestead_upgrade.quest_building` (Zielwahl) | OCR | **OCR** (Navigation) | Text/Navigation, kein Zahlenwert. Bleibt Vision. |
| 15 | AFK-Stage („AFK Stage 249“) + Battle-Power auf Prep | `afk_stage_push.parse_stage/parse_power` → `wall-report.log`, afk-wall-dash | OCR | **HUNT** (Stage) / **N/A** (Gegner-Power) | Nur geloggt. Stage hat einen sauberen +1-Schritt pro Sieg. Gegner-Power ist transient pro Kampf. |
| 16 | Dura's Tokens „N/6“ + Floor | `afk_duras.parse_tokens/parse_floor` (0 → kein Kampf; Sweep muss N-1 lesen) | OCR | **HUNT, blockiert** | TODOS R24: Dura fehlt im Battle-Modes-Menü (nicht freigeschaltet bei H143). Keine Frames. |
| 17 | Gilden-Tokens („28 704“) | `afk_guild.token_balance` (nur Log, LOG-ONLY-Käufe) | OCR | **HUNT** | README listet `guild_tokens @0x18` aus der Vorlage, nie gemessen. |
| 18 | Gilden-Shop-Preise | `afk_guild.store_items/plan_buys` (nur Log) | OCR | **OCR** | Item-Liste = UI-Daten, pro Öffnen neu. Kein Hunt. |
| 19 | Diamanten | nirgends gelesen (OCR schneidet „44“ ab); Kaufdialoge → immer CANCEL | – | **HUNT** | `Resources.gems @0x08` ist Platzhalter. Beleg OCR: Shop-Header „Diamanten 31 920“ (T11). Nie mit Ausgabe als Differential testen. |
| 20 | Gildentruhen-Countdown („3d 22h“) + andere Timer | `afk_guild.chest_hours` (nur Log) | OCR | **HUNT** (End-Epoch) | Timer liegen meist als End-Epoch im Speicher. Der Countdown selbst ändert sich dort nicht. |
| 21 | Guild-Duel-Phase + Challenge-Badge | `afk_guild.duel_phase/challenge_badge` (nur Log) | OCR + Pixel | **OCR** | Text/Badge = Navigation. |
| 22 | AFK-Truhe/Idle-Timer, AFK-Pools | `afk_claim_vision.claim_round` (kein Popup → rc 4) | Pixel | **N/A** (bisher negativ) | T23: Sekundenzähler (+25 s exakt), Epoch, BE, f32/f64 und AFK-Raten 20743/56170/1529 sind alle NEGATIV. `afk_pool_*` (+0x453B58/+0x453B90) wuchsen am 10-31 und sind seit dem Neustart STALE. Offen ist nur ein Epoch in Millisekunden (H8). |
| 23 | HP im Kampf | nirgends (nur visueller Boss-Balken) | – | **N/A** | Keine Entscheidung. Kampfobjekte sind transient (neue Adresse pro Kampf). |
| 24 | Spieler-Identität (player_id 60068087, „SiLeet“) | nirgends | – | **HUNT** (Anker) | Kein Entscheidungswert, aber konstanter exakter u32 (LE `f7 90 94 03`). Damit bester Relokations-Anker für eine Player-Struktur. |
| 25 | Platzhalter in offsets.yaml (PlayerState/TeamState/HeroInfo, gems, energy) | – | – | **N/A** (Vorlage) | Fake-Basen `0x1A2B3C00`/`0x2A3B4C00`/`0x3A4B5C00`. `Resources.base_offset 0x724DF0000000` ist die Basis eines toten Prozesses. Kommentiert, nicht gelöscht (Loader-Tests prüfen die Struktur). |

## Hunt-Plan für Hermes (live, seriell)

Allgemein:
- Nur bei idle PC, Bot-Lock frei und nichts anderes auf adb. spectre-mcp ist der einzige adb-Owner:
  **nie** CLI-search/hot parallel zu MCP oder Bot-Läufen.
- pid/base nach jedem Neustart neu über `scripts/afk-bot-watch.sh` holen (Stand 11-04: pid 4039,
  base `0x7607E0000000`).
- Eine `--state`-Datei pro Wert/Typ unter `%TEMP%/spectre-hunt/`. `search`/`--continue` **nur für
  markante Werte** (653402, Gold-Bereich, Epoch-Fenster): `--continue` liest jeden Kandidaten mit
  einem eigenen `adb shell su -c dd` (~0,15 s pro Aufruf; walletall.log: 550 Aufrufe in 83 s), und
  die exakte Suche hat keine Regionen-/Basis-Grenze. Liefert der erste Durchgang mehr als ~10k
  Kandidaten → abbrechen. **Kleine Werte** (Zähler, Level, Stage, Stamina) laufen über Dump-Diff
  (docs/memory-first.md): heiße Heaps (`spectre regions $PID --adb`) per
  `spectre dump $PID <start> <size> --adb --format raw --output <vorher|nachher>.dump` vor und nach
  der Aktion sichern, dann offline `spectre dumpdiff vorher.dump nachher.dump --base <start> --json`
  und nach Slots mit genau dem erwarteten Delta filtern (z. B. N→N+1, 7→6). Ein voller `hot`-Scan dauert ~13 min 39 s (mem_probe-Messung), deshalb
  `hot`-Scans nicht stapeln.
- Jeden Überlebenden mit Kontext sichern (`spectre dump $PID <addr-32> 96 --adb`) und **nach einem
  Spiel-Neustart** erneut prüfen. Abstand zum team_power-Slot bzw. zum player_id-Treffer notieren.
  Erst wenn der Abstand nach dem Neustart konstant ist, kommt der Wert mit `min`/`max` in
  offsets.yaml.

Ausdrücke wie `(G-100)` oder `G*1000` in den Befehlen sind Platzhalter: vorher ausrechnen, die CLI
rechnet nicht.

Reihenfolge nach Nutzen pro Aufwand:

> **Aktueller Fahrplan: `docs/reports/hunt/H1-runbook.md`** (Felder 16/16 → Auslöser per v0→v1, Slot-Modus von `dumpdiff`).

**H1 — Homestead-Gold + Amber + Field-Zähler + Queue (ein Field-Bau).** Exakten Wert G (z. B. 653402)
und A ablesen, N/16, Queue q.
```
spectre search $PID u32 G --adb --state %TEMP%/spectre-hunt/hs_gold.json
spectre search $PID i64 G --adb --state %TEMP%/spectre-hunt/hs_gold64.json
spectre search $PID u32 A --adb --state %TEMP%/spectre-hunt/hs_amber.json   # nur wenn A markant (> ~1000)
spectre dump $PID <start> <size> --adb --format raw --output %TEMP%/spectre-hunt/hs_0.dump   # N/16, q: Dump-Diff
# genau 1 Field bauen (afk_homestead.py, Kosten 100/10, Zähler N+1 geprüft)
spectre search $PID u32 (G-100) --continue --adb --state %TEMP%/spectre-hunt/hs_gold.json
spectre search $PID i64 (G-100) --continue --adb --state %TEMP%/spectre-hunt/hs_gold64.json
spectre search $PID u32 (A-10)  --continue --adb --state %TEMP%/spectre-hunt/hs_amber.json
spectre dump $PID <start> <size> --adb --format raw --output %TEMP%/spectre-hunt/hs_1.dump
spectre dumpdiff %TEMP%/spectre-hunt/hs_0.dump %TEMP%/spectre-hunt/hs_1.dump --base <start> --json   # N->N+1, q->q+1
# 60 s idle, dann jede Suche nochmal --continue mit denselben Werten (Stabilität)
```
Prüfen, ob Gold und Amber nebeneinander liegen und ob team_power oder player_id in der Nähe sind.
Ergebnis = Kontrolle für T23: Findet sich Homestead-Gold, war die Methode tauglich, und der Re-Test
H3 für Helden-Gold lohnt sich.

**H2 — Dream-Chancen 7→1 und Arena-Versuche (täglicher Lauf, kostet nichts extra).**
Kleine Werte → Dump-Diff statt `search` (ein u32-Suchlauf nach 7 oder 1 liefert Millionen Treffer):
```
spectre dump $PID <start> <size> --adb --format raw --output %TEMP%/spectre-hunt/dream_0.dump   # vor Kampf 1
# Kampf 1
spectre dump $PID <start> <size> --adb --format raw --output %TEMP%/spectre-hunt/dream_1.dump   # dann _2, _3 ...
spectre dumpdiff %TEMP%/spectre-hunt/dream_0.dump %TEMP%/spectre-hunt/dream_1.dump --base <start> --json
```
Gesucht: Slot mit 7→6→5 (übrig) bzw. 0→1→2 (verbraucht), als u32, i32 oder u16. Arena analog, aber
den **tatsächlich angezeigten** Rest-Zähler vor dem ersten Kampf ablesen und als Startwert nehmen
(keine gespeicherte Quelle belegt die Zahl der Freiversuche; TODOS nennt 5 frei + 5 kaufbar).
Gegenprobe nach dem Daily-Reset (Sprung auf 7 bzw. 0).

**H3 — Helden-Level + Helden-Gold-Re-Test (genehmigter Daily-Charge).** Level L der Hand, Kostenzeile
„G K/C“ ablesen.
Ob der HUD-Wert „K“ abgeschnitten oder gerundet ist, belegt nichts (8572K → 8553K nach 18840 passt
zu beidem), deshalb das Fenster ±1000. Kostenzeile „G K/C  E K/X“: E = EXP-Bestand, X = EXP-Kosten.
```
spectre search $PID u32 --min G*1000-1000 --max G*1000+1000 --adb --state %TEMP%/spectre-hunt/gold_u32.json
spectre search $PID u32 --min E*1000-1000 --max E*1000+1000 --adb --state %TEMP%/spectre-hunt/hero_exp.json
# dasselbe als i64 (gold_i64.json, hero_exp64.json) und f64 (gold_f64.json)
spectre dump $PID <start> <size> --adb --format raw --output %TEMP%/spectre-hunt/hl_0.dump   # Level L
# genau 1 Level laden (Kosten C Gold, X EXP)
spectre search $PID u32 --min G*1000-1000-C --max G*1000+1000-C --continue --adb --state %TEMP%/spectre-hunt/gold_u32.json
spectre search $PID u32 --min E*1000-1000-X --max E*1000+1000-X --continue --adb --state %TEMP%/spectre-hunt/hero_exp.json
spectre dump $PID <start> <size> --adb --format raw --output %TEMP%/spectre-hunt/hl_1.dump
spectre dumpdiff %TEMP%/spectre-hunt/hl_0.dump %TEMP%/spectre-hunt/hl_1.dump --base <start> --json   # Slot L -> L+1
# 60 s idle, nochmal --continue
```
Hat ein erster Range-Durchgang > ~10k Kandidaten → abbrechen und ebenfalls per Dump-Diff suchen.
Null Überlebende in allen drei Gold-Typen → Gold endgültig server-side oder verschleiert, dann bleibt
OCR. Für Level-Überlebende `dump $PID <addr-64> 192 --adb` machen und nach hero_id/Sternen suchen.
Andere Helden (85/100/110) mit festem Stride = Helden-Array gefunden (dann `spectre chain`).

**H4 — AFK-Stage (Progress-Push).** Dump-Diff (Stage ist ein kleiner Wert): Dump vor dem Kampf,
Dump nach einem Sieg, `dumpdiff` → Slot N→N+1. Nach einer Niederlage bleibt der Wert gleich
(zusätzlicher Filter).

**H5 — Diamanten / Gilden-Tokens (nächster Reward-Claim).** Exakten Wert V bzw. T ablesen,
`search u32 V` (`dia.json`, `dia64.json` als i64) bzw. `search u32 T` (`gtok.json`). Nach einem Claim mit
angezeigter Menge D: `--continue V+D` (bzw. T+gain), dann 60 s idle und nochmal. **Diamanten nie
ausgeben** – nur Gutschriften als Differential verwenden.

**H6 — Stamina (Küche).** Dump-Diff: nach einem Make (unter Max) S ablesen und dumpen, dann ein
weiterer Make oder ein Regen-Tick, dumpen, `dumpdiff` → Slot S→S'. Ist u32 leer, f32 versuchen.

**H7 — Timer als End-Epoch.** Countdown D Sekunden bei Unixzeit now, also E = now + D:
```
spectre search $PID u32 --min E-5 --max E+5 --adb --state %TEMP%/spectre-hunt/gchest_s.json
spectre search $PID u64 --min (E-5)*1000 --max (E+5)*1000 --adb --state %TEMP%/spectre-hunt/gchest_ms.json
# 60 s warten, --continue mit DEMSELBEN Bereich (End-Epoch bleibt konstant)
```

**H8 — Letzter AFK-Claim als ms-Epoch (niedrige Prio, von T23 nicht abgedeckt).** Direkt nach einem
Claim zur Zeit t: `search u64 --min (t-5)*1000 --max (t+5)*1000` (`afk_claim_ms.json`) plus u32
Sekunden (`claim_s.json`). Beim nächsten Claim t2 `--continue` mit dem t2-Fenster.

**H9 — player_id-Anker.** `spectre hot $PID f7909403 --adb --base $BASE --json` (voller Heap, bei
Idle laufen lassen). „SiLeet“ direkt per `spectre hot $PID 53694c656574 --adb --json` (UTF-8) bzw.
`spectre hot $PID 530069004c00650065007400 --adb --json` (UTF-16LE) suchen, oder für jeden Treffer
`spectre dump $PID <hit-128> 512 --adb --format raw --output <datei>` und die Bytes offline durchsuchen
(`spectre find` sucht Prozesse nach Namen, nicht Speicher). Abstände zu den Treffern aus H1/H5 vergleichen.

**Überspringen:** HP, Gegner-Power (transient, keine Entscheidung). Dura erst nach dem Unlock.

**Raw-Check team_power (kein Hunt nötig):** `python scripts/afk_memory.py --show --pid $PID --base $BASE`
→ erwartet `team_power: ok ~258K`. Nach einem Neustart muss die Relokation `ok` melden und der
HUD-Wert (Resonating Hall „Power 2xxK“) übereinstimmen.

## Was im Branch ist

| Datei | Änderung |
|---|---|
| `spectre-game/src/offsets.rs` | `YamlFieldDef.min` / `max` (`Option<f64>`, serde default) |
| `spectre-game/src/validate.rs` | `range_error`: min > max, NaN, Range auf Nicht-Zahlen-Typ → Fehler |
| `spectre-cli/src/read_batch.rs` | Range-Check in `read_all` (Wert bleibt, `valid: false`, Note angehängt; NaN/Inf bei gesetzter Range = außerhalb). 3 neue Tests (Grenzen inklusiv, kaputte Ranges, gebündelte offsets.yaml) |
| `games/afk-journey/offsets.yaml` | team_power `min`/`max`, Header + STALE-/Nicht-Offset-Markierungen |
| `games/afk-journey/README.md` | falsche „Verified“-Tabelle und gold-spend-Text ersetzt |
| `docs/cli-reference.md` | Abschnitt `read-batch` + Range-Zeile in der Validierungstabelle |

Python: keine Änderung (kein weiterer verifizierter Offset → keine OCR-Umstellung möglich).

## Offen / nicht geprüft

- Kein Live-Lauf (Regel). Alle HUNT-Einträge sind unbewiesen.
- `examples/afk-offsets-live.yaml` (team_power I64 @0xA578, afk_pool_*) ist ebenfalls STALE und hier
  nicht angefasst (genutzt nur von `examples/bot-config-afk-live.yaml`, kein Python-Skript).
- Die Range in `afk_memory.slot_yaml` ist bewusst **nicht** gesetzt. Die Relokation liest dort auch
  Kandidaten-Offsets, und der Drift-Guard in `memory_preflight` bleibt die einzige Prüfung (T78).
