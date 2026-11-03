@echo off
REM Scheduled entry point for the AFK Journey NIGHT push (02:00).
REM Night run = 135 min stage push with --retry-defeats (the retry loop wins the
REM wall eventually). Idle-gated: skips when the PC is in use, exits mid-run
REM when someone starts working (per-iteration idle re-check in the script).
REM Log: C:\Users\Sigi\spectre\.spectre\logs\afk-bot-<date>.log
REM IMPORTANT: always start this via afk-bot-night.vbs (hidden launcher).
"C:\Program Files\Git\bin\bash.exe" -lc "cd /c/Users/Sigi/spectre && bash scripts/afk-night.sh"
