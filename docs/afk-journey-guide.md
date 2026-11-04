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

## Free-economy edges (bot/manual notes, T45k + T45l)

From `docs/research/mechanics-gaps.md` §5–6 — operational notes, no gem/real-money actions:

### Temporal Essence Swap (T45l)
- On the EX upgrade page there is a **Temp Essence Swap** button: hero-specific
  temporal essence ⇄ universal essence, limited by how much universal essence is
  actually built into that hero; **unlimited for heroes at +15**.
- Consequence for any reward/shop pick: **hero-specific essence is never a dead
  pick** — take it, then swap it to universal. Excess specific shards on a +15
  hero are pure universal essence.
- Direction of the swap is lossy-neutral only one way: you can only "take back"
  universal essence by putting a specific bottle back into the same hero. Bot
  rule (manual step for now): never dump specific essence before checking the
  swap direction; swap-to-universal is the default sink for Lucky-Flip picks.

### Supreme Arena settlement slot (T45k)
- Calculation time is **player-selectable, 12:00–24:00 UTC**, takes effect
  *next day*, settles inside a **10-minute window**; in the last 30 minutes only
  re-challenges of the *same* opponent are allowed, with a **15-minute lockout**.
- Off-peak recipe: slot when your district sleeps → rank snapshot before the
  crowd pushes. Season start: set 24:00 UTC (full day to climb), switch to an
  off-peak slot once the level stabilises.
- Final-30-minute play needs **two prepared snipe targets** (15-min same-target
  lockout). 3 free Glory Badges/day (up to 12 more with diamonds — policy:
  never automated); off-season Mon/Tue: no rewards, but still set formation.
- Bot relevance: this is a **scheduler-slot problem**, not a UI problem — the
  only action is "set the slot once". Late-game feature (Talent Tree applies
  here); not worth UI automation before the account reaches Supreme Arena.

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

Bot templates built on these actions (placeholder offsets marked `REPLACE`):
`examples/bot-config-afk.yaml` and the `safe_claim` mode of
`examples/afk-bot.lua`; the placeholder-to-real-offset walkthrough is step 5
of [examples/README.md](../examples/README.md).

## Bot operation (scheduler, gates, recovery)

Derived from `scripts/afk-bot-watch.sh`, `scripts/afk-night.sh`, the
`afk-bot-*.cmd/.vbs` launchers and the drivers' `argparse` flags (state
2026-11-03). Every driver classifies the screen before it taps and refuses to
tap on an unknown screen.

### The three Windows tasks

| Task | Time | Launcher chain | Runs |
|---|---|---|---|
| `Spectre AFK Night` | 02:00 | `afk-bot-night.vbs` → `afk-bot-night.cmd` → `afk-night.sh` | `afk_stage_push.py --auto --auto-minutes 135 --retry-defeats` |
| `Spectre AFK Daily` | 05:10 | `afk-bot-scheduled.vbs` → `afk-bot-scheduled.cmd` → `afk-bot-watch.sh --scheduled` | chest claim, then all once-per-day phases (below) |
| `Spectre AFK Progress` | 17:10 | `afk-bot-progress.vbs` → `afk-bot-progress.cmd` → `afk-bot-watch.sh --scheduled-progress` | chest claim + `afk_stage_push.py --auto --auto-minutes 6 --retry-defeats` |

The `.vbs` launchers start the `.cmd` hidden (window style 0) and wait for it,
so the task's result is the wrapper's exit code. Logs:
`.spectre/logs/afk-bot-<UTC date>.log`.

**Night task:** 135 minutes of Auto Battle with `--retry-defeats` — on DEFEAT
the driver taps Retry (1280,1020) and keeps pushing (the retry loop wins a wall
eventually, verified 249→252). Retry cap 200; a wall report is written on the
first defeat and every 10th retry (`.spectre/wall-report.log`, JSONL, rendered
by `scripts/afk-wall-dash.py`). 135 min from 02:00 ends before the 05:10 Daily
run. The idle gate is re-checked on every poll of the auto loop: input on the
PC aborts the run (exit 5). The wrapper captures both pipeline statuses after
`tee`: a stage-push failure (including idle skip 5) reaches Task Scheduler; if
the push succeeds, a `tee` failure is reported instead.

