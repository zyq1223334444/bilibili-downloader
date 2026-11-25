# =====================================================================
#  ffmpeg_setup.ps1 -- resolve / download / extract ffmpeg
#
#  Called by installer.iss while the setup is running:
#
#      -Mode Url       write the resolved archive URL into -OutFile
#      -Mode Size      write the archive's real size into -OutFile
#      -Mode Download  multi-threaded download into -Zip, with its own small
#                      progress window (total progress, total speed, stop)
#      -Mode Extract   unpack the already downloaded -Zip into <Dest>\bin
#      -Mode Install   silent multi-threaded download + extract (CLI use)
#
#  -Threads          parallel range requests (default 8)
#
#  -Source official  GitHub release asset (what Gyan publishes)
#  -Source mirror    same asset through https://ghfast.top, which is usable
#                    from mainland China without a proxy
#  -Source auto      official; if that cannot be resolved, gyan.dev
#
#  Size must query the live URL (the installer shows that number before
#  asking), never a hardcoded guess.
#
#  The parallel part lives in a small inline C# helper instead of PowerShell
#  runspaces: .NET threads start instantly and are not capped by the session
#  thread pool (runspace jobs were observed to stall at ~5 concurrent).
#  Memory stays flat: one 256 KB buffer per worker plus a 1 MB merge buffer,
#  so even a 200 MB archive costs only a few MB.
#
#  Keep this file UTF-8 *with BOM*: Windows PowerShell 5.1 reads .ps1 as ANSI
#  unless it sees a BOM, and the progress window below uses Chinese text.
# =====================================================================
param(
    [ValidateSet('Url', 'Size', 'Download', 'Extract', 'Install')]
    [string]$Mode = 'Size',
    [ValidateSet('auto', 'official', 'mirror')]
    [string]$Source = 'auto',
    [string]$Url = '',
    [string]$Zip = '',
    [string]$Dest = '',
    [string]$OutFile = '',
    [int]$Threads = 8
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# gyan.dev is the upstream release page, but it served ~30 KB/s here, so the URL
# is resolved through the GitHub API first (same archive, an order of magnitude faster).
$FallbackUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$ReleaseApi = 'https://api.github.com/repos/GyanD/codexffmpeg/releases/latest'
# ghfast.top proxies GitHub releases; measured ~4x faster than github.com from CN.
$MirrorPrefix = 'https://ghfast.top/'
$UserAgent = 'bilibili-downloader-setup'

function Write-Out([string]$Text) {
    if ($OutFile) {
        # 带 BOM 的 UTF-8：安装器（Inno Setup，Unicode）按 BOM 解码，中文提示不会变成 ????
        [System.IO.File]::WriteAllText($OutFile, $Text + [Environment]::NewLine,
            (New-Object System.Text.UTF8Encoding($true)))
    }
}

# Resolve the current essentials zip. Its asset name carries the version (9.1),
# so it cannot be hardcoded; query the API and fall back to $FallbackUrl.
function Resolve-Url {
    $base = ''
    if ($Url) {
        $base = $Url
    }
    else {
        try {
            $headers = @{ 'User-Agent' = $UserAgent }
            $resp = Invoke-WebRequest -Uri $ReleaseApi -Headers $headers -UseBasicParsing -TimeoutSec 20
            $json = $resp.Content | ConvertFrom-Json
            $asset = $json.assets | Where-Object { $_.name -like '*essentials_build.zip' } |
                     Select-Object -First 1
            if ($asset -and $asset.browser_download_url) { $base = [string]$asset.browser_download_url }
        }
        catch { }
        if (-not $base) { $base = $FallbackUrl }
    }
    if ($Source -eq 'mirror' -and $base -like 'https://github.com/*') {
        return $MirrorPrefix + $base
    }
    return $base
}

# Total size + whether the host honours Range requests. A HEAD request is
# rejected by the GitHub asset host, so ask for the first byte and read the
# total out of Content-Range (bytes 0-0/119467219).
function Get-RemoteMeta([string]$Target) {
    # 用 HttpClient：它的 Timeout 覆盖 DNS / 建连 / 等响应全过程。
    # 之前用 HttpWebRequest 时镜像源偶发卡在握手，安装器会长时间停在"准备安装"页。
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromSeconds(15)
    $resp = $null
    try {
        $req = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, $Target)
        [void]$req.Headers.TryAddWithoutValidation('User-Agent', $UserAgent)
        $req.Headers.Range = New-Object System.Net.Http.Headers.RangeHeaderValue(0, 0)
        $resp = $client.SendAsync($req).GetAwaiter().GetResult()
        $range = [string]$resp.Content.Headers.ContentRange
        $length = 0
        $ranges = $false
        if ($range -match '/(\d+)$') {
            $length = [int64]$Matches[1]
            $ranges = $true
        }
        if ($length -le 0 -and $resp.Content.Headers.ContentLength) {
            $length = [int64]$resp.Content.Headers.ContentLength
        }
        if ($length -le 0) { throw 'server did not report a size' }
        return @{ Length = $length; Ranges = $ranges }
    }
    catch {
        $why = $_.Exception.Message
        if ($_.Exception.InnerException) { $why = $_.Exception.InnerException.Message }
        throw ('读取文件大小失败：' + $why)
    }
    finally {
        if ($resp) { $resp.Dispose() }
        $client.Dispose()
    }
}

