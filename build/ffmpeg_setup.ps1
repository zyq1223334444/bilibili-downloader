# =====================================================================
#  ffmpeg_setup.ps1 -- resolve / extract ffmpeg for bilibili-downloader
#
#  Called by installer.iss while the setup is running. The actual download
#  is done by Inno Setup itself (TDownloadWizardPage) so the user sees a
#  real progress bar and can stop it; this script only does the small,
#  non-blocking jobs around it:
#
#      -Mode Url      write the resolved archive URL into -OutFile
#      -Mode Size     write the archive's real size into -OutFile
#      -Mode Extract  unpack the already downloaded -Zip into <Dest>\bin
#      -Mode Install  download + extract in one go (standalone use)
#
#  Size must query the live URL (the installer shows that number before
#  asking), never a hardcoded guess.
#
#  Keep this file ASCII-only: Windows PowerShell 5.1 reads .ps1 as ANSI
#  unless it carries a BOM, so non-ASCII text would arrive garbled.
# =====================================================================
param(
    [ValidateSet('Url', 'Size', 'Extract', 'Install')]
    [string]$Mode = 'Size',
    [string]$Url = '',
    [string]$Zip = '',
    [string]$Dest = '',
    [string]$OutFile = ''
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# gyan.dev is the upstream release page, but it served ~30 KB/s here, so the URL
# is resolved through the GitHub API first (same archive, an order of magnitude faster).
$FallbackUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$ReleaseApi = 'https://api.github.com/repos/GyanD/codexffmpeg/releases/latest'

function Write-Out([string]$Text) {
    if ($OutFile) {
        Set-Content -LiteralPath $OutFile -Value $Text -Encoding ASCII
    }
}

# Resolve the current essentials zip. Its asset name carries the version (9.1),
# so it cannot be hardcoded; query the API and fall back to $FallbackUrl.
function Resolve-Url {
    if ($Url) { return $Url }
    try {
        $headers = @{ 'User-Agent' = 'bilibili-downloader-setup' }
        $resp = Invoke-WebRequest -Uri $ReleaseApi -Headers $headers -UseBasicParsing -TimeoutSec 20
        $json = $resp.Content | ConvertFrom-Json
        $asset = $json.assets | Where-Object { $_.name -like '*essentials_build.zip' } |
                 Select-Object -First 1
        if ($asset -and $asset.browser_download_url) { return [string]$asset.browser_download_url }
    }
    catch { }
    return $FallbackUrl
}

# Copy the archive's bin\ folder into <Dest>\bin, then make sure the copy starts.
function Install-Bin([string]$SrcRoot, [string]$Target) {
    $exe = Get-ChildItem -LiteralPath $SrcRoot -Recurse -Filter 'ffmpeg.exe' |
           Where-Object { $_.Directory.Name -eq 'bin' } |
           Select-Object -First 1
    if (-not $exe) { throw 'ffmpeg.exe not found inside the archive' }

    $bin = Join-Path $Target 'bin'
    New-Item -ItemType Directory -Path $bin -Force | Out-Null
    Copy-Item -Path (Join-Path $exe.DirectoryName '*') -Destination $bin -Force

    $installed = Join-Path $bin 'ffmpeg.exe'
    & $installed -version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'installed ffmpeg does not start' }
}

try {
    if (-not $Dest) { $Dest = Join-Path $env:USERPROFILE 'ffmpeg' }

    if ($Mode -eq 'Url') {
        Write-Out (Resolve-Url)
    }
    elseif ($Mode -eq 'Size') {
        $target = Resolve-Url
        # A HEAD request is rejected by the GitHub asset host, so ask for the
        # first byte and read the total out of Content-Range (bytes 0-0/119467219).
        $request = [System.Net.HttpWebRequest]::Create($target)
        $request.Method = 'GET'
        $request.UserAgent = 'bilibili-downloader-setup'
        $request.AllowAutoRedirect = $true
        $request.Timeout = 25000
        $request.AddRange(0, 0)
        $response = $request.GetResponse()
        $range = [string]$response.Headers['Content-Range']
        $length = 0
        if ($range -match '/(\d+)$') { $length = [int64]$Matches[1] }
        if ($length -le 0) { $length = $response.ContentLength }
        $response.Close()
        if ($length -le 0) { throw 'server did not report a size' }
        Write-Out ([string]$length)
    }
    elseif ($Mode -eq 'Extract') {
        if (-not $Zip) { throw 'no -Zip given' }
        if (-not (Test-Path -LiteralPath $Zip)) { throw "archive not found: $Zip" }
        $tmp = Join-Path $env:TEMP ('bili_ffmpeg_' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        try {
            Expand-Archive -LiteralPath $Zip -DestinationPath $tmp -Force
            Install-Bin $tmp $Dest
        }
        finally {
            Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Out 'OK'
    }
    else {
        $target = Resolve-Url
        $tmp = Join-Path $env:TEMP ('bili_ffmpeg_' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        try {
            $zipFile = Join-Path $tmp 'ffmpeg.zip'
            (New-Object System.Net.WebClient).DownloadFile($target, $zipFile)
            $unzip = Join-Path $tmp 'unzip'
            Expand-Archive -LiteralPath $zipFile -DestinationPath $unzip -Force
            Install-Bin $unzip $Dest
            Write-Out 'OK'
        }
        finally {
            Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    exit 0
}
catch {
    Write-Out ('ERR: ' + $_.Exception.Message)
    exit 1
}
