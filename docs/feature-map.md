# Spectre Feature-Map (guide-getrieben, Stand 2026-11-05)

Regel (User-Direktive): Features EINZELN nehmen -> vollstaendig bauen -> live testen
-> abhaken -> naechstes. Kein Parallel-Flickwerk.

Legende: [DONE]=im Auto-Run live · [PARTIAL]=Skript/Soft vorhanden, unvollstaendig · [OPEN]=fehlt

## P1 — Core-Loop & Ertrag (hoechster Impact)
- [DONE] AFK-Stage-Push (afk_stage_push im Watch; Kerngrind: DUST fuer Hero-Level)
- [DONE] Idle/Claim-Routinen (claim_vision-Phasen)
- [PARTIAL] Tower-Pushing (Spire-Upgrade-Kette da; aktives Stage-Pushing am Turm fehlt)
- [OPEN] Guild: beitreten (Server-Invite gesehen!) + Guild-Quests + Clashfronts + Guild-Store (210-Dia-Ticket taegl.)
- [PARTIAL] Supreme Arena (arena.py erweitern: 3 Tickets)
- [OPEN] Taegliche Shop-Buys (DR-Store Essence, Invite-Letter) + taegliche Summon (Wishlist-Banner)
- [DONE] Arena, Dream Realm 7/7, Daily Quests, Hero-Leveling (Hall)

## P2 — Modi & Breite
- [OPEN] Honor Duel (15 Wins/Runde)
- [OPEN] Battle Drills (weekly-ish, meh-Rewards)
- [OPEN] Arcane Labyrinth (min. 1 Battle/Tag)
- [PARTIAL] Einhorn-Events: Event-Erkennung (Banner) + Minimal-Participation (saisonal!)
- [OPEN] Map-Exploration-Bot: Chests/Puzzles (Dias, wertvoll; wave-weise)
- [OPEN] Corrupt Creatures (Map-Battles, gutes Gear)
- [OPEN] Equipment: craften/upgraden (main 5)

## P3 — Rest
- [PARTIAL] Dura's Trials (Skript, wartet auf Karte auf H143)
- [OPEN] Legend Trials (purple dust)
- [OPEN] Fishing, Dekorationen (quest-bedingt)

## Homestead (komplett, laeuft)
- [DONE] Felder 16/16 build-autonom | [PARTIAL] Build-all (T105) & Upgrade-all+Refinery (T105)
- [DONE] Kitchen/Spire-Kette | [PARTIAL] Cook+Requests+Gazette-Kreis (T104)

## Meta / System
- [DONE] Input-Healing (keyevent-Fallback-Kette), Memory-Reads, wall-dash, gold-hunt, Speed-Profil
- [PARTIAL] Frida/timeScale (braucht Root) ; [DONE] Watcher/Auto-Merge/Soak/Night-Tasks

## Arbeitsweise (Pipeline je Feature)
1) Recon live (Frames+OCR/Pixel-Scan, Werte nur verifiziert) -> 2) Mini-Brief an Claude-Session
"spectre" (ein Feature, abgeschlossen = DoD: FakeVision-Tests+Suite, Branch, 1 Commit, kein push)
-> 3) Hermes: Merge + Fresh-Eyes-Review -> 4) LIVE-Test am Geraet -> gruen = abhaken; rot = Fix-Brief
-> 5) erst dann naechstes Feature.
