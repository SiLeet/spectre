#!/usr/bin/env python3
"""Normalize the game screen back to a known state (world / AFK panel).

Used by the scheduler wrapper between phases: a phase that ends on an unknown
screen (live case: the gift driver's camera pan accidentally tapped into the
Arcane Labyrinth card) otherwise poisons every follow-up phase. Non-blind:
classify() per step, capped BACK taps, login popups get claimed when OCR'd.

Zombie popup (T66, night log 2026-11-03: "normalize 0..4: POPUP", dream then
"could not reach the world view"): when every read of the normal pass is
POPUP, a bounded escape ladder runs — login resolver -> BACK -> empty ground
(300,250) -> BACK x2 — classify after every step, a purchase/confirm dialog
is always cancelled, the ground tap is skipped when OCR shows purchase words.
It ends with one clear marker line: 'ESCAPE: recovered ...' or 'ESCAPE: gave up ...'.

Dream Realm result screens (T93: Victory Rewards overlay / BATTLE ENDED card,
both UNKNOWN) get dr.CARD_CLOSE instead of BACK (BACK on the card hits Replay),
at most DR_END_TAPS times, one extra step each; never BACK there.

T94: a Dream Realm boss page (DR_BOSS, also under its info card) or a black /
UI-less transition hands over to v.recover_leftover (the round-start helper
claim_round uses), once: v.RECOVER_BUDGET minus the T91/T93 Dream taps already
made, transitions waited out instead of BACK. It ends WORLD/PANEL -> 0; POPUP ->
normalize's own pass goes on (login resolver / escape ladder) but a Dream
leftover after it -> 1; anything else -> 1.

T95: an arena leftover (select screen / lobby UNKNOWN, detail view POPUP; the lobby with
its back arrow mid-press reads POPUP and its 'Daily Rewards' widget fooled
the login resolver into LOGIN_CLAIM on Battle Modes, shots-15028|17920/norm_pop1)
gets its own back button, once per screen (select / detail / lobby; a stale
repeat must not re-tap: (793,1000) on the lobby is its Challenge bar), one
extra step each.

Exit: 0 world/panel reached, 1 still unknown after the cap.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import afk_claim_vision as v  # noqa: E402

POPUP_STREAK = 5        # LIVE: 5 POPUP reads in a row = zombie popup (03.11.: 0..4 POPUP)
ESCAPE_CYCLES = 2       # LIVE: ladder repetitions before giving up
LADDER = ('resolver', 'back', 'ground', 'back2')
PURCHASE_WORDS = ('purchase', 'buy', 'recharge', 'top up', 'top-up', 'diamond', 'pack')
# T91 Dream Realm prep: its back button spans x 481-598 / y 945-1038; v.BACK
# (474,1010) sits 7 px left of it on the cream panel (it did leave the prep
# live, shots-80660/norm_0 -> norm_1), the arrow centre is the safe spot.
# Leaving takes prep -> boss page -> Battle Modes -> world (norm_0..final),
# one step more than the 4-step pass had: the prep BACK gets its own step.
# LIVE: button extent measured on shots-66808/dr_f1_prewait1 + shots-80660/norm_0
# ((535,1000) reads (199,188,187) on both); (535,1000) not yet tapped live.
DR_PREP_BACK = (535, 1000)
# T93: a Dream Realm fight left on its result screens (Victory Rewards overlay
# over the BATTLE ENDED card, both UNKNOWN). BACK there is unsafe: on the
# overlay it only reveals the card (shots-69680/norm_0 -> norm_1), on the card
# (474,1010) hit Replay and restarted the fight (norm_1 -> norm_2 'Battle
# Begins', norm_final 'Replaying...'). Each gets dr.CARD_CLOSE instead.
DR_END_TAPS = 2         # overlay + card; one extra step each


def escape_ladder(tag: str = 'esc', cycles: int = ESCAPE_CYCLES) -> bool:
    """Bounded escape from a screen the normal pass could not leave. True when
    WORLD/PANEL was reached (marker 'ESCAPE: recovered'), else 'ESCAPE: gave up'."""
    for cycle in range(1, cycles + 1):
        for step in LADDER:
            name = f'{tag}_{cycle}_{step}'
            img = v.shot(name)
            st = v.classify(img)
            if st in ('WORLD', 'PANEL'):
                print(f'    ESCAPE: recovered ({st}) before step {step}, cycle {cycle}', flush=True)
                return True
            if v.is_confirm_dialog(img):
                print(f'    escape {cycle}/{step}: confirm dialog -> cancel', flush=True)
                v.tap(v.CONFIRM_CANCEL, 1.5)
                continue
            if step == 'resolver':
                hit = v.resolve_startup_popup(f'{name}_pop')
                print(f'    escape {cycle}/{step}: login popup {"claimed" if hit else "not recognised"}',
                      flush=True)
            elif step == 'back':
                print(f'    escape {cycle}/{step}: BACK ({st})', flush=True)
                v.tap(v.BACK, 1.5)
            elif step == 'ground':
                lines = ' '.join(v.ocr_lines(name)).lower()
                if any(w in lines for w in PURCHASE_WORDS):
                    print(f'    escape {cycle}/{step}: purchase text on screen -> ground tap skipped',
                          flush=True)
                    continue
                print(f'    escape {cycle}/{step}: tap empty ground {v.GROUND}', flush=True)
                v.tap(v.GROUND, 1.5)
            else:
                print(f'    escape {cycle}/{step}: BACK x2 ({st})', flush=True)
                v.tap_seq([(*v.BACK, 1.2), (*v.BACK, 1.5)], tolerate=False)   # T75: 1 round trip
    st = v.classify(v.shot(f'{tag}_final'))
    if st in ('WORLD', 'PANEL'):
        print(f'    ESCAPE: recovered ({st}) after {cycles} cycle(s)', flush=True)
        return True
    print(f'    ESCAPE: gave up after {cycles} cycle(s), screen {st}', flush=True)
    return False


def main() -> int:
    import afk_dream_realm as dr    # lazy: afk_dream_realm imports this module
    import afk_arena as ar          # lazy, like dr: only normalize needs the arena tells
    popups, steps, i, ends, rec, arena = 0, 4, 0, 0, False, set()
    while i < steps:
        img = v.shot(f'norm_{i}')
        st = v.classify(img)
        print(f'    normalize {i}: {st}', flush=True)
        if st in ('WORLD', 'PANEL'):
            return 0
        popups = popups + 1 if st == 'POPUP' else 0
        if rec and (v.is_dr_boss(img) or st == 'DR_PREP'
                    or dr.is_victory_rewards(img) or dr.is_battle_ended(img)):
            print('    normalize: Dream Realm leftover after the recovery — giving up', flush=True)
            return 1
        if not rec and (v.is_dr_boss(img)
                        or (st == 'UNKNOWN' and (dr.is_uniform_dark(img) or v.is_ui_less(img)))):
            # T94: boss page (+ info card) / black / UI-less transition: the shared
            # bounded recovery; each T91/T93 Dream tap above added one step
            rec = True
            st, _ = v.recover_leftover('norm_rec', img, f'norm_{i}',
                                       budget=max(0, v.RECOVER_BUDGET - (steps - 4)))
            print(f'    normalize: after leftover recovery: {st}', flush=True)
            if st in ('WORLD', 'PANEL'):
                return 0
            if st != 'POPUP':
                return 1
            i += 1                      # login/promo popup: normalize's own pass resolves it
            continue
        if st == 'DR_PREP' and steps == 4 + ends + len(arena):   # T93/T95 taps add steps too
            steps += 1                  # T91: once — the prep BACK gets its own step
            print('    normalize: Dream Realm prep -> BACK', flush=True)
            v.tap(DR_PREP_BACK, 2.5)    # boss page loads behind it (norm_1 was mid-load)
        elif st == 'UNKNOWN' and (dr.is_victory_rewards(img) or dr.is_battle_ended(img)):
            if ends == DR_END_TAPS:
                break                   # never BACK here (Replay); norm_final decides
            ends, steps = ends + 1, steps + 1
            print('    normalize: Dream Realm result screen -> tap to close', flush=True)
            v.tap(dr.CARD_CLOSE, 2.5)
        elif (kind := 'select' if ar.is_select(img) else 'detail' if ar.is_detail(img)
              else 'lobby' if ar.is_lobby(img) else ''):
            if kind in arena:           # still mid-transition: wait, never the resolver/BACK
                print(f'    normalize: arena {kind} after its back tap — waiting', flush=True)
                time.sleep(2.5)
            else:
                arena.add(kind)
                steps += 1              # T95: counts toward the T94 budget
                print(f'    normalize: arena {kind} -> back', flush=True)
                v.tap(ar.LOBBY_BACK if kind == 'lobby' else ar.SELECT_ARROW, 2.5)
        elif st == 'POPUP' and v.resolve_startup_popup(f'norm_pop{i}'):
            time.sleep(1.0)
        else:
            v.tap(v.BACK, 1.5)
        i += 1
    st = v.classify(v.shot('norm_final'))
    print(f'    normalize final: {st}', flush=True)
    if st in ('WORLD', 'PANEL'):
        return 0
    popups = popups + 1 if st == 'POPUP' else 0
    if popups >= POPUP_STREAK:
        print(f'    normalize: {popups}x POPUP in a row — escape ladder', flush=True)
        return 0 if escape_ladder('norm_esc') else 1
    return 1


if __name__ == '__main__':
    sys.exit(main())
