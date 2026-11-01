' Fensterloser Starter fuer den AFK-Bot (Windows-Task "Spectre AFK Progress", 17:10).
' Warum: Der Task rief bisher direkt afk-bot-progress.cmd auf. Unter dem
' interaktiven Benutzerkonto erzeugt das jedes Mal ein sichtbares Konsolen-
' fenster (cmd -> bash -> python), das ca. 1-5 s schwarz aufblitzt.
' Run-Fensterstil 0 = komplett versteckt, Konsole wird gar nicht erst angezeigt.
' bWaitOnReturn=True + WScript.Quit: der Task meldet weiterhin den echten
' Exit-Code des Bot-Laufs (Diagnose bleibt erhalten).
Option Explicit
Dim sh, cmdline, rc
Set sh = CreateObject("WScript.Shell")
cmdline = "cmd.exe /c """"" & "C:\Users\Sigi\spectre\scripts\afk-bot-progress.cmd" & """"""
' cmd /c "..." - die inneren Quotes schuetzen den Pfad gegen Leerzeichen.
rc = sh.Run(cmdline, 0, True)
WScript.Quit rc
