#!/usr/bin/env python3
"""Explore + level the 5 Hands of Resonance heroes (AFK Journey, BlueStacks).

For each hand card (x in 710/840/970/1100/1220, y=500): tap it, OCR the detail
screen (hero name + level), if level < 90 tap the x10 button (1460,1065), OCR
again to verify, then BACK. Prints one line per hand with real OCR output.
"""
import re, subprocess, sys, time, pathlib

ADB = r"C:\Users\Sigi\AppData\Local\Android\Sdk\platform-tools\adb.exe"
SERIAL = "127.0.0.1:5555"
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
OCR = r"C:\Users\Sigi\spectre\templates\ocr.ps1"
SHOTDIR = pathlib.Path(r"C:\Users\Sigi\spectre\.spectre")

def sh(*args, **kw):
    return subprocess.run([ADB, "-s", SERIAL, *args], capture_output=True, timeout=kw.get("timeout", 30))

def tap(x, y, wait=1.0):
    sh("shell", "input", "tap", str(x), str(y))
    time.sleep(wait)

def key(keycode, wait=1.5):
    sh("shell", "input", "keyevent", str(keycode))
    time.sleep(wait)

def shot(name):
    path = SHOTDIR / name
    with open(path, "wb") as fh:
        subprocess.run([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"], stdout=fh, timeout=60)
    return str(path)

def ocr(png):
    png = str(pathlib.PureWindowsPath(png))
    try:
        p = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", OCR, "-Path", png],
                           capture_output=True, timeout=20, text=True,
                           encoding="utf-8", errors="replace")
        return [l.strip() for l in p.stdout.splitlines() if l.strip()]
    except Exception:
        return []

def read_level(lines):
    for ln in lines:
        m = re.search(r"Lv[.\s]*l?\.?\s*(\d{1,3})", ln)
        if m:
            return int(m.group(1))
    return None

def name_of(lines):
    for ln in lines:
        for pat in ("Dragonslayer", "Knight of Valor", "Knight", "Hodgkin", "Sinbad",
                    "Gwyneth", "Koko", "Rowan", "Brutus", "Antandra", "Cecia"):
            if pat.lower() in ln.lower():
                return pat
    return None

def hero_detail(name):
    png = shot(f"hl_{name}.png")
    lines = ocr(png)
    lvl = read_level(lines)
    nm = name_of(lines)
    return lvl, nm, lines

HANDS = [710, 840, 970, 1100, 1220]

def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    for x in HANDS:
        tap(x, 500, 3.0)
        png = shot(f"hl_{x}.png")
        lvl, nm, lines = None, None, ocr(png)
        for ln in lines:
            m = re.search(r"Lv[.\s]*l?\.?\s*(\d{1,3})", ln)
            if m:
                lvl = int(m.group(1))
                nm = ln.strip()[:40]
                break
        print(f"HAND x={x}: lines={len(lines)} level={lvl} first={lines[0][:40] if lines else ''}",
              flush=True)
        if lvl is None:
            key(4)
            continue
        if lvl >= target:
            print(f"    hand {x}: level {lvl} >= {target} — skip", flush=True)
            key(4)
            continue
        # level up: x10 button at (1460,1065)
        tap(1460, 1065, 3.0)
        png2 = shot(f"hl_{x}_after.png")
        lines2 = ocr(png2)
        lvl2 = read_level(lines2)
        print(f"    hand {x}: {lvl} -> {lvl2}", flush=True)
        key(4)
    print("done", flush=True)

if __name__ == "__main__":
    main()