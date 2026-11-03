' Fensterloser Starter fuer den AFK-Night-Push (Windows-Task "Spectre AFK Night", 02:00).
' Gleiches Muster wie afk-bot-scheduled.vbs: Run-Fensterstil 0 = komplett
' versteckt, bWaitOnReturn=True + WScript.Quit: der Task meldet den echten
' Exit-Code des Laufs (Diagnose bleibt erhalten).
Option Explicit
Dim sh, cmdline, rc
Set sh = CreateObject("WScript.Shell")
cmdline = "cmd.exe /c """"" & "C:\Users\Sigi\spectre\scripts\afk-bot-night.cmd" & """"""
rc = sh.Run(cmdline, 0, True)
WScript.Quit rc
