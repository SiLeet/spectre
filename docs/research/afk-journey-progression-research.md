# AFK Journey — progression meta research (compiled 2026-11-01, live patch 1.8.2 / Season 8)

Scope: current-patch player meta for an account at **AFK Stage ~254, Chapter ~20** — i.e. early game by 2026 standards. The permanent ladder is **1125 stages** long, after which Infinite Stages + seasonal content open. A casual account reaches RL 240 and stage 1125 in ~70–80 days (Prydwen).
Do not apply endgame advice (Infinite Stages, Resonance Synergy, seasonal Phantimals/Charms) to this account yet — none of it is reachable at stage 254.

---

## 1. Resonance mechanics (the single most important system)

Rules, agreed across Prydwen, LootBar, Fandom and an instrumented account (Agentic-Search repo):

| Rule | Detail |
|---|---|
| Hands of Resonance | Exactly 5 hero slots |
| Resonance Level (RL) | Set by the **lowest** Hand; every other hero on the account is auto-levelled to RL for free |
| Level gap | No Hand may sit more than **+10** above RL |
| Swap cost | **Free, unlimited, any time**; the incoming hero inherits the slot's level, the outgoing hero drops to RL |
| Only Hands are levelled | Non-Hands cannot be levelled at all |
| Pre-Synergy cap | RL **240** |

Implications that actually drive decisions:

- **Level all five Hands evenly.** Levels invested in any Hand other than the lowest buy *only that hero's headroom* — nothing for the account. The correct loop is: raise the lowest Hand until it is no longer the lowest, repeat. Never leave a Hand +10 above the rest.
- **Because swap is free and level travels with the slot, the five Hands should be the five heroes you are actually fielding.** Re-pick them for each push mode (stage comp, Dream Realm comp, arena comp) instead of levelling "whoever was first".
  - Note: LootBar/afk.global claim a swapped-in hero enters at RL, not at the slot level. An instrumented account contradicts them — verify in-game once before automating on this; either way, even distribution is correct.
- **Pre-240 the cost is Gold + Hero EXP + Hero Essence together.** Post-240 the RL stops and **Resonance Synergy** takes over: Essence *only*, +5 cap per Supreme+ hero owned, base cap 300, only the first 60 levels (→300) pay combat stats, higher levels pay Diamonds. So: **do not pre-farm "essence for 240+" by starving levels now** — gold is the early bind, essence becomes the bind later.
- Training Manuals become dead weight after 240 and convert to Hero Essence at **3000:1** (a real later-stage sink, irrelevant at stage 254).
- Ascension tiers gate skills, and this matters more than levels in some modes: **Legendary+ → Hero Focus**, **Mythic+ → Exclusive Equipment (a new skill)**, **Supreme+ → Enhance Force**. A hero below its breakpoint is a different, weaker hero.

## 2. Resource priorities (what the bot should spend / not spend)

**Binding constraint at stage 254: Gold.** Everything about levelling, class gear and shop buys competes for it. Layered constraints by phase:

1. **AFK Stage first, every session.** Stage determines the passive rate of Gold/EXP/Essence and every "instant reward"/hourglass payout. Push stages *before* spending resources or doing side modes; then spend the new income; then push again.
2. **Gold → Hands of Resonance levels** (evenly), then **class equipment** upgrades. Don't drain gold on shop refreshes/cosmetics.
3. **Hero Essence** — spend normally pre-240; hold a buffer because it is the only currency that buys post-240 power.
4. **Diamonds** — spend order:
   - Guild Store discounted Invite Letter, **210 diamonds/day** (best rate in the game; a 10-pull is 270/draw).
   - Save toward ~30k for a wanted rate-up (pity 40 = 10,800 hard guarantee).
   - Rest → All-Hero 10-pulls.
   - **Never** buy gold, EXP or standard equipment with diamonds; never single-pull (300 vs 270/pull; always pull in tens — 10-pull always contains ≥1 A-level).
   - Arena tickets only when a rank-up is in reach.