### Marker / idle-gate matrix

`MIN_IDLE` = `AFK_MIN_IDLE` (default 180 s) for both scheduled watch modes and
for the Night task. Markers live in `.spectre/` and hold the UTC date of the
last successful run.

| Phase | Night | Daily | Progress | Idle gate | Once-per-day marker (written when) |
|---|---|---|---|---|---|
| Chest claim `afk_claim_vision.py` | – | ✓ first | ✓ first | `--min-idle` | – (every run) |
| Journey's Gift `afk-daily-gift.py` | – | ✓ | – | `--min-idle` | `daily-gift-last.txt` (exit 0) |
| Quests + mail `afk_dailies.py` | – | ✓ | – | `--min-idle` | `dailies-last.txt` (exit 0) |
| Normalizer `afk_normalize.py` | – | ✓ before arena, dream realm, stage push | – | none | – |
| Arena `afk_arena.py --fights 1` ×4 | – | ✓ | – | `--min-idle` | `arena-last.txt` (attempt 1 exit 0) |
| Dream Realm `afk_dream_realm.py --fights 7` | – | ✓ | – | `--min-idle` | `dream-last.txt` (exit 0) |
| Dura's Trials `afk_duras.py` (T84, `AFK_DURAS=0` = off) | – | ✓ before stage push (soft) | – | `--min-idle` | `duras-last.txt` (exit 0 or 4) |
| Stage push `afk_stage_push.py --auto` | 135 min | 6 min | 6 min | Night/Daily: `--min-idle`; Progress: none | Daily: `stage-last.txt` (exit 0); Night/Progress: none |

Daily and Progress only continue past the chest claim when it exits 0 (claim
verified) or 4 (nothing claimable yet). The arena loop stops at the first
attempt that does not exit 0.

### Phase normalizer (`afk_normalize.py`)

Runs between the Daily phases so a phase that ends on an unknown screen (live
case: a camera pan tapped into the Arcane Labyrinth card) cannot poison the
next one. Up to 4 steps: classify → WORLD/PANEL ends the run (exit 0); a POPUP
the login-popup resolver recognises is claimed; anything else gets one BACK
(474,1010). A final classify decides exit 0/1. The wrapper captures the result,
reports a failed normalization as a nonzero Daily task result, and aborts the
remaining gameplay phases rather than starting them on an unknown screen. Other
Daily phase failures also reach Task Scheduler; exit 3 from the Journey's Gift
driver remains a warning-only result because the missing entry can mean it was
already claimed or the event ended.

### Login-popup resolver (`afk_claim_vision.resolve_startup_popup`)

A fresh game login opens the Esperia Monthly / Daily Rewards popup, which
blocks every flow. The resolver OCRs the frame (WinRT, `templates/ocr.ps1`)
and only acts on a text hit (`monthly`, `gazette` or `daily rewards`): it taps
Claim (960,930) — the rewards are free — and closes a follow-up card with one
BACK. Without an OCR hit it does nothing and the caller falls back to its own
handling (BACK in the claim driver and the normalizer, abort in stage push).
Used by `afk_claim_vision.py`, `afk_stage_push.py` and `afk_normalize.py`.

### Lock keeper and stale policy

`afk-bot-watch.sh` and `afk-night.sh` share `.spectre/afk-bot.lock`, so two
runs never tap at the same time:

- lock present and younger than `AFK_LOCK_STALE` (default 3600 s) → the new
  run exits 6 ("another run in progress");
- older → treated as stale (crashed run), removed, the new run takes it;
- while a run is alive a background keeper `touch`es the lock every 240 s, so
  long runs (135-min Night, a full Daily round > 30 min) never look stale;
- an `EXIT` trap stops the keeper and removes the lock.

Other wrapper exits: 2 game process not found, 3 heap-base resolution
failed, 7 no Python with PIL (the wrappers refuse the blind CLI fallback).

## Sources

- Prydwen beginner guide + tips/tricks + homestead guide
- afk-journey.fandom.com (Guild, Homestead, Gate of Avalon, Golden Supplier,
  Dreamdelve, Events)
- gacha.gg/afk-journey/progression (ascension tiers, EX costs, season caps)
- gamerant.com/afk-journey/how-get-gold-diamonds
- bluestacks.com AFK Journey beginner guide