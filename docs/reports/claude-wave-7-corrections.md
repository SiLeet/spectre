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