function Format-Mb([double]$Bytes) {
    return ('{0:N1} MB' -f ($Bytes / 1MB))
}
# ---- parallel downloader ---------------------------------------------------
# One background .NET thread per range; a dropped connection resumes from the
# bytes already on disk; the parts are then joined into the final archive.
# Progress is exposed as static fields so the caller can poll it cheaply.
$DownloaderCode = @'
using System;
using System.IO;
using System.Net;
using System.Threading;

public class FfDl
{
    public static long Total;
    public static long Done;
    public static volatile bool Stop;
    public static volatile bool Busy;
    public static volatile int Result;
    public static string Error;

    public static void Begin(string url, long total, string workDir, string zipPath,
                             int threads, bool ranges)
    {
        Total = total;
        Done = 0;
        Stop = false;
        Busy = true;
        Result = -1;
        Error = null;
        Thread t = new Thread(delegate() { Run(url, workDir, zipPath, threads, ranges); });
        t.IsBackground = true;
        t.Start();
    }

    static void Run(string url, string workDir, string zipPath, int threads, bool ranges)
    {
        try
        {
            if (threads < 1) threads = 1;
            if (threads > 16) threads = 16;
            if (!ranges) threads = 1;

            // HttpWebRequest allows only 2 connections per host by default,
            // which would serialise the workers; raise it first.
            ServicePointManager.DefaultConnectionLimit = 16;

            long seg = (long)Math.Ceiling((double)Total / threads);
            int n = 0;
            Thread[] workers = new Thread[threads];
            string[] parts = new string[threads];
            for (int i = 0; i < threads; i++)
            {
                long start = (long)i * seg;
                if (start >= Total) break;
                long end = start + seg - 1;
                if (end >= Total) end = Total - 1;
                parts[n] = Path.Combine(workDir, "part" + i.ToString("D2"));
                workers[n] = new Thread(new ParameterizedThreadStart(Worker));
                workers[n].IsBackground = true;
                workers[n].Start(new object[] { url, parts[n], start, end });
                n++;
            }
            for (int i = 0; i < n; i++) workers[i].Join();

            if (Stop) { Result = 3; return; }
            if (Error != null) { Result = 1; return; }

            byte[] buf = new byte[1048576];
            using (FileStream outFs = new FileStream(zipPath, FileMode.Create,
                                                     FileAccess.Write, FileShare.None))
            {
                for (int i = 0; i < n; i++)
                {
                    using (FileStream inFs = new FileStream(parts[i], FileMode.Open,
                                                            FileAccess.Read, FileShare.Read))
                    {
                        int read;
                        while ((read = inFs.Read(buf, 0, buf.Length)) > 0)
                            outFs.Write(buf, 0, read);
                    }
                }
            }
            if (new FileInfo(zipPath).Length != Total)
            {
                Error = "merged archive size mismatch";
                Result = 1;
                return;
            }
            Result = 0;
        }
        catch (Exception ex)
        {
            Error = ex.Message;
            Result = 1;
        }
        finally
        {
            Busy = false;
        }
    }

    // Shared state for the stall watchdog: if a connection stops delivering
    // bytes, the timer closes its stream so Read throws and the retry starts.
    class Stall
    {
        public Stream St;
        public DateTime Last;
    }

