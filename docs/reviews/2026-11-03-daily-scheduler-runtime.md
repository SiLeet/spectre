# Daily scheduler runtime review — 2026-11-03

## Scope

The P5 Dailies-Roadmap section had no open `⬜` item, so this run reviewed the latest scheduler evidence and made one focused wrapper improvement. `TODOS.md` was not edited, per `CLAUDE.md`.

## Runtime evidence

- `Spectre AFK Daily` ran at 05:10 local (04:10Z) and Task Scheduler reported `0x00000000`.
- `Spectre AFK Night` last ran at 02:00 with `0x00000000`, before the R12 wrapper fix; it is not a post-fix verification. `Spectre AFK Progress` remains at its 2026-11-02 18:36 result `0x800710E0`, with its next run due at 17:10 today.
- `.spectre/logs/afk-bot-2026-11-03.log` shows the initial AFK chest claim verified, then the Journey's Gift driver reported no visible Login Rewards entry (exit 3 / warning).
- The later gameplay chain did not complete cleanly: Arena reached `STUCK` (`SELECT` → repeated `RESULT`), normalization ended at `POPUP`, Dream Realm could not reach the world view, and Stage Push rejected the observed `BATTLE` state. The normalizer continued to report `POPUP`.
- The task result was misleading: `afk-bot-watch.sh` returned the initial chest driver's success code and did not fold in later phase failures or gate on a failed normalization.

## Change

`scripts/afk-bot-watch.sh` now accumulates nonzero Daily phase results for Task Scheduler. If screen normalization fails, the wrapper reports the failure and aborts the remaining gameplay phases rather than starting them on an unknown screen. The Journey's Gift exit 3 remains warning-only because the driver documents it as ambiguous (already claimed, event gone, or camera pan missed); it does not set the daily marker.

The behavior is documented in `docs/afk-journey-guide.md`. Regression coverage in `scripts/tests/test_afk_daily_exit_code.py` verifies both fail-closed normalization and propagation of a later Arena failure while subsequent safe phases still run.

## Verification

- Focused wrapper tests: 2/2 passed.
- `python -m unittest discover -s scripts/tests`: 191 tests passed, 22 skipped.
- The frame-regression harness skipped its 139 manifest frames because the archived screenshots are absent locally; those image cases were not re-exercised.
- `bash -n scripts/afk-bot-watch.sh` and `git diff --check`: passed.
- No live game taps were made during this review.

## Fresh-eyes follow-up batch (not changed here)

- Gift exit 3 can also mean the pan missed a claimable entry; warning-only handling can therefore leave a possible missed claim while the task returns success.
- Marker-file write failures are not included in the aggregate result, so a phase may succeed but be eligible to run again.

These were kept out of this focused fix batch; `TODOS.md` remains untouched per the repo instruction.
