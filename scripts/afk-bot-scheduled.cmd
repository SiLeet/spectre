@echo off
REM Scheduled entry point for the AFK Journey claim bot.
REM Registered as Windows Task "Spectre AFK Bot" (every 15 min). The wrapper
REM only acts when the PC has been idle for AFK_MIN_IDLE seconds (default 180)
REM and when the game is on a known screen, so it never fights manual play.
REM Log: C:\Users\Sigi\spectre\.spectre\logs\afk-bot-<date>.log
"C:\Program Files\Git\bin\bash.exe" -lc "cd /c/Users/Sigi/spectre && bash scripts/afk-bot-watch.sh --scheduled"