    static void Worker(object arg)
    {
        object[] a = (object[])arg;
        string url = (string)a[0];
        string path = (string)a[1];
        long start = (long)a[2];
        long end = (long)a[3];
        long want = end - start + 1;
        long have = File.Exists(path) ? new FileInfo(path).Length : 0;
        byte[] buf = new byte[262144];
        string lastError = null;

        for (int attempt = 1; attempt <= 4 && have < want && !Stop; attempt++)
        {
            Stall stall = new Stall();
            stall.Last = DateTime.Now;
            Timer watchdog = new Timer(delegate(object state)
            {
                Stall s = (Stall)state;
                if ((DateTime.Now - s.Last).TotalSeconds > 12 && s.St != null)
                {
                    try { s.St.Close(); } catch (Exception) { }
                }
            }, stall, 2000, 2000);

            try
            {
                HttpWebRequest req = (HttpWebRequest)HttpWebRequest.Create(url);
                req.Method = "GET";
                req.UserAgent = "bilibili-downloader-setup";
                req.AllowAutoRedirect = true;
                req.Timeout = 30000;
                req.ReadWriteTimeout = 25000;
                req.AddRange(start + have, end);

                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    Stream st = resp.GetResponseStream();
                    stall.St = st;
                    stall.Last = DateTime.Now;
                    using (st)
                    using (FileStream fs = new FileStream(path, FileMode.Append,
                                                          FileAccess.Write, FileShare.None))
                    {
                        while (have < want && !Stop)
                        {
                            int read = st.Read(buf, 0, buf.Length);
                            if (read <= 0) break;
                            if (read > want - have) read = (int)(want - have);
                            fs.Write(buf, 0, read);
                            have += read;
                            stall.Last = DateTime.Now;
                            Interlocked.Add(ref Done, (long)read);
                        }
                        fs.Flush();
                    }
                }
            }
            catch (Exception ex)
            {
                lastError = ex.Message;
                if (Stop) break;
            }
            finally
            {
                watchdog.Dispose();
            }
            if (have < want && !Stop) Thread.Sleep(700);
        }

