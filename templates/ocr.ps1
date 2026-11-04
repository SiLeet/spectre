# WinRT OCR (Windows.Media.Ocr) on a PNG - offline, no dependencies.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr.ps1 -Path <png> [-Boxes]
# Prints one line per recognized OCR line; with -Boxes as 'x y w h text'
# (integer pixel bounding box of the line = union of its word boxes).
param([Parameter(Mandatory=$true)][string]$Path, [switch]$Boxes)

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                   $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType=WindowsRuntime]

# StorageFile APIs need native backslash paths
$Path = $Path.Replace('/', '\')

$ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $ocr) { Write-Error 'no OCR engine'; exit 1 }

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($ocr.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

foreach ($line in $result.Lines) {
    if (-not $Boxes) { $line.Text; continue }
    $r = $line.Words | ForEach-Object { $_.BoundingRect }
    $x0 = ($r | ForEach-Object { $_.X } | Measure-Object -Minimum).Minimum
    $y0 = ($r | ForEach-Object { $_.Y } | Measure-Object -Minimum).Minimum
    $x1 = ($r | ForEach-Object { $_.X + $_.Width } | Measure-Object -Maximum).Maximum
    $y1 = ($r | ForEach-Object { $_.Y + $_.Height } | Measure-Object -Maximum).Maximum
    '{0} {1} {2} {3} {4}' -f [int]$x0, [int]$y0, [int]($x1 - $x0), [int]($y1 - $y0), $line.Text
}