5. **Class equipment is per CLASS, not per hero** (6 sets). Six slots per class; the displayed class level is the **mean of the six slots (rounded down)**, so spreading stones moves the headline faster than spiking one slot. Upgrade 2–3 slots per class, in this order: Warrior/Rogue → Weapon; Tank → Armor+Gloves; Mage → Gloves+Ring; Marksman/Support → Boots. Start with the carry's class (Mage, then Tank, then Support).
6. **Never burn Temporal / Twilight Essence** (EX weapon mats above +10) on a whim — near-unbuyable for F2P and income dries up.

## 3. Hero priorities for stage ~250+, chapter ~20

The stage ladder at this level is beaten by an early-game carry + sustain, not by the current SS-tier (Rolan, Senea, Taichi & Agumon, Contess, Saida, Gunnar — those are late/PvP units and mostly Celestial/Hypogean, i.e. not pullable from All-Hero).

Practical picks for this stage band (Prydwen early/mid + afk.global current aggregate):

- **Carry: Cecia (S+ early)** — best early DPS almost every account has; manual her ultimate onto the enemy backline. Shemira is the other recommended all-mode carry if owned. Bryon also rates S early→late.
- **Support/sustain: Smokey & Meerky** (Dream Realm + stage staple, works unduped), **Rowan** (team energy), **Koko** (Mauler core), **Elijah & Lailah** if owned (universal energy/haste).
- **Tank: Thoran / Brutus** (Brutus stalls ~seconds even at 1 copy), **Antandra** (S mid-game tank).
- **Utility/DPS flex: Odie** (execute ultimate, all modes), **Bonnie**, **Lily May**, **Silvina** (Graveborn — melts Lightbearer backliners like Rowan), **Alsa/Shakir/Sinbad** as owned.
- **Wishlist** (unlocks at 30 pulls): 2 S-level + 2 A-level per faction — set it to the plan above rather than leaving it default.
- A-level heroes are fully viable: they ascend to max tier and level identically; several are best-in-mode. Don't ignore them.

## 4. Faction & formation (cheap, immediate power)

- Faction bonus activates with **>2 of one faction**: **+10% ATK/HP at 3, +18% at 4, +22% at 5**. Mono-faction is not worth it; the standard shape is a **3-hero faction core + 2 flex**.
- **Celestial/Hypogean count as any faction** — they fill slots 4/5 without breaking the 3-core bonus.
- **Counter wheel: +15% damage dealt / −15% taken** vs the countered faction. When bonus and counter conflict, **counter wins** (15 > 10). Pick the core from the faction that counters the enemy.
- Strong heroes beat the bonus: a hero 2 ascension tiers higher, or one with an EX weapon, is worth dropping the bonus for.
- Default role shape: 1 Tank, 1 Support(heal), 1 carry, 2 flex. Carry chosen *before* the core.
- **Range decides the row, not the class label** (range 1 = melee walks in; 6+ = safe backline).
- **Low walls block movement but not ranged attacks**; high walls block both. A melee carry losing a fight it should win is usually a low-wall explanation. Barrels/spikes can be clicked — use stage traps deliberately.
- Split aggro with two tanks on the flanks when the tank dies too fast.
- **Per-stage "Records" (ⓘ icon next to Battle → Records)** shows lowest-power clears, per-hero damage and replays. This is the highest-value, least-used tool: it turns a wall into a copyable formation.
- Auto-play is a real handicap: manual ult timing (Cecia onto backline, etc.) clears stages auto cannot.

## 5. AFK income optimisation

- AFK chest caps at **12h early, 24h later** — never let it overcap; collect at least twice a day.
- **Hourglasses / Instant Rewards / Quick AFK**: hold until stuck or end of day, because payout scales with current stage. (Diamonds for Quick AFK only when deep enough for rare drops — not at stage 254.)
- Do **Arena and Dream Realm at the end of the day**, after all power gains, not on login.
- **Dream Realm** = best source of A-level dupes → ascension → skills. 5 attempts/day (→10 via Mystic Collection), **no restart once entered**, so only enter when ready; same comp has roll variance, so re-running a good setup can improve the score.
- **Legend Trial** gaps between factions are capped at 20 stages, and all four towers open **Sunday** — that is catch-up day.
- Join a guild immediately (guild quests/medals → Celestial/Hypogean heroes; guild chest).
- Affinity: spread gifts/plants across heroes; **1300 total affinity → 100 diamonds + 1 Invite Letter**.
- Redeem promo codes (a current one gives 3,000 diamonds).

