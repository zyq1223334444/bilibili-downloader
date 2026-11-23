# =====================================================================
#  ffmpeg_setup.ps1 -- download / extract ffmpeg for bilibili-downloader
#
#  Called by installer.iss during setup; the program's own
#  --install-ffmpeg does the same thing in Python. Two modes:
#
#      -Mode Size     write the archive's Content-Length into -OutFile
#      -Mode Install  download + extract into <Dest>\bin, verify the exe
#
#  Size must query the live URL (the installer shows that number before
#  asking), never a hardcoded guess.
#
#  Keep this file ASCII-only: Windows PowerShell 5.1 reads .ps1 as ANSI
#  unless it carries a BOM, so non-ASCII text would arrive garbled.
# =====================================================================
param(
    [ValidateSet('Size', 'Install')]
    [string]$Mode = 'Size',
    [string]$Url = '',
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

try {
    if (-not $Dest) { $Dest = Join-Path $env:USERPROFILE 'ffmpeg' }
    $target = Resolve-Url

    if ($Mode -eq 'Size') {
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
    else {
        $tmp = Join-Path $env:TEMP ('bili_ffmpeg_' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        try {
            $zip = Join-Path $tmp 'ffmpeg.zip'
            (New-Object System.Net.WebClient).DownloadFile($target, $zip)

            $unzip = Join-Path $tmp 'unzip'
            Expand-Archive -LiteralPath $zip -DestinationPath $unzip -Force

            $exe = Get-ChildItem -LiteralPath $unzip -Recurse -Filter 'ffmpeg.exe' |
                   Where-Object { $_.Directory.Name -eq 'bin' } |
                   Select-Object -First 1
            if (-not $exe) { throw 'ffmpeg.exe not found inside the archive' }

            $bin = Join-Path $Dest 'bin'
            New-Item -ItemType Directory -Path $bin -Force | Out-Null
            Copy-Item -Path (Join-Path $exe.DirectoryName '*') -Destination $bin -Force

            $installed = Join-Path $bin 'ffmpeg.exe'
            & $installed -version | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'installed ffmpeg does not start' }

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
