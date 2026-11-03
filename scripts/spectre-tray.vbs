' Fensterloser Starter fuer das Spectre-Tray-Icon (T66).
' Startet scripts\spectre-tray.ps1 versteckt (Fensterstil 0) und wartet nicht.
' Das Skript haelt sich per Mutex selbst einzig; ein zweiter Start beendet sich sofort.
' Autostart: Verknuepfung auf diese Datei in shell:startup legen.
Option Explicit
Dim sh, fso, ps1
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ps1 = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "spectre-tray.ps1")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File """ & ps1 & """", 0, False