## 6. Arena tactics (bot-relevant, and counterintuitive)

- Arena **normalises hero level to a baseline (151, +~10% if above, so ~166 max) and adjusts hero gear to match**. Unlocked skills are *not* touched.
  → Levels, class gear and total power are **worth nearly nothing in Arena**. What pays: **ascension tier (skills), faction bonus, counter wheel, kit, formation, map**.
- **Defender wins on timeout** — a defence only needs to survive. Attacker must kill all five.
- The **defender saves the map**; attackers fight on it. On defence pick a map that punishes melee carries (low walls) — on attack read the map before locking formation.
- **3 random opponents, free refresh ×5/day** — scout the visible defence formation and pick targets rather than accepting the first offer: 18 defences seen for 5 attacks.
- 5 free tickets/day + 5 buyable; spend all free ones. Early on, attack only clearly lower-power teams for reliable wins; rank-ups pay one-time rewards and raise daily Mystic Collection income.

## 7. "Quick wins" leaders repeat

1. Push AFK stages, then re-spend, then push again (loop, not a one-shot).
2. Copy the lowest-power formation from a stage's Records, then adjust placement one variable at a time.
3. Manual ultimates instead of auto.
4. Two tanks flanking to split aggro; reposition rather than rebuild.
5. Set the Wishlist; pull only in tens; buy the 210-diamond daily letter.
6. Even out the five Hands — never one hero +10 ahead.
7. Spend gold on class gear for the carry's class before maxing hero levels far past the stage requirement.
8. Do arena/Dream Realm late in the day; spend every free attempt.
9. Guild + Sunday Legend Trial + affinity 1300 + promo codes.

---

## 8. What this implies for Spectre (bot feature levers, ordered by expected value)

1. **Auto-leveller: raise the lowest Hand only, keep all five within 0–1 levels.** Needs a read of the five Hand levels + Gold/Hero Essence. This is the account-wide power multiplier; a bot that levels "some hero" or leaves a gap is leaking progress.
2. **Swap Hands to the comp being pushed** before each run (stage comp vs Dream Realm comp vs arena comp) — free, and only Hands get the +10 headroom.
3. **Stage-push loop**: attempt → on fail, read Records (lowest power clear) → swap formation/faction counter → retry with a bounded retry budget → then report "stuck, needs X".
4. **Class-equipment upgrader**: pick the carry class, upgrade 2–3 slots to the next tier break, spread stones across slots (mean-level display).
5. **Arena target selection**: filter offered opponents by power/ascension tier, scout formation, set a melee-punishing defence map, spend all 5 free tickets late in the day.
6. **Income hygiene**: collect AFK chest ≥2×/day before cap, hold hourglasses until stuck, run Dream Realm at end of day.

## Source quality / caveats

- Solid, multi-source: resonance rules, faction bonus values (+10/+18/+22), counter ±15%, class-gear mechanics, diamond spend order, AFK-stage-first economy — Prydwen guides (beginner, tips & tricks, AFK progression teams), LootBar Resonating Hall guide, Fandom wiki.
- Single-source / `unverified` in origin: Arena baseline 151 (+10%), 90s battle timer, exact stage count 1125 as the story ceiling, "level travels with the swapped slot" (one instrumented account contradicts two guides), Instant-Reward diamond prices.
- Reddit was 403-blocked during this research (r/AFKJourney threads on deficit pushing and "why do similar-power players clear higher stages" could only be read as search snippets: the consistent claim is **power rating is inflated by roster size and is not a strength measure — formation, counter and kit decide deficits**).
- Full extracted source text saved at `C:\Users\Sigi\AppData\Local\hermes\cache\scratch\afkj\*.md`; the Agentic-Search repo (github.com/MalcolmMcNeely/Agentic-Search, mechanics/ + account/) is an unusually well-instrumented AFK Journey knowledge base and the best single reference found.
