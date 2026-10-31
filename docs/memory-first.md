# Memory-first automation (no pixel/OCR)

Spectre is designed to drive bots from **game memory**, not from screenshots.
Pixel/OCR is only used for one-time calibration (finding a first screen
transition); all subsequent state detection and navigation should read the
game's own memory.

## Why

- Screenshots + OCR are slow, fragile (fonts, res, overlays), and useless for
  values the UI rounds ("259K" instead of 259850).
- The game already tracks its own UI state, scene, currencies, energy, timers —
  that data lives in process memory and is the *source of truth*.
- A bot that reads memory reacts instantly and exactly; a bot that OCRs
  re-detects the same label every frame.

## What to read from memory instead of pixels

| UI concept            | Memory counterpart                                       |
| --------------------- | -------------------------------------------------------- |
| Which screen is open  | UI/scene state enum or current view object (stable int)  |
| Gold / diamonds       | u32/u64 resource slots (verified via hunt + action diff) |
| Buttons claimable     | quest/red-dot flags (bool per quest entry)               |
| Timers / countdowns   | unix-epoch or seconds-since-midnight u32/u64             |
| Energy / stamina      | numeric slot that refills on a timer                     |

## Finding a UI-state offset (calibration loop)

1. Pick two clearly different screens (e.g. Town vs Open World).
2. `spectre dump` the hot heaps in state A, transition to state B (one manual
   tap or a `spectre bot` action), dump again.
3. Diff with `spectre dumpdiff`; the slot that changed and *stays* at the new
   value across idle time (no churn) is the scene/state ID.
4. Record it in the game offsets YAML (e.g. `ui_state: { type: u32, address: ... }`)
   and gate bot actions on it: `if ui_state != expected { wait; retry }`.

See `reference: android-emulator-memory-reading` skill for the full
offset-discovery workflow (spectre hunt + action diff).