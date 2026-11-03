# spectre-tray.ps1 — Tray-Icon, solange ein Spectre-Bot-Lauf aktiv ist (T66).
#
# Signal: .spectre\afk-bot.lock — afk-bot-watch.sh und afk-night.sh legen ihn
# für die Dauer eines Laufs an, ein Keeper frischt ihn alle 240 s auf.
#   Lock frisch (< AFK_LOCK_STALE, Default 3600 s) -> grünes Icon "läuft"
#   Lock älter                                    -> oranges Icon "Lock veraltet"
#   kein Lock                                     -> Icon ausgeblendet
# Tooltip: aktuelle Phase = letzte "=== ..."-Zeile des heutigen Bot-Logs.
# Menü: Log öffnen · Wall-Dashboard · .spectre-Ordner · Tray beenden.
# Läuft nur lesend; nichts am Bot/Gerät wird angefasst.
#
# Start (versteckt): wscript scripts\spectre-tray.vbs
# Debug/Test:        powershell -File scripts\spectre-tray.ps1 -StateOnly
param(
    [string]$SpectreDir = (Join-Path (Split-Path -Parent $PSScriptRoot) '.spectre'),
    [int]$PollSeconds = 5,
    [switch]$StateOnly
)

$StaleSeconds = 3600
if ($env:AFK_LOCK_STALE -match '^\d+$') { $StaleSeconds = [int]$env:AFK_LOCK_STALE }

function Get-TodayLog {
    Join-Path $SpectreDir ("logs\afk-bot-{0}.log" -f [DateTime]::UtcNow.ToString('yyyy-MM-dd'))
}

function Get-SpectreState {
    $lock = Join-Path $SpectreDir 'afk-bot.lock'
    $log = Get-TodayLog
    $phase = ''
    if (Test-Path -LiteralPath $log) {
        $last = Get-Content -LiteralPath $log -Tail 400 -ErrorAction SilentlyContinue |
            Where-Object { $_ -like '=== *' } | Select-Object -Last 1
        # "=== 2026-11-03T05:12:00Z arena attempt 1/4" -> "arena attempt 1/4"
        if ($last) { $phase = ($last -replace '^=== \S+\s*', '').Trim() }
    }
    if (-not (Test-Path -LiteralPath $lock)) {
        return [pscustomobject]@{ State = 'idle'; Pid = ''; Age = 0; Phase = $phase }
    }
    $item = Get-Item -LiteralPath $lock
    $age = [int]([DateTime]::Now - $item.LastWriteTime).TotalSeconds
    $procId = Get-Content -LiteralPath $lock -TotalCount 1 -ErrorAction SilentlyContinue
    $state = if ($age -lt $StaleSeconds) { 'running' } else { 'stale' }
    return [pscustomobject]@{ State = $state; Pid = "$procId".Trim(); Age = $age; Phase = $phase }
}

if ($StateOnly) {
    $s = Get-SpectreState
    "{0} pid={1} age={2}s phase={3}" -f $s.State, $s.Pid, $s.Age, $s.Phase
    exit 0
}

# one tray per user session
$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Local\SpectreTray', [ref]$created)
if (-not $created) { exit 0 }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function New-DotIcon([System.Drawing.Color]$color) {
    $bmp = New-Object System.Drawing.Bitmap 16, 16
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.FillEllipse((New-Object System.Drawing.SolidBrush $color), 1, 1, 14, 14)
    $g.DrawEllipse([System.Drawing.Pens]::Black, 1, 1, 14, 14)
    $g.Dispose()
    return [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
}

$icons = @{
    running = New-DotIcon ([System.Drawing.Color]::FromArgb(46, 160, 67))
    stale   = New-DotIcon ([System.Drawing.Color]::FromArgb(230, 140, 20))
}

$tray = New-Object System.Windows.Forms.NotifyIcon
$tray.Visible = $false

function Open-Path([string]$path) {
    if (Test-Path -LiteralPath $path) { Start-Process -FilePath $path }
    else { $tray.ShowBalloonTip(3000, 'Spectre', "Nicht gefunden: $path", 'Warning') }
}

$menu = New-Object System.Windows.Forms.ContextMenuStrip
[void]$menu.Items.Add('Log öffnen', $null, { Open-Path (Get-TodayLog) })
[void]$menu.Items.Add('Wall-Dashboard öffnen', $null, { Open-Path (Join-Path $PSScriptRoot 'spectre-walls.html') })
[void]$menu.Items.Add('.spectre-Ordner öffnen', $null, { Open-Path $SpectreDir })
[void]$menu.Items.Add('-')
[void]$menu.Items.Add('Tray beenden', $null, { $tray.Visible = $false; [System.Windows.Forms.Application]::Exit() })
$tray.ContextMenuStrip = $menu
$tray.add_DoubleClick({ Open-Path (Get-TodayLog) })

function Update-Tray {
    $s = Get-SpectreState
    if ($s.State -eq 'idle') {
        $tray.Visible = $false
        return
    }
    $text = if ($s.State -eq 'running') { "Spectre läuft: $($s.Phase)" }
            else { "Spectre: Lock veraltet ($([int]($s.Age / 60)) min)" }
    if ($text.Length -gt 63) { $text = $text.Substring(0, 63) }   # NotifyIcon.Text limit
    $tray.Icon = $icons[$s.State]
    $tray.Text = $text
    if (-not $tray.Visible) {
        $tray.Visible = $true
        $tray.ShowBalloonTip(3000, 'Spectre', $text, 'Info')
    }
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = [Math]::Max(1, $PollSeconds) * 1000
$timer.add_Tick({ Update-Tray })
$timer.Start()
Update-Tray
[System.Windows.Forms.Application]::Run()

$timer.Stop()
$tray.Visible = $false
$tray.Dispose()
$mutex.ReleaseMutex()
