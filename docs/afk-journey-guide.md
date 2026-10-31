# AFK Journey — Game Orientation (for bot/offset work)

Target game for Spectre offset discovery. This file is the *game knowledge*
reference: modes, screens, currencies and where they are earned/spent.
Compiled 2026-10-31 from Prydwen, Fandom, Gacha.gg, GameRant, BlueStacks.

## Global layout / screens (observed on BlueStacks 1920x1080)

| Screen | How to reach | Notable UI |
|---|---|---|
| Title | app start | "Tap to begin your journey" (~962,893), BlueStacks sidebar right |
| Town/Hub | after login | Gold top-left (~34-82, 90-104), event timer below (~18-110, 305-318), bottom nav: Mystical House / Battle Modes / Resonating Hall / Guild (~830/922/1004/1089, 1017), Homestead (1880,920), Login Rewards (1804,662), Quests (40,890), Story (101,878) |
| Homestead | bottom-right icon / world map preview | base-building, harvesters (mills/fields), processors, Home Cairn, Treasure Chest (AFK rewards), Dream Pavilion; Gate of Avalon building = entry to open world |
| Open World / Avalon | Gate of Avalon in Homestead (or map route) | event currency shown top-left (e.g. "996"), chat overlay, "Gate of Avalon" text, World button bottom-right (1858,931) |
| Journey's Gift | Login Rewards button (1804,662) | login reward panel, Day 1..5, daily claim (sometimes none claimable — Day N marked "Tomorrow") |
| Esperia Monthly / Classic Gazette | event popup after login | Rowans text, "Rewards Accumulated", genuine Claim button (~959,935, area 815-1104 x 895-975) |

## Core loops

1. **AFK Stages** (the priority): passive income of Gold + EXP + Essence; the
   further you push, the more you earn per hour. Idle chest caps at 12h early,
   up to 24h later. Hourglasses grant several hours of resources instantly —
   use at end of day when strongest.
2. **Main Story / Open World**: hidden chests, quests; generous one-time
   rewards but not the daily engine.
3. **Guild**: join ASAP; Guild Quests/Challenges; guild currency buys
   Celestial/Hypogean heroes. Battle Drills = guild boss event (rounds start
   00:00 UTC Tuesday; stamina needed; rewards gold + Treasure Keys ->
   Chest of Valor).
4. **Arena / PVP / Dream Realm** (guild boss): good gold/diamond income;
   do attacks at end of day when strongest.

## Currencies (value sources)

| Currency | Use | Earned from |
|---|---|---|
| **Gold** | leveling heroes, abilities | AFK stages, Arena, Dream Realm, events, stage chests, quests |
| **Diamonds** | gacha (300/pull, 2700/10-pull), shops | story, quests, arena, dream realm, codes, events |
| Invite Letters | All-Hero + Rate-Up banners | dailies, quests, events, codes |
| Temporal/Twilight Essence | Exclusive Weapon +15..+25 | rare — leaderboards, events |
| Acorns | ascension of S-level heroes | events, shops |
| Stellar Crystal | Stargaze (Celestial/Hypogean) only | Guild/Recruitment store, monthly limited |
| Season currency (Abyssal Essence etc.) | seasonal shop | battle drills / seasonal content |
| Homestead: Ancient Coins, Wish Points, Mirage Orbs, Lucky Keys | homestead upgrades/decoration | fulfilling visitor requests, daily rewards |

## Key mechanics affecting memory work

- Display strings are ROUNDED ("259K" = actual numeric value somewhere in
  259000-259999); never grep the string, scan the numeric range.
- The top-left currency label switches by screen (Town shows Gold; Open
  World/Avalon shows the event currency) — do not hard-code one address as
  "the gold display" until verified per screen.
- A visible HH:MM:SS near the top-left is a COUNTDOWN (event/daily reset),
  stored as end-epoch or seconds — good candidate for a live ticking offset.
- Claimable rewards show red-dot/notification flags (e.g. "1.4" badge on the
  Login Rewards button, red badge on the chat button) — these are likely
  bool/int fields per entry.
- Homestead has its own resource economy + aggression (Darkswarm Invasion) —
  separate value cluster.
- Battle Drills rewards convert to mail when a round ends — mail is a
  claimable-reward pool.

## Trigger actions for offset confirmation (cheap + safe)

Prefer actions that change a currency with zero risk:
- Claim Daily/Login rewards (Journey's Gift "Claim" or the Esperia Monthly
  Claim at ~959,935) — adds Gold/diamonds.
- Fulfill Homestead visitor requests (gives Wish Points/Ancient Coins).
- Take AFK idle chest (Treasure Chest in Homestead) — Gold/EXP/essence.
- Clear a Battle Drills stage (gold + keys).

Use these with `spectre dump` before/after + `spectre dumpdiff --base` to find
the exact slot that moved. Never click real-money "Purchase" buttons (bundle
popups appear on Homestead entry).

## Sources

- Prydwen beginner guide + tips/tricks + homestead guide
- afk-journey.fandom.com (Guild, Homestead, Gate of Avalon, Golden Supplier,
  Dreamdelve, Events)
- gacha.gg/afk-journey/progression (ascension tiers, EX costs, season caps)
- gamerant.com/afk-journey/how-get-gold-diamonds
- bluestacks.com AFK Journey beginner guide