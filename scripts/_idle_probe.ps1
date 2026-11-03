$sig = @'
[DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
'@
Add-Type -MemberDefinition $sig -Name PI -Namespace W
$lii = New-Object W.PI+LASTINPUTINFO
$lii.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($lii)
[void][W.PI]::GetLastInputInfo([ref]$lii)
$idle = [int](([Environment]::TickCount - [uint32]$lii.dwTime) / 1000)
Write-Output "IDLE_SECONDS=$idle"
