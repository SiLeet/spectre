@echo off
REM Scheduled entry point for the AFK Journey PROGRESS run (17:10).
REM Progress run = chest claim (vision driver) + stage push (--auto) only.
REM All once-per-day tasks (gift, quests, mail, arena, dream realm) stay in
REM the Daily run ("Spectre AFK Daily", 05:10) via afk-bot-scheduled.cmd.
REM Log: C:\Users\Sigi\spectre\.spectre\logs\afk-bot-<date>.log
REM IMPORTANT: always start this via afk-bot-progress.vbs (hidden launcher).
"C:\Program Files\Git\bin\bash.exe" -lc "cd /c/Users/Sigi/spectre && bash scripts/afk-bot-watch.sh --scheduled-progress"