        if (have < want && !Stop)
        {
            if (lastError == null) lastError = "part is short: " + have + " of " + want + " bytes";
            if (Error == null) Error = lastError;
        }
    }
}
'@
function Initialize-Downloader {
    if (([System.Management.Automation.PSTypeName]'FfDl').Type) { return }
    try {
        Add-Type -TypeDefinition $DownloaderCode -Language CSharp
    }
    catch {
        # PowerShell 7 marks ServicePointManager as obsolete (SYSLIB0014); it is
        # only needed on .NET Framework (the installer runs Windows PowerShell
        # 5.1), so drop that one line and compile again there.
        $fallback = $DownloaderCode -replace 'ServicePointManager\.DefaultConnectionLimit = 16;', ''
        Add-Type -TypeDefinition $fallback -Language CSharp
    }
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

# Multi-threaded download in its own window: total progress, total speed,
# thread count and a stop button. DoEvents keeps the window alive without a
# timer; the transfer itself runs on .NET threads inside FfDl.
function Invoke-ParallelDownload([string]$Target, [string]$ZipPath, [int]$Threads) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    # 150% 缩放时窗口被系统按位图拉伸的话，字会糊成一团毛边：
    # 先把本进程声明成 Per-Monitor V2，让 WinForms 自己按真实像素排版。
    Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class WinDpi{[DllImport("user32.dll")]public static extern bool SetProcessDpiAwarenessContext(System.IntPtr v);[DllImport("user32.dll")]public static extern uint GetDpiForSystem();}'
    try { [void][WinDpi]::SetProcessDpiAwarenessContext([IntPtr]-4) } catch { }

    # 缩放不是 100% 时，让控件按真实像素自己放大，而不是让 DWM 把整窗位图拉伸
    $sf = [single]1
    try {
        $sf = [single]([WinDpi]::GetDpiForSystem() / 96.0)
        if ($sf -lt 1) { $sf = [single]1 }
    } catch { }

    # GDI+ 兼容文本渲染（UseCompatibleTextRendering）的边缘是硬锯齿；关掉它走 GDI+Uniscribe 混合路径才有 ClearType
    try { [System.Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false) } catch { }

    # 配色：白底 + B 站粉，尽量贴近 Win11 的观感
    $pink  = [System.Drawing.Color]::FromArgb(251, 114, 153)
    $ink   = [System.Drawing.Color]::FromArgb(31, 35, 41)
    $muted = [System.Drawing.Color]::FromArgb(138, 144, 153)
    $edge  = [System.Drawing.Color]::FromArgb(217, 222, 229)

    $form = New-Object System.Windows.Forms.Form
    $form.Text = '下载 ffmpeg'
    $form.FormBorderStyle = 'FixedSingle'
    $form.StartPosition = 'CenterScreen'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true
    $form.ClientSize = New-Object System.Drawing.Size(520, 206)
    $form.BackColor = [System.Drawing.Color]::White
    $form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
    $form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::None

    $title = New-Object System.Windows.Forms.Label
    $title.Text = '正在获取文件信息…'
    $title.AutoSize = $true
    $title.Location = New-Object System.Drawing.Point(18, 18)
    $title.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 12.5, [System.Drawing.FontStyle]::Bold)
    $title.ForeColor = $ink
    $form.Controls.Add($title)

    # 副标题：线程数 / 总大小，信息量够但不去抢标题的注意力
    $sub = New-Object System.Windows.Forms.Label
    $sub.Text = '正在连接下载服务器…'
    $sub.AutoSize = $true
    $sub.Location = New-Object System.Drawing.Point(19, 53)
    $sub.ForeColor = $muted
    $form.Controls.Add($sub)

    # 自绘进度条：WinForms 自带的 ProgressBar 是 XP 时代的方块条，改手绘圆角胶囊
    $track = New-Object System.Windows.Forms.Panel
    $track.Location = New-Object System.Drawing.Point(18, 82)
    $track.Size = New-Object System.Drawing.Size(484, 12)
    $track.BackColor = [System.Drawing.Color]::White
    $track.Tag = [double]0
    $track.Add_Paint({
        param($sndr, $ev)
        $g = $ev.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $gw = [single]$sndr.Width
        $gh = [single]$sndr.Height
        $gr = [single]($gh / 2)
        $gp = New-Object System.Drawing.Drawing2D.GraphicsPath
        $gp.AddArc(0, 0, 2 * $gr, 2 * $gr, 180, 90)
        $gp.AddArc($gw - 2 * $gr, 0, 2 * $gr, 2 * $gr, 270, 90)
        $gp.AddArc($gw - 2 * $gr, $gh - 2 * $gr, 2 * $gr, 2 * $gr, 0, 90)
        $gp.AddArc(0, $gh - 2 * $gr, 2 * $gr, 2 * $gr, 90, 90)
        $gp.CloseFigure()
        $g.FillPath((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(238, 240, 243))), $gp)
        $ratio = [double]$sndr.Tag
        if ($ratio -gt 0) {
            $fw = [single]($gw * $ratio)
            $minw = [single](2 * $gh)
            if ($fw -lt $minw) { $fw = $minw }
            if ($fw -gt $gw) { $fw = $gw }
            $fp = New-Object System.Drawing.Drawing2D.GraphicsPath
            $fp.AddArc(0, 0, 2 * $gr, 2 * $gr, 180, 90)
            $fp.AddArc($fw - 2 * $gr, 0, 2 * $gr, 2 * $gr, 270, 90)
            $fp.AddArc($fw - 2 * $gr, $gh - 2 * $gr, 2 * $gr, 2 * $gr, 0, 90)
            $fp.AddArc(0, $gh - 2 * $gr, 2 * $gr, 2 * $gr, 90, 90)
            $fp.CloseFigure()
            $fb = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                (New-Object System.Drawing.Point(0, 0)),
                (New-Object System.Drawing.Point([int]$fw, 0)),
                [System.Drawing.Color]::FromArgb(251, 114, 153),
                [System.Drawing.Color]::FromArgb(255, 168, 194))
            $g.FillPath($fb, $fp)
            $fb.Dispose()
            $fp.Dispose()
        }
        $gp.Dispose()
    })
    $form.Controls.Add($track)

    $detail = New-Object System.Windows.Forms.Label
    $detail.Text = '正在连接下载服务器，请稍候…'
    $detail.AutoSize = $true
    $detail.Location = New-Object System.Drawing.Point(18, 101)
    $detail.ForeColor = $ink
    $form.Controls.Add($detail)

    $percent = New-Object System.Windows.Forms.Label
    $percent.Text = ''
    $percent.AutoSize = $false
    $percent.Size = New-Object System.Drawing.Size(120, 20)
    $percent.Location = New-Object System.Drawing.Point(382, 101)
    $percent.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
    $percent.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9, [System.Drawing.FontStyle]::Bold)
    $percent.ForeColor = $pink
    $form.Controls.Add($percent)

    $speed = New-Object System.Windows.Forms.Label
    $speed.Text = '总速度 0.0 MB/s'
    $speed.AutoSize = $true
    $speed.Location = New-Object System.Drawing.Point(18, 125)
    $speed.ForeColor = $muted
    $form.Controls.Add($speed)

    $hint = New-Object System.Windows.Forms.Label
    $hint.Text = '下载完成后自动继续安装'
    $hint.AutoSize = $true
    $hint.Location = New-Object System.Drawing.Point(18, 162)
    $hint.ForeColor = [System.Drawing.Color]::FromArgb(170, 176, 185)
    $form.Controls.Add($hint)

    $stopBtn = New-Object System.Windows.Forms.Button
    $stopBtn.Text = '停止'
    $stopBtn.Size = New-Object System.Drawing.Size(96, 32)
    $stopBtn.Location = New-Object System.Drawing.Point(406, 154)
    $stopBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $stopBtn.FlatAppearance.BorderSize = 1
    $stopBtn.FlatAppearance.BorderColor = $edge
    $stopBtn.FlatAppearance.MouseOverBackColor = $pink
    $stopBtn.BackColor = [System.Drawing.Color]::White
    $stopBtn.ForeColor = $ink
    $stopBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
    $form.Controls.Add($stopBtn)
    $form.AcceptButton = $stopBtn
    $stopBtn.Add_MouseEnter({ $stopBtn.ForeColor = [System.Drawing.Color]::White; $stopBtn.FlatAppearance.BorderColor = $pink })
    $stopBtn.Add_MouseLeave({ $stopBtn.ForeColor = $ink; $stopBtn.FlatAppearance.BorderColor = $edge })

    # Label 默认走 GDI+ 的 TextRenderer 之外那一套，字号小时边缘全是锯齿；
    # 逐个改回 GDI 文本渲染，字才有灰度抗锯齿。
    foreach ($c in $form.Controls) {
        if ($c -is [System.Windows.Forms.Label]) { $c.UseCompatibleTextRendering = $false }
    }

    # 控件坐标都是按 96 DPI 摆的，这里按真实缩放整体放大一次
    if ($sf -ne 1) {
        $form.Scale((New-Object System.Drawing.SizeF($sf, $sf)))
        $form.ClientSize = New-Object System.Drawing.Size([int](520 * $sf), [int](206 * $sf))
        # Scale() 只放大了控件框，字号还是 96 DPI 那套，得一起放大，不然字会显得瘪
        foreach ($c in $form.Controls) {
            try {
                $cf = $c.Font
                if ($cf) {
                    $c.Font = New-Object System.Drawing.Font($cf.FontFamily, [single]($cf.SizeInPoints * $sf), $cf.Style, $cf.Unit)
                }
            }
            catch { }
        }
    }
    $stopBtn.Add_Click({
        [FfDl]::Stop = $true
        $stopBtn.Enabled = $false
        $stopBtn.Text = '正在停止…'
        $stopBtn.FlatAppearance.MouseOverBackColor = $edge
    })

    # 先把窗口亮出来：抓远端大小可能要十几秒，不能让它看起来像卡死。
    # 安装器是用 SW_HIDE 起的进程，Windows 会把"首个窗口"按隐藏状态处理，
    # 所以 Show() 之后还要用 ShowWindow(SW_SHOW) 强制显示一次。
    $form.Show()
    Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class WinShow{[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h,int n);}'
    [void][WinShow]::ShowWindow($form.Handle, 5)
    $form.Activate()
    [System.Windows.Forms.Application]::DoEvents()

    $meta = Get-RemoteMeta $Target
    [int64]$total = $meta.Length
    $useRanges = [bool]$meta.Ranges
    if (-not $useRanges) { $Threads = 1 }
    if ($Threads -lt 1) { $Threads = 1 }
    if ($Threads -gt 16) { $Threads = 16 }

    Initialize-Downloader

    $work = Join-Path $env:TEMP ('bili_dl_' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work -Force | Out-Null

    $title.Text = '正在下载 ffmpeg'
    $sub.Text = ('{0} 线程并行 · 共 {1} · 断了会自己续传' -f $Threads, (Format-Mb $total))
    $detail.Text = ('0.0 MB / {0}' -f (Format-Mb $total))
    $percent.Text = '0%'
    $speed.Text = '总速度 0.0 MB/s'
    $track.Tag = [double]0
    $track.Invalidate()
    [System.Windows.Forms.Application]::DoEvents()

    [FfDl]::Begin($Target, $total, $work, $ZipPath, $Threads, $useRanges)

    [int64]$lastDone = 0
    $lastTick = [DateTime]::UtcNow
    [double]$rate = 0

    try {
        while ([FfDl]::Busy) {
            [System.Windows.Forms.Application]::DoEvents()

            [int64]$done = [FfDl]::Done
            if ($done -gt $total) { $done = $total }
            $now = [DateTime]::UtcNow
            if (($now - $lastTick).TotalMilliseconds -ge 300) {
                $secs = ($now - $lastTick).TotalSeconds
                if ($secs -gt 0) {
                    $instant = ($done - $lastDone) / $secs
                    if ($instant -ge 0) {
                        if ($rate -le 0) { $rate = $instant }
                        else { $rate = $rate * 0.6 + $instant * 0.4 }
                    }
                }
                if ($rate -lt 0) { $rate = 0 }
                $pct = 0
                if ($total -gt 0) { $pct = [int][Math]::Floor($done * 100 / $total) }
                if ($total -gt 0) { $track.Tag = [double]($done / $total) }
                $track.Invalidate()
                $detail.Text = ('{0} / {1}' -f (Format-Mb $done), (Format-Mb $total))
                $percent.Text = ('{0}%' -f $pct)
                $eta = ''
                # 速度已经掉到 0 的时候别拿它算剩余时间，否则会冒出"剩余 86 分 41 秒"这种鬼话
                if ($rate -ge 102400 -and $total -gt $done) {
                    $left = [int][Math]::Ceiling(($total - $done) / $rate)
                    if ($left -ge 60) { $eta = (' · 剩余约 {0} 分 {1} 秒' -f [int]($left / 60), ($left % 60)) }
                    else { $eta = (' · 剩余约 {0} 秒' -f $left) }
                }
                if ([FfDl]::Stop) {
                    $speed.Text = '已停止，正在收尾…'
                }
                else {
                    $speed.Text = ('总速度 {0}/s{1}' -f (Format-Mb $rate), $eta)
                }
                $lastDone = $done
                $lastTick = $now
            }
            Start-Sleep -Milliseconds 60
        }
    }
    finally {
        $form.Close()
        $form.Dispose()
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }

    if ([FfDl]::Result -eq 3) { return 3 }
    if ([FfDl]::Result -ne 0) {
        $why = [FfDl]::Error
        if (-not $why) { $why = 'download failed' }
        throw $why
    }
    return 0
}

