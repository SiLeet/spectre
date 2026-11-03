#!/usr/bin/env python3
"""Generate the AFK Journey wall dashboard widget (spectre-walls.html).

Reads the wall report JSONL (written by afk_stage_push.py / afk-bot-watch.sh),
takes the current stage/power from its newest events and renders a self-contained HTML widget for
the Hermes chat. The "Refresh" button sends a prompt back to the agent, which
re-runs this script after the next bot check.
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spectre-walls.html")
JSONL = os.path.join(ROOT, ".spectre", "wall-report.log")


def load_events(path):
    """Parse the wall-report JSONL. Returns (events, bad_lines).

    Only JSON objects are events; unparsable lines and JSON that is not an
    object ('null', '123', '[1,2]') are collected as bad lines instead of being
    swallowed (or crashing the render later). Blank lines are ignored."""
    evs, bad = [], []
    if not os.path.exists(path):
        return evs, bad
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                obj = None
            if isinstance(obj, dict):
                evs.append(obj)
            else:
                bad.append(line.rstrip("\r\n"))
    return evs, bad


def current(evs):
    """Latest known stage/power from the events themselves (the old
    .spectre/afk-state.json source is written by nothing): newest non-null
    value per field."""
    cur = {"stage": None, "power": None}
    for e in reversed(evs):
        for k in cur:
            if cur[k] is None and e.get(k) is not None:
                cur[k] = e[k]
    return cur


def or_dash(v):
    return "—" if v is None else v


def fmt_int(v):
    """'74,986' for anything int-like (int, '74986', 74986.0); '—' otherwise."""
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "—"


def reason_family(reason):
    """'wall' | 'progress' | 'other' for afk_stage_push.wall_report reasons.

    Producer vocabulary: wall_defeat_*, auto_defeat_after_*, battle_N_defeat
    and auto_prep_stop_* ('wall reached') are walls; single_push_complete_*
    is the only stage gain. Exact 'defeat'/'progress' never occur, and
    'battle_N_no_victory_*' is a stall, not a win."""
    r = str(reason or "")
    if "defeat" in r or r.startswith("auto_prep_stop"):
        return "wall"
    if r.startswith("single_push_complete"):
        return "progress"
    return "other"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def human_ts(ts):
    """Local 'dd.mm HH:MM' for the producer's ISO strings (or epoch numbers)."""
    if ts is None:
        return "—"
    try:
        if isinstance(ts, str):
            dt = datetime.datetime.fromisoformat(ts)
            dt = dt.astimezone() if dt.tzinfo else dt
        else:
            dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%d.%m %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(ts)


def main():
    evs, bad = load_events(JSONL)
    if not evs:   # no data yet — don't write an empty widget
        print(f"no events, skipped {len(bad)} bad lines — widget not written")
        return

    cur = current(evs)
    families = [reason_family(e.get("reason")) for e in evs]
    defeated = families.count("wall")
    progress = families.count("progress")
    rows = "".join(
        f"<tr><td>{human_ts(e.get('ts'))}</td>"
        f"<td>{esc(or_dash(e.get('stage')))}</td>"
        f"<td>{fmt_int(e.get('power'))}</td>"
        f"<td>{esc(e.get('reason', '?'))}</td></tr>"
        for e in reversed(evs[-30:])
    )
    now = datetime.datetime.now().strftime("%H:%M:%S")
    html = f"""<!doctype html>
<meta charset="utf-8">
<div id="wall-dash">
  <div class="head">
    <span class="t">AFK Journey — Wall Dashboard</span>
    <span class="btn" data-hermes-send="prompt">Refresh</span>
    <span class="ts">{now}</span>
  </div>
  <div class="stats">
    <div><div class="v">{esc(or_dash(cur.get('stage')))}</div><div class="l">Stage</div></div>
    <div><div class="v">{fmt_int(cur.get('power'))}</div><div class="l">Power</div></div>
    <div><div class="v">{len(evs)}</div><div class="l">Reports</div></div>
    <div><div class="v">{defeated}</div><div class="l">Walls</div></div>
    <div><div class="v">{progress}</div><div class="l">Progress</div></div>
  </div>
  <table>
    <tr><th>Time</th><th>Stage</th><th>Power</th><th>Event</th></tr>
    {rows}
  </table>
</div>
<style>
  :root {{
    --bg: var(--card, #1a1a1a); --fg: var(--foreground, #eee);
    --mut: var(--muted-foreground, #888); --acc: var(--accent, #4f8cff);
    --bd: var(--border, #333);
  }}
  body {{ margin: 0; padding: 0; background: transparent; color: var(--fg);
         font: 12px/1.5 var(--font, sans-serif); }}
  #wall-dash {{ max-width: 520px; }}
  .head {{ display: flex; align-items: center; gap: 8px; padding: 6px 8px; }}
  .head .t {{ font-weight: 600; flex: 1; }}
  .head .btn {{ padding: 2px 10px; border: 1px solid var(--bd); border-radius: 4px;
         cursor: pointer; user-select: none; }}
  .head .btn:hover {{ border-color: var(--acc); color: var(--acc); }}
  .head .ts {{ color: var(--mut); font-size: 10px; }}
  .stats {{ display: flex; gap: 4px; padding: 0 8px 6px; }}
  .stats > div {{ flex: 1; background: var(--bg); border: 1px solid var(--bd);
          border-radius: 6px; padding: 6px 4px; text-align: center; }}
  .stats .v {{ font-size: 15px; font-weight: 700; }}
  .stats .l {{ color: var(--mut); font-size: 10px; text-transform: uppercase;
        letter-spacing: .04em; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  th, td {{ padding: 3px 8px; border-bottom: 1px solid var(--bd); text-align: left; }}
  th {{ color: var(--mut); font-weight: 600; font-size: 10px; text-transform: uppercase;
      letter-spacing: .04em; }}
  td:nth-child(2), td:nth-child(3) {{ font-variant-numeric: tabular-nums; }}
  td:nth-child(4) {{ color: var(--mut); }}
</style>
"""
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    for ln in bad[:3]:
        print(f"bad line: {ln[:120]}", file=sys.stderr)
    print(f"wrote {OUT} ({len(evs)} events, skipped {len(bad)} bad lines)")


if __name__ == "__main__":
    main()
