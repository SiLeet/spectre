<#
.SYNOPSIS
    Harmless practice target for spectre: holds a "score" in memory and
    changes it every time you press Enter.

.DESCRIPTION
    Use this instead of a real game to learn the find -> search ->
    search --continue -> dump -> dumpdiff workflow (see examples/README.md).

    The score is stored as a little-endian 32-bit integer in a block of
    unmanaged memory (Marshal.AllocHGlobal). Unlike a normal PowerShell
    variable - a boxed .NET object that gets a new address on every change -
    this block stays at the same address for the life of the process, so
    `spectre search <pid> u32 <value> --continue` can follow it, just like a
    field inside a game's player struct.

    The script only touches its own memory. Close it with Ctrl+C or by
    typing q and Enter.

.PARAMETER Start
    Initial score (default 31337).

.PARAMETER Step
    Amount added on every Enter (default 100).

.PARAMETER Reveal
    Also print the address of the score - the "answer key". Leave it off the
    first time and find the address with spectre instead.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File examples\practice-target.ps1
#>
param(
    [uint32] $Start = 31337,
    [uint32] $Step = 100,
    [switch] $Reveal
)

$ErrorActionPreference = 'Stop'

# 64-byte block: the score sits at offset 0x10, surrounded by fixed marker
# bytes so a dump of the block has something recognisable around it.
$size = 64
$block = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
try {
    for ($i = 0; $i -lt $size; $i++) {
        [System.Runtime.InteropServices.Marshal]::WriteByte($block, $i, 0xAB)
    }
    $scoreOffset = 0x10
    $round = 0

    function Set-Score([uint32] $value) {
        # WriteInt32 stores the raw bits; reinterpret the uint32 as int32.
        $bits = [BitConverter]::ToInt32([BitConverter]::GetBytes($value), 0)
        [System.Runtime.InteropServices.Marshal]::WriteInt32($block, $scoreOffset, $bits)
        # Also count the rounds in the byte right after the score.
        [System.Runtime.InteropServices.Marshal]::WriteByte($block, $scoreOffset + 4, [byte]($round % 256))
    }

    function Get-Score {
        $bits = [System.Runtime.InteropServices.Marshal]::ReadInt32($block, $scoreOffset)
        [BitConverter]::ToUInt32([BitConverter]::GetBytes($bits), 0)
    }

    Set-Score $Start

    [Console]::Out.WriteLine("spectre practice target")
    [Console]::Out.WriteLine("PID:   $PID")
    if ($Reveal) {
        $addr = $block.ToInt64() + $scoreOffset
        [Console]::Out.WriteLine(('score address: 0x{0:x}  (block starts at 0x{1:x})' -f $addr, $block.ToInt64()))
    }
    [Console]::Out.WriteLine("score: $(Get-Score)")
    [Console]::Out.WriteLine("Press Enter to add $Step to the score, q + Enter to quit.")
    [Console]::Out.Flush()

    while ($true) {
        # [Console]::ReadLine works both in a console and with redirected stdin.
        $line = [Console]::ReadLine()
        if ($null -eq $line -or $line.Trim() -eq 'q') { break }
        $round++
        Set-Score ([uint32]((Get-Score) + $Step))
        [Console]::Out.WriteLine("score: $(Get-Score)")
        [Console]::Out.Flush()
    }
}
finally {
    [System.Runtime.InteropServices.Marshal]::FreeHGlobal($block)
}