# Same downloader without a window: used by -Mode Install (plain CLI installs)
# so a command-line run never pops a GUI.
function Invoke-SilentDownload([string]$Target, [string]$ZipPath, [int]$Threads) {
    $meta = Get-RemoteMeta $Target
    Initialize-Downloader
    $work = Join-Path $env:TEMP ('bili_dl_' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work -Force | Out-Null
    try {
        [FfDl]::Begin($Target, $meta.Length, $work, $ZipPath, $Threads, [bool]$meta.Ranges)
        while ([FfDl]::Busy) { Start-Sleep -Milliseconds 150 }
        if ([FfDl]::Result -ne 0) {
            $why = [FfDl]::Error
            if (-not $why) { $why = 'download failed' }
            throw $why
        }
    }
    finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

try {
    if (-not $Dest) { $Dest = Join-Path $env:USERPROFILE 'ffmpeg' }

    if ($Mode -eq 'Url') {
        Write-Out (Resolve-Url)
    }
    elseif ($Mode -eq 'Size') {
        $meta = Get-RemoteMeta (Resolve-Url)
        Write-Out ([string]$meta.Length)
    }
    elseif ($Mode -eq 'Download') {
        if (-not $Zip) { throw 'no -Zip given' }
        $code = Invoke-ParallelDownload (Resolve-Url) $Zip $Threads
        if ($code -eq 3) { Write-Out 'STOPPED'; exit 3 }
        if (-not (Test-Path -LiteralPath $Zip)) { throw 'archive was not written' }
        Write-Out 'OK'
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
        $tmp = Join-Path $env:TEMP ('bili_ffmpeg_' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        try {
            $zipFile = Join-Path $tmp 'ffmpeg.zip'
            Invoke-SilentDownload (Resolve-Url) $zipFile $Threads
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
    $why = [string]$_.Exception.Message
    if ($why.Length -gt 120) { $why = $why.Substring(0, 120) + '…' }
    Write-Out ('ERR: ' + $why)
    exit 1
}
