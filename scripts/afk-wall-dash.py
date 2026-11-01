#!/usr/bin/env python3
"""Generate the AFK Journey wall dashboard widget (spectre-walls.html).

Reads the wall report JSONL (written by afk_stage_push.py / afk-bot-watch.sh)
and the current stage snapshot, then renders a self-contained HTML widget for
the Hermes chat. The "Refresh" button sends a prompt back to the agent, which
re-runs this script after the next bot check.
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spectre-walls.html")
STATE = os.path.join(ROOT, ".spectre", "afk-state.json")
JSONL = os.path.join(ROOT, ".spectre", "wall-report.log")


def load():
    """Return (current, events) from the local wall report files."""
    cur = {}
    if os.path.exists(STATE):
        try:
            cur = json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    evs = []
    if os.path.exists(JSONL):
        for line in open(JSONL, encoding="utf-8"):
            try:
                evs.append(json.loads(line))
            except Exception:
                continue
    return cur, evs


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def human_ts(ts):
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
    except Exception:
        return str(ts)


def main():
    cur, evs = load()
    if not cur:
        cur = {"stage": 0, "power": 0}
    if not evs:
        sys.exit(0)  # no data yet — don't write an empty widget

    last = evs[-1]
    defeated = sum(1 for e in evs if e.get("reason") == "defeat")
    progress = sum(1 for e in evs if e.get("reason") == "progress")
    rows = "".join(
        f"<tr><td>{human_ts(e.get('ts', 0))}</td>"
        f"<td>{esc(e.get('stage', '—'))}</td>"
        f"<td>{esc('{:,}'.format(e['power']) if e.get('power') else '—')}</td>"
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
    <div><div class="v">{cur.get('stage', '?')}</div><div class="l">Stage</div></div>
    <div><div class="v">{cur.get('power', 0):,}</div><div class="l">Power</div></div>
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
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"wrote {OUT} ({len(evs)} events)")


if __name__ == "__main__":
    main()
