# Claude Wave-7 (T86–T100) — Korrekturen an den Diagnosen + Stand (2026-11-04)

Für Hermes. Alle Fixes T86–T100 sind in `main` (`88843a0`). Meine Rückmeldungen per Nachricht
kamen nie an (ENOINBOX — deine Sessions waren beim Antworten schon zu); deshalb hier gesammelt.
Offline erarbeitet, `.spectre` nur read-only gelesen, kein push.

**Kurz:** Bei T89, T90, T91, T98, T99 und T100 stimmte die Ursache im Brief nicht. Die Fixes in
`main` beheben die *tatsächliche* Ursache (Belege unten). Bitte die betroffenen Notizen/TODOs nicht
auf die Brief-Diagnose stützen.

## Korrekturen (Brief-Diagnose → Befund)

| Task | Brief sagte | Tatsächlich (Beleg) |
|---|---|---|
| T89 | Welt-Tell über den Chip (60,1036), Vorschlag `chip > 100` | Chip liegt auf dem Avatar-Sprite: roter Umhang (`livecheck/after_norm`, eine Welt) → L 77, Gildenhalle (`livecheck/hall_test2`) → L 133. `chip > 100` hätte den Bug zurückgebracht. Fix nutzt den türkisen AFK-Progress-Balken `AFK_BAR` (40,1068), `min(G,B) - R > 80`: 106–119 auf allen 57 Welt-Frames, ≤ 36 auf jedem Nicht-Welt-Frame. Die Merge-Message von `ff891db` („Chip") ist falsch. |
| T90 | Panel verfehlt wegen `lbar` (960,602) | `is_afk_panel` liest `lbar` gar nicht. Im 12:21-Frame (`shots-58212/r1_1_panel`, md5-gleich mit deinem `after_afk_panel_frame`) fehlen Badge **und** Battle-Leiste (Panel animiert noch ein). Fix: zweites Tell-Set (Kapitel-Emblem (513,348) + weißes Band y = 300). |
| T91 | Dream-Prep: Battle-Tap falsch | Auf dem Prep wurde nie getippt. Die Boss-Seite wurde als Prep gelesen (Mittelprobe (960,1040) auf dem dunklen „Chances"-Label), der echte Prep als gar nichts. `dr_f1_after0_0..9` zeigen alle noch Prep: kein Kampf gestartet, kein Marker verpasst. |
| T98 | „Battle Modes / main menu did not open" 16:39–16:48 = tote Taps | Keine toten Taps: Menü ging auf, der Bot hat falsch gelesen. `is_battle_modes` kannte nur HUD-Layout B; Wolke auf (960,602) → Welt als POPUP → `open_menu` tippte 5× BACK statt MENU. HUD hat zwei Layouts (A: Raute + Hamburger; B: Leiste ~100 px rechts, ohne Hamburger, wechselt mitten in einer Session). (890,1060) trifft in beiden. |
| T97b | Tote Taps durch unseren adb-Aufruf | adb-Audit: überall dieselbe SDK-`adb.exe` + `127.0.0.1:5555`, argv am Gerät identisch. Unser Aufruf erklärt tote Taps nicht; Ursache geräte-/spielseitig. Fallback-Kette tap → touchscreen → sendevent ist drin (sendevent live ungeprüft). |
| T99 (Quests) | 11-04 „quest panel did not open" = toter Icon-Tap | Detektor-Fehlschlag: Panel war offen, Titelprobe (500,90) las L 140 (großes Layout / gescrollte Liste). Fix: Tab-Leisten-Probe (650,1040) + Hub-Veto. Alte Regel hatte 48 Fehltreffer, neue 34 Treffer = alles echte Quest-Panels. |
| T99 (Hub-Karten) | Dream (1085,300), Arena (1310,300) | Karten liegen bei Dream ~(960,290), Arena ~(1155,290). `DREAM_CARD` / `ARENA_CARD` stimmen schon; deine Punkte wären daneben. Nicht übernommen. |
| T100 (alle drei Soft-Fails) | Dream „already inside" = Stage-Liste; Hall öffnet nicht; Arena-Lobby öffnet nicht | Gemeinsame Ursache, gefährlicher: die **alte PANEL-Regel** (Back auf Creme) traf auch Hauptmenü (`shots-70368/norm_0`), breite Arena-Lobby (inkl. „Continue"-Variante), Mail, Hero-Hall, Preps und die alte BATTLE-ENDED-Karte. normalize hielt dort mit „PANEL" an, jede Folgephase startete am falschen Ort; `claim_round` hätte auf dem Hauptmenü CHEST/CLAIM blind getippt. Im Einzelnen: (1) „Stage-Liste" war die liegengebliebene Arena-Lobby — Fight 1 tippte deren Challenge-Balken → Gegnerauswahl → 7/7 Chancen verfallen. (2) Hall-Phase startete in der Arena; `HALL_BTN` (990,1010) traf den Continue-Balken. (3) Die Lobby war offen (breites Layout), die Checks kannten nur das gezoomte T92/T95-Layout. |

## Was in `main` ist (Commit je Task)

| Task | Commit | Kern |
|---|---|---|
| T86 | `79e0935` | Intro-Screen: `intro_hint` = „esperia" **und** Gruß; bei UNKNOWN genau 1× BACK. `classify_battle` PREP braucht `g > r + 20`. |
| T87 | `7f15efe` | Dura's: Swipe-Suche in `MENU_BOX`, rc 4 wenn nicht verfügbar; kein Kartentap nach Swipe. |
| T88 | `4f059cd` | `is_afk_panel` (heller Back + Creme + grüne Battle-Leiste + Badge). |
| T89 | `673a9aa` | Welt-Tell `AFK_BAR` statt Chip. |
| T90 | `f4e0989` | Zweites Panel-Tell-Set (Emblem + Band). |
| T91 | `045853a` | Neuer Zustand DR_PREP, `BOSS_BAR_LEFT`, normalize-BACK `DR_PREP_BACK`. |
| T92 | `2d9e9be` | `afk_arena.is_lobby` (Leiste + Plakette + Navy-Band). Alte Prüfung: 34 Treffer, alles Fehltreffer. |
| T93 | `ca9b1e5` | Victory-Rewards-Overlay: `CARD_CLOSE` max. 2×, nicht mehr „Kampf läuft". |
| T94 | `04364ca` | `recover_leftover` mit `RECOVER_BUDGET = 3`, Zustand DR_BOSS. |
| T95 | `539324c` + `9f61569` | Arena-Select: Schwert-Button, Detailansicht → `DETAIL_CHALLENGE` (1050,1000), Exit/normalize je 1 Tap pro Screen. |
| T96 | `06b6feb` | Arena-Reste in `recover_leftover`, 1 gezählter Tap pro Screen-Art. |
| T97 | `95cebe5` | `back()` = keyevent 4 auf erkannten Nicht-Welt-Screens; Hold-Tap/Stall-Fallbacks. |
| T97b | `a65cd83` (Merge `073bb85`) | `TAP_MODE`-Kette tap → touchscreen → sendevent, sticky nur bei Fortschritt (`AFK_TAP_MODE` erzwingbar). |
| T98 | `19de870` | `BATTLE_MODES_BTN` (890,1060) zentral; `BM_TABS` für Layout A + B. |
| T99 | `1e9100f` | Wolken-POPUP nur ohne helle AFK-Leiste; `is_quests_panel` neu; Hub → BACK. |
| T100 | `e8da780` | Alte PANEL-Regel verlangt zusätzlich `afk_battle_bar`; breite Layouts für lobby/select/detail; Dream `run()` verlangt DR_BOSS/DR_PREP; `is_battle_ended` Bannerprobe (1400,60). |

Belege T100: über alle 1377 Vollbild-Frames (inkl. trash) bleiben 57 PANEL — alle echte AFK-Rewards-
Panels, per Kontaktbogen einzeln geprüft. Suite auf dem T100-Branch: `Ran 548 tests … OK (skipped=195)`.

## LIVE offen (nur offline belegt)

- `SWORD_LEFT_W` (Schwert auf dem breiten Select) — nie live getippt.
- `HALL_BTN` auf HUD-Layout B — keine Frames.
- sendevent-Pfad der Tap-Kette (T97b).
- `CARD_CLOSE` auf dem Victory-Overlay (T93).
- T99-Schwelle `tell <= 95`: Wolkenwelt 106–115, echte Popups ≤ 42, Battle-Modes-Fade-in 87 — knapp.
- T88/T90-Badge-Probe hängt am englischen Titel; andere Sprache → sicher UNKNOWN.
- Ein als Nicht-Welt verlesener Welt-Screen bekommt BACK → Exit-Dialog; der nächste BACK schließt ihn, Schleife begrenzt.
- Nebenbefund T90: CHEST-Tap (975,760) öffnete auf `shots-42328/r1_3_chest` kein Popup; die Truhe sitzt im neuen Layout eher um (1060,740). Deine CHEST-Kalibrierung.

Worktrees `C:\Users\Sigi\spectre-w7-T86` … `-T100` stehen noch (alles gemergt; können weg).

## Nachtrag T101–T103b (Abend 2026-11-04)

Auch diese Rückmeldungen kamen nicht an (ENOINBOX). Stand der Branches (je 1 Commit, kein push):

| Task | Branch @ Commit | In `main`? | Kern |
|---|---|---|---|
| T101 | `feature/T101-hall-direct` @ `c22766a` | ja (`66086ce`) | Hall-Einstieg nur von verifizierter Welt; Hand-Level = große „Level NNN"-Box; Charge = 1 Tap; Kostenzeile per OCR-Vote |
| T101b | `feature/T101b-level-preview` @ `2e371ab` | **nein — bitte mergen** | Meilenstein-Vorschau „Upgrade 100 » 101" wird einmal bestätigt; COST_BOX ab x 840; Scan pollt |
| T102 | `feature/T102-homestead-build` @ `c186e37` | ja (`c84dec7`) | Homestead Phase 1: Fields bauen |
| T102b | `feature/T102b-homestead-counter` @ `734228b` | ja (`9bee2dd`) | Zähler per 7-Varianten-Vote; Menü-Exit nie per BACK |
| T102c | `feature/T102c-radial-anywhere` @ `dc4a8b5` | **nein — bitte mergen** | Platzierungs-Radial im ganzen Band gesucht (folgt dem Ghost) |
| T103 | `feature/T103-homestead-upgrades` @ `cd22c0f` | ja (`1d56598`) | Spire-Upgrade-Dialog; „Complete Now" wird nie getippt |
| T103b | `feature/T103b-spire-select` @ `412f8fa` | **nein — bitte mergen** | Spire über sein schwebendes Upgrade-Icon wählen; offener Dialog beim Start ok |

### Korrekturen zu deinen T101–T103-Diagnosen

| Punkt | Brief sagte | Tatsächlich (Beleg) |
|---|---|---|
| T101 (1) | Hall-Tap (990,1010) liegt auf totem Punkt | Beide 20:30-Direktläufe starteten auf dem offenen Radiant-Spire-Upgrade-Panel (shots-62772/80500, classify UNKNOWN). (990,1010) liegt dort im „Complete Now"-Button (1800 Diamanten). Fix: Tap nur auf verifizierter Welt, sonst erst zurück zur Welt. |
| T101 (2) | Gold knapp unter Bedarf, „heute korrekt geskippt" | Falsch. `8572K/9390` = 8,57 M Gold gegen 9.390 Bedarf. Die alte Regel „Bedarf erbt das K" las 9,39 M → falscher Skip um 18:22Z. |
| T101 (3) | „charge had no effect" | Die Ladung wirkte doppelt und auf die falsche Hand: shots-17092 101→103, shots-48104 103→105 (Gold 8572K→8553K = 9390 + 9450). Das „Lvl. NN"-Badge ist nicht das Hand-Level (Badges 82/92/85 bleiben bei jeder Ladung gleich); Cecia/Aurora (100) wurden nie geladen. |
| T101-Nachtrag | LEVEL_X1 trifft nach Redesign ins Leere; echte Trigger = grüne Doppelpfeile im Hall | Widerlegt: LEVEL_X1 levelte live (101→103 mit passendem Gold/EXP-Verbrauch). Die Doppelpfeile sind „levelbar"-Marker, bei (1003/1116/1229, 423), nicht ~(963,400). |
| T101-live | Level-Read nach Tap None; Kosten 8,53 M vs. Gold-Anzeige 653K inkonsistent; drittes Paar weg = Verbrauch? | Bei Level 100 öffnet der Tap eine „Upgrade 100 » 101"-Vorschau (shots-43184) → Level-Box weg. 8,53 M ist Helden-Gold, 653K ist Homestead-Gold (andere Währung). „Drittes Paar weg" = der Ausschnitt schnitt das Gold-Paar ab (Vorschau-Zeile ~100 px weiter links), kein Verbrauch. Fix in T101b. |
| T102 | „Build" (900,1017) ist ein Bauschritt; Toast kommt automatisch | „Build" ist der schon aktive Build/Layout-Umschalter; der Toast kommt erst nach dem Tap auf den „Tap to Complete"-Marker; Toast-Mitte öffnet die Diamant-Infokarte. |
| T102-live | FIELD_BOX-Crop prüfen | Weißer kursiver Zähler: kein einzelner Crop liest 12/13/14 zuverlässig → 7-Varianten-Vote (T102b). |
| T102-Radial | Radial-Lage dynamisch | Bestätigt; Geometrie fest (X 247 px links vom Haken, gleiche Höhe), nur die Position wandert → Band-Suche + Weißscheiben-Test (T102c, Sweep 1796 Frames: 7 Treffer, alle echt). |
| T103-live | Label „Radiant Spire" ~(890,185) antippen | Dort steht kein Text-Label; es ist ein schwebendes weißes Icon mit Pfeil nach oben über dem Spire (Mitte ~(916,171)). T103b sucht es pro Frame (Sweep: 4 Treffer, alle echt). |

### Diamanten-Policy (T103)

Die „Complete Now"-Regel (automatisch, wenn Diamanten ≥ 10× Kosten) ist **nicht** umgesetzt. Sie widerspricht der stehenden Regel „nie Diamanten" und braucht Sergejs Entscheidung. Das Modul lehnt jeden Tap in der „Complete Now"-Fläche ab.

### LIVE offen

- T101b: Verhalten nach der Bestätigung in der Vorschau (schließt sie oder zeigt 101 » 102?) — beides wird behandelt, ungesehen.
- T101: „tap missed" (rc 1) hat keine Obergrenze über Zyklen; nichts wird verbraucht.
- T102c/T103b: neue Detektoren live ungetippt; T103 „Go"-Wege, 7/7-Dialog, Kitchen/Kochen offen.

## Nachtrag T103c (22:28-Läufe)

`feature/T103c-homestead-camera` @ `edf23aa` (Basis `98d972b`) — **bitte mergen**. 75 Homestead-Tests OK, volle Suite `Ran 668 tests … OK (skipped=201)`.

| Punkt | Brief sagte | Tatsächlich (Beleg) | Fix |
|---|---|---|---|
| Upgrade-Phase „nothing to do" | Kamera verschoben, Icon-Scan auf x 350–1300 verbreitern | Ein Lauf (shots-9308) startete auf dem Dialog „Are you sure you want to exit the game?". Im anderen (shots-80480) war die Kitchen ausgewählt. Das Spire-Icon wäre bei ~(507,373) im Bild gewesen, war aber nicht gezeichnet (vermutlich, weil ein anderes Gebäude den Fokus hat). x-Verbreiterung hilft nicht (Scan läuft schon über x 300–1600). | Exit-Dialog → X (1014,710), nie der Haken. Kein Radial/Icon → Abwahl (GROUND), dann höchstens 2 Drags mit Neusuche; weiter nichts → rc 4. Das Kitchen-Radial gilt nie als Spire (Label muss über dem eigenen „Level Up" stehen). |
| „Tap to Complete" einsammeln | als begrenzter Schritt | Marker (760,877) lag außerhalb des alten Suchfensters | Build-Phase sammelt vor dem Menü bis 3 Marker in (250,150)–(1700,1000). Sweep 1806 Frames: 17 Treffer auf WORLD, alle echt; `MARK_PX` 2000 (Kitchen-Sprechblase ~930 px). |
| „Tap to close" per BACK | zuverlässig | übernommen | Nur als Fallback: genau ein BACK, wenn derselbe erkannte Toast nach dem Tap noch steht; nie auf Welt/Menü. |
| Ore Refinery | Upgrade-Kette vormerken | — | nur Notiz |

LIVE offen: ob Drags die Homestead-Kamera bewegen, ob nach der Abwahl das Spire-Icon erscheint, mehrere Marker hintereinander.

## Nachtrag T103d (Turm-Tap-Fallback)

`feature/T103d-spire-tower-tap` @ `0543b1d` — liegt **auf T103c** (`edf23aa`), also T103c vorher oder zusammen mergen. Homestead-Tests 83 OK, volle Suite `Ran 676 tests … OK (skipped=201)`.

- **Turm finden:** 4 goldene Lichtstrahlen an den Turmpfeilern (äußeres Paar 200–229 px, inneres 98–116 px auseinander, inneres 40–105 px tiefer, gemeinsame Achse ±7 px); 3 von 4 reichen (die Strahlen flackern); eigener Nacht-Pfad über R−B. Tap auf die Achse in halber Höhe der äußeren Strahlen = Turmkörper, 150–180 px über der Tür (shots-80480: (507,528), dein Live-Tap ~(520,450)).
- **Sweep:** 358 WORLD-Frames, 162 Treffer, alle auf dem Turmkörper (Kontaktbögen; 12 zufällige Treffer von mir nachgeprüft), 0 Fehltreffer. Verpasst nur, wenn der Turm vom Rand/HUD abgeschnitten ist.
- **Ablauf:** (a) Radial/Icon wie bisher → (b) Turm-Tap, „Interact" per OCR + Cremescheibe (tower_tap: Mitte (953,683)), ein Retry, Dialog-Prüfung „Upgrade Requirement" + „Radiant Spire" → sonst rc 1 ohne weiteren Tap. Kein Turm → T103c-Kamerasuche, auf jedem Frame Icon dann Turm.
- **(c) Label-Tap nicht umgesetzt:** Das Label „Radiant Spire" erscheint nur, wenn der Spire schon ausgewählt ist — dann greift (a). Kein Frame zeigt, was ein Label-Tap öffnet.

LIVE offen: ob der Turm-Tap den Spire wählt (und den Helden nicht laufen lässt), 2 s Wartezeit bis zur Kamerazentrierung, ob „Interact" auch ohne mögliches Upgrade den Dialog öffnet.
