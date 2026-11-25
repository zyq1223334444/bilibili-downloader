# Regenerates assets\app.ico from a transparent square PNG.
#
#   powershell -ExecutionPolicy Bypass -File build\make_icon.ps1
#
# The .ico holds real PNG payloads (Vista+ layout): 16/24/32/48/64/128/256 px,
# so Explorer, the taskbar and the installer each pick a size that fits instead
# of rescaling one bitmap. Source PNG lives in assets\icon-source.png.

param(
    [string]$Source = (Join-Path $PSScriptRoot '..\assets\icon-source.png'),
    [string]$Out    = (Join-Path $PSScriptRoot '..\assets\app.ico'),
    [int[]]$Sizes   = @(16, 24, 32, 48, 64, 128, 256)
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$Source = (Resolve-Path -LiteralPath $Source).Path
$Out    = [System.IO.Path]::GetFullPath($Out)
$dir    = [System.IO.Path]::GetDirectoryName($Out)
if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$src = [System.Drawing.Image]::FromFile($Source)
try {
    $payloads = @()
    foreach ($size in $Sizes) {
        $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $g.InterpolationMode  = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.PixelOffsetMode    = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $g.SmoothingMode      = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $g.Clear([System.Drawing.Color]::Transparent)
        $g.DrawImage($src, 0, 0, $size, $size)
        $g.Dispose()

        $ms = New-Object System.IO.MemoryStream
        $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $payloads += ,@($size, $ms.ToArray())
        $ms.Dispose()
        $bmp.Dispose()
    }
}
finally {
    $src.Dispose()
}

# ICONDIR + one ICONDIRENTRY per image, then the PNG payloads back to back.
$fs = [System.IO.File]::Create($Out)
$bw = New-Object System.IO.BinaryWriter($fs)
try {
    $bw.Write([uint16]0)                 # reserved
    $bw.Write([uint16]1)                 # type: icon
    $bw.Write([uint16]$payloads.Count)   # image count

    $offset = 6 + 16 * $payloads.Count
    foreach ($p in $payloads) {
        $size = $p[0]
        $bytes = $p[1]
        $dim = if ($size -ge 256) { 0 } else { $size }   # 256 is stored as 0
        $bw.Write([byte]$dim)            # width
        $bw.Write([byte]$dim)            # height
        $bw.Write([byte]0)               # palette colours
        $bw.Write([byte]0)               # reserved
        $bw.Write([uint16]1)             # colour planes
        $bw.Write([uint16]32)            # bits per pixel
        $bw.Write([uint32]$bytes.Length)
        $bw.Write([uint32]$offset)
        $offset += $bytes.Length
    }
    foreach ($p in $payloads) { $bw.Write($p[1]) }
}
finally {
    $bw.Dispose()
    $fs.Dispose()
}

$len = (Get-Item -LiteralPath $Out).Length
Write-Host ("[OK] {0}  ({1} bytes, {2} sizes)" -f $Out, $len, $payloads.Count)
