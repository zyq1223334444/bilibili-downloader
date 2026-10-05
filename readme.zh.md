> [🇬🇧 English](readme.md)

# bilibili-downloader

B 站视频 / 分P / 合集下载器 —— DASH 音视频分流下载，再用 ffmpeg 合并成 MP4 并导出 MP3。

---

## 功能特性

- **单视频 / 多P（分P）/ 合集一次下全** —— 给一个链接就够，自动展开。
- **默认取最高可用画质**（8K / 4K / HDR / 杜比视界，以账号权限为准），可用 `-q` 限制上限。
- **音频优先无损**：`dash.flac`（Hi-Res）→ 杜比全景声 → 最高码率，再导出 MP3。
- **同时产出 MP4 与 MP3**：MP4 用 `-c copy -movflags +faststart` 合并（不重新编码、秒级完成、可在线拖进度）。
- **多线程下载 + 每线程一条进度条**：合集/多P 时默认 **4 个文件同时下**，终端底部就是 4 行实时状态，每行直接写明**是哪个视频的哪条流**（如 `[11/22] #43 逃离棋盒 · 1080P 视频流`）；此时不再逐项打印标题行，日志里只留 `[完成] / [失败] / [跳过]`，看得更清楚。进度条按**终端实际宽度**自适应：窗口越宽进度条越长；标题按宽度预算截断（极窄时先丢掉"第几个/共几个"），保证百分比/大小/速度不会被挤掉。输出被重定向时自动改成"每 15 秒一行"。
- **慢速连接自动重连**：某条流的速度掉到**它自身历史平均**（从开始下载到 10 秒前）的 **30% 以下并持续 10 秒**，就丢掉这条连接、换个 CDN 节点用 `Range` 续传，进度不丢（默认最多 5 次，`--max-reconnects 0` 关闭）。**若按当前速度算出的预计剩余时间不足 10 秒，则保持连接继续下完**，不做无谓重连。
- **下载很抗折腾**：CDN 节点优选、每节点多次重试 + 退避、HTTP Range 断点续传、大小完整性校验。
- **原子写入**：所有产物先写 `.part`，成功才改名 —— 失败绝不会留下半个文件毁掉旧文件。
- **可重复执行**：已下载的自动跳过；失败的保留 `.m4s` 流文件，重跑即续传而不是从头再来。
- **WBI 接口签名**，签名失败自动回退旧接口。
- **SESSDATA 只问一次**：存进 Windows 用户环境变量，源码里永远不留凭证。
- **目录自动整理**：文件名清洗、Windows 保留名避让、超长路径自动缩短（补短哈希防重名）。
- `--dry-run` 先看计划；退出码规范（`0` 成功 / `1` 有失败 / `2` 参数错误 / `130` 中断）。
- **真正可非交互**：加 `-y` 或把输出重定向后，**即使在一台没有凭证的新机器上也不会停下提问**
  （旧版这里会用 `getpass` 直接打开 `/dev/tty`，把 stdin 重定向也拦不住，CI/批处理会永久挂住）。
- **跨平台**：Windows / Linux / macOS 同一份源码；凭证在 Windows 存用户环境变量，其他平台存
  `~/.config/bilibili-downloader/sessdata`（权限 600）。

## 环境要求

| 项目 | 说明 |
|---|---|
| Python | 3.9 及以上 |
| 依赖库 | `pip install -r requirements.txt`（requests、tqdm） |
| ffmpeg | 必须在 `PATH` 中：`choco install ffmpeg` / `scoop install ffmpeg` / `brew install ffmpeg` / `sudo apt install ffmpeg` |

### 方式一：安装包（Windows，推荐）

到 [Releases](https://github.com/zyq1223334444/bilibili-downloader/releases) 下载
**`bilibili_downloader_setup_1.0.0.exe`** 双击安装：

- 装到 `C:\Program Files\bilibili-downloader`，带开始菜单快捷方式、**卸载程序**（"设置 → 应用"里也能卸载）
- 可选把安装目录加入系统 `PATH`（默认勾选），之后任意终端直接敲 `bilibili_downloader`；
  卸载时会把 `PATH` **逐字节还原**（安装前会先把原值备份进注册表）
- 安装结束会检查 `PATH` 里有没有 ffmpeg，没有就提示安装命令

### 方式二：免安装（Windows 单文件 / 压缩包）

| 下载 | 形态 | 实测启动 | Ctrl+C 退出码 |
|---|---|---|---|
| `bilibili_downloader.exe` | 单文件（约 11 MB） | ≈0.9 s（每次要自解压） | `0xC000013A`（见下方说明） |
| `bilibili_downloader_standalone_win64.zip` | 解压出一个文件夹 | ≈0.3 s | **130**，与源码版一致 |

```powershell
.\bilibili_downloader.exe BV1xx411c7mD -q 720p --no-mp3
.\bilibili_downloader.exe --dry-run BV1xx411c7mD
```

> **单文件版的已知差异**：`--onefile` 在真正的程序外面还套了一层自解压引导进程。按 Ctrl+C 时控制台事件
> 同时送达两者，引导进程先退出，于是命令行看到的退出码是 `0xC000013A`（显示为 `-1073741510`）而不是 130。
> 程序本身依然正常收尾：打印 `[中断]`、保留 `.part` 断点、不留残余进程、临时目录清理干净——**只有退出码不同**。
> 脚本里要判断 130 的话请用 standalone 版，或把 `0xC000013A` 一并当作"已中断"。

### 方式三：Linux / macOS

| 平台 | 单文件 | 文件夹版（含可执行权限，推荐） |
|---|---|---|
| Linux x86_64 | `bilibili_downloader_linux_x86_64` | `bilibili_downloader_linux_x86_64.tar.gz` |
| macOS Intel | `bilibili_downloader_macos_x86_64` | `bilibili_downloader_macos_x86_64.tar.gz` |
| macOS Apple Silicon | `bilibili_downloader_macos_arm64` | `bilibili_downloader_macos_arm64.tar.gz` |

```bash
tar -xzf bilibili_downloader_linux_x86_64.tar.gz
./bilibili_downloader_standalone/bilibili_downloader BV1xx411c7mD --single -q 720p
```

> macOS 上是**未签名**的二进制，首次运行可能被 Gatekeeper 拦下：
> `xattr -d com.apple.quarantine <文件>`，或右键 → 打开。
> Linux / macOS 的二进制由 GitHub Actions 在**真机**上构建（见 `.github/workflows/build.yml`），
> 因为 Nuitka 把 Python 编译成 C 后要调用目标平台自己的链接器，**不支持交叉编译**。
> 想自己构建：`bash build/build_unix.sh`（Linux 需要 gcc / patchelf）。

三种形态都由 Nuitka 把 Python **编译成 C 再链接**而成，已内置 Python 运行时与 `requests` / `tqdm`，
**唯一还需要的外部程序是 ffmpeg**（必须在 `PATH` 中：`choco install ffmpeg` / `brew install ffmpeg` /
`sudo apt install ffmpeg`）。

参数、保存结构、凭证读取顺序都与源码版一致（其中"程序目录下的 `sessdata.txt`"对二进制而言就是**它旁边**那个文件）。

## 快速开始

```powershell
pip install -r requirements.txt

# 单个视频 → .\bili_downloads\<视频标题>\<视频标题>.mp4 与 .mp3
python bilibili_downloader.py BV1xx411c7mD

# 多P视频只下第 2 个分P
python bilibili_downloader.py "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single

# 只看看会下载什么，不真的下
python bilibili_downloader.py BV1xx411c7mD --dry-run

# 限制画质、不要 MP3、换保存目录
python bilibili_downloader.py BV1xx411c7mD -q 720p --no-mp3 -o D:\videos

# 只要音频，码率 192k
python bilibili_downloader.py BV1xx411c7mD --audio-only --mp3-bitrate 192
```

**首次运行**若没检测到凭证，脚本会打印获取方法并询问一次 `SESSDATA`（输入不回显），
校验通过后自动保存到 Windows 用户环境变量 `BILI_SESSDATA`。之后**新开一个终端窗口**运行即可自动读取，不用再输入。

### 多项目时选择下载范围

合集/多P 会先列出编号清单，然后询问要下哪些：

```
共 54 项。回车 / y = 全部下载，n = 不下载，也可只下部分（如 1,3,5,6-20）：
> 1,3,5,6-20
[选择] 已选 20/54 项：1,3,5-6,6-20
```

| 输入 | 效果 |
|---|---|
| 回车、`y`、`yes`、`all` | 全部下载 |
| `n`、`no`、`q` | 不下载，直接退出（退出码 0） |
| `1,3,5,6-20` | 只下这些：支持区间 `6-20`、重复项、空项（`1,,3`）、全角逗号 `1，3`，顺序自动整理 |
| `20-6` | 区间写反也认，等价于 `6-20` |
| 非法输入（如 `abc`、`0`、`99`） | 提示原因后重问，连续 3 次无效则取消 |

选完后回显 `[选择] 已选 N/总数 项：1,3,5-8`；下载时的 `[3/20]` 是"正在下第 3 个"，行首 `#5` 是**清单里的原始序号**，方便和上面列表对照。

> 非交互场景（输出被重定向、或加了 `-y`）不会询问，直接全部下载 —— 保持脚本/CI 可用。
> 单个视频/单个分P 也不会询问（没什么可选）。

## 保存结构

```
bili_downloads\
├── <视频标题>\                         # 单视频（两层）
│   ├── <视频标题>.mp4
│   └── <视频标题>.mp3
├── <视频标题>\                         # 多P视频（三层，P 序号保证顺序）
│   ├── P01 <分P标题>\
│   │   ├── P01 <分P标题>.mp4
│   │   └── P01 <分P标题>.mp3
│   └── P02 <分P标题>\……
└── <合集标题>\                         # 合集（三层）
    ├── <视频标题>\
    │   ├── <视频标题>.mp4
    │   └── <视频标题>.mp3
    └── <视频标题>\P01 <分P标题>\……      # 合集里又有多P视频时（四层）
```

## 参数一览

| 参数 | 默认 | 说明 |
|---|---|---|
| `inputs` | 交互输入 | 一个或多个：视频链接 / `BV` 号 / `av` 号 / `b23.tv` 短链 |
| `-o, --output` | `./bili_downloads` | 保存根目录 |
| `-q, --quality` | `max` | 画质上限：`max 8k 4k 1080p60 1080p+ 1080p 720p60 720p 480p 360p` |
| `--mp3-bitrate` | `320` | MP3 码率：`128 / 192 / 256 / 320` |
| `--audio-only` | 关 | 只导出 MP3（不下载视频流） |
| `--no-mp3` | 关 | 只保存 MP4 |
| `--single` | 关 | 只下输入链接指向的那一个视频/分P，忽略合集 |
| `-j, --jobs` | `4` | 并发线程数（最多 4），每个线程一条进度条 |
| `--max-reconnects` | `5` | 单个流因"速度掉到历史平均 30% 以下"而重开连接的次数上限（`0` = 关闭该检测） |
| `--force` | 关 | 已存在也重新下载 |
| `--no-probe` | 关 | 关闭节点优选探测 |
| `--retries` | `2` | 每个节点重试次数 |
| `--timeout` | `15` | 网络超时（秒） |
| `--reset-sessdata` | 关 | 忽略已保存凭证，重新输入（换号或过期时用） |
| `--dry-run` | 关 | 只列出计划，不下载 |
| `-y, --yes` | 关 | 不询问，直接全部下载（跳过范围选择与凭证重输） |

## SESSDATA 凭证

**读取顺序**：① 当前进程的环境变量 `BILI_SESSDATA` → ② **Windows 注册表里的用户环境变量**（直查 `HKCU\Environment`）
→ ③ 程序目录下的 `sessdata.txt`（源码版=脚本所在目录，exe 版=exe 所在目录）→ ④ `~/.config/bilibili-downloader/sessdata`。
都没有就会询问一次；Windows 下保存到用户环境变量（并同步当前进程），其他系统写入配置文件（权限 600）。

> 为什么要直查注册表：Windows 只在**进程启动那一刻**注入环境变量，已经开着的终端（尤其常驻的终端/服务进程）
> 拿到的是旧快照，于是会出现"明明设置成功了，脚本却说没检测到"。直查注册表后，旧终端里运行同样能读到。

**启动时会用 `nav` 接口校验一次凭证**：

| 结果 | 表现 |
|---|---|
| 有效 | 打印 `[凭证] 校验通过（普通账号 / 大会员）`，顺便说明你的画质权限 |
| 失效 | 打印 `[!] 凭证已失效……只能以游客身份下载，一般最高 480P/360P`，并提示怎么换；交互式终端里会直接问"现在重新输入 SESSDATA？"（答 Y 当场输入，只给一行极简提示） |
| 网络不可用 | 跳过校验，按原样使用 |

> 以前凭证失效会**静默降级**到 480P，看起来像"脚本坏了"；现在会直接告诉你原因。
> 需要完全非交互（脚本/CI，或输出重定向）时不会提问；加 `-y` 也不会问。

手动设置（PowerShell，永久生效）：

```powershell
setx BILI_SESSDATA "你的SESSDATA值"
```

获取方法：浏览器登录 B 站 → 按 `F12` → **Application** → **Cookies** → 选 `https://www.bilibili.com`
→ 复制名为 `SESSDATA` 的值。

查看 / 删除：

```powershell
[Environment]::GetEnvironmentVariable('BILI_SESSDATA','User')     # 查看（会打印明文，注意旁边有没有人）
Remove-ItemProperty -Path 'HKCU:\Environment' -Name 'BILI_SESSDATA'   # 删除
```

> ⚠️ `SESSDATA` 等同于账号登录凭证：不要写进源码、不要提交仓库、不要发给别人。
> 一旦怀疑泄露，立刻到 B 站「设置 → 安全隐私 → 退出所有设备」使旧凭证失效。

## 断点续传与失败处理

- **随时 Ctrl+C 都安全且立刻生效**：主线程每 0.3 秒检查一次信号，收到就通知下载线程收手并**立即退出**（不会等卡住的线程或 ffmpeg），不打印 traceback，退出码固定为 130；已下载的 `.part` / `.m4s` 都会保留，重跑即续传。
- 视频/音频先下载到 `<名字>.video.m4s.part` / `<名字>.audio.m4s.part`；重跑时用 `Range` 从已有字节数继续。
- 成功后改名为 `.m4s` → 合并 → 导出 → **删除**临时流文件。
- 失败时**保留**这些文件，因此重新执行同一条命令是"续传"而不是"从头下载"。
- 实际字节数与 `Content-Length` / `Content-Range` 不一致时判为失败并重试，避免用被截断的文件去合并。
- 若本地残留与远端不一致会返回 `416`，此时自动清除断点重新下载。

### 输出里的状态标记

| 标记 | 含义 |
|---|---|
| `[跳过]` | 已有缓存 / 成品已存在，不重复下载 |
| `[重试]` | 某节点某次尝试失败，并说明下一步：**同一节点重试** / **换下一个节点** / **已无可用节点** |
| `[重连]` | 速度掉到自身历史平均的 30% 以下并持续 10 秒：丢掉这条连接、换个节点用 Range 续传（若预计剩余时间不足 10 秒则不动，继续下完） |
| `[成功]` | 中间失败过、但最终成功（一切顺利时不播报，避免刷屏） |
| `[失败]` | 该项目彻底失败（所有节点都试过），整批退出码会变成 1 |
| `[完成]` | 产出的成品文件，带大小 |
| `[结果]` | 整批统计与失败明细 |
| `[中断]` | 你按了 Ctrl+C（退出码 130） |

网络错误会被压成一行可读文本（不再打印嵌套异常的原始元组）：

```
视频流：[重试] 节点 1/3 第 1 次失败（远程主机强迫关闭了一个现有的连接。（ConnectionResetError 10054））→ 换下一个节点
视频流：[成功] 第 2 个节点第 1 次尝试成功（191.4 MB，用时 42s）
#2 [完成] P02 空月之歌 第一幕 雪浪与苍林之舞（2）.mp4（191.4 MB）
```

> 关键：**看到 `[重试]` 不等于失败** —— 结论看这一行的结尾（换下一个节点 / 已无可用节点）和紧随其后的 `[成功]` / `[失败]`。

## 常见问题

| 现象 | 说明 |
|---|---|
| `未找到 ffmpeg` | 安装 ffmpeg 并加入 `PATH` |
| 只能下 360P/480P | 没设置有效 `SESSDATA`，或账号本身没有该画质 |
| `该视频没有 DASH 流` | 番剧/影视内容（本工具只支持普通投稿），或极老视频 |
| `这是番剧/影视内容` | 接口返回了 `redirect_url`，ep/番剧不在支持范围内 |
| `code=62002 / 62004` | 稿件不可见 / 审核中 |
| `《…》是付费合集` | 付费合集无法下载 |
| 进度长时间不动 | 换节点中；脚本正在重试+退避，看那一行"节点 x/y 第 n 次失败"即可 |

## 仓库结构

仓库里放的是**程序本身**和**构建它的手段**；构建**产出**的东西全部集中在一个被忽略的目录里，
所以 clone 下来永远是干净的：

```
bilibili_downloader.py      整个程序（单文件）
requirements.txt            运行时依赖（requests、tqdm）
readme.md / readme.zh.md    本文档
LICENSE
.github/workflows/build.yml CI：Linux + 两个 macOS 架构
build/                      构建工具（属于仓库内容）
├── build_exe.bat             Windows 单文件 exe
├── build_exe_standalone.bat  Windows 文件夹版 + zip
├── build_installer.bat       Windows 安装包（调用 installer.iss）
├── build_unix.sh             Linux / macOS 二进制
├── installer.iss             Inno Setup 脚本
├── ChineseSimplified.isl     安装包的中文文案
└── out/                      被忽略：全部产物与 Nuitka 中间目录
```

本仓库的 `.gitignore` 在这里只排除 `build/out/` 一项。脚本本身是提交进仓库的，
所以任何人 clone 之后都能自己重新编译出这些二进制。

## 从源码构建（Nuitka）

| 想要什么 | 在哪构建 | 命令 |
|---|---|---|
| Windows 单文件 exe | Windows | `build\build_exe.bat` → `build\out\bilibili_downloader.exe` |
| Windows 文件夹版 | Windows | `build\build_exe_standalone.bat` → 文件夹 + zip，都在 `build\out\` |
| Windows 安装包 | Windows | `build\build_installer.bat`（需要 Inno Setup 6.5+） |
| Linux / macOS 二进制 | **对应平台**（WSL / Mac / CI） | `bash build/build_unix.sh` → `build/out/dist_unix/` |

脚本会自己算出仓库根目录，因此在任何工作目录下都能直接运行，且只往 `build/out/` 里写东西。

环境要求：`pip install -r requirements.txt nuitka zstandard`，Windows 上还需要 **MSVC 14.3+**
（Visual Studio 2022 Build Tools 或更新版本）——Nuitka 在 Python 3.13 及以上**不能用 MinGW**。
三个值得知道的参数（都是实测踩出来的，完整说明在脚本注释里）：

- `VSLANG=1033` —— Nuitka 的 Scons 后端用 `mbcs` 代码页解码 `cl.exe` 输出，中文版 Visual Studio
  会让构建抛 `UnicodeDecodeError`，强制英文消息即可绕过。
- `--include-package-data=certifi` —— `requests` 用 certifi 的 `cacert.pem` 校验 TLS，那是数据文件而非代码。
  没有它 exe 能启动，但每次 HTTPS 请求都会报
  *"Could not find a suitable TLS CA certificate bundle"*。
- `--windows-console-mode=force` —— 这是个控制台工具，不加这个参数会变成没有 stdout 的 GUI 子系统程序。

安装包用 **Inno Setup 6.5+** 编译：`winget install --id JRSoftware.InnoSetup -e`。
它在 `[Code]` 里先把系统 `PATH` 原值备份进注册表再修改，卸载时逐字节还原；
安装结束时若 `PATH` 里没有 ffmpeg 会给出提示。

**ffmpeg 从不打包进去** —— 它是约 100 MB 的外部程序，运行时通过 `shutil.which("ffmpeg")` 查找，
所以每个平台都得单独安装。

> **为什么 Linux/macOS 不能在 Windows 上编**：Nuitka 把 Python 编译成 C，然后调用**目标平台自己的**
> 编译器/链接器，没有交叉编译。本仓库用 GitHub Actions 在真机上构建 Linux 与两个 macOS 架构，
> 见 `.github/workflows/build.yml`。

## 实现要点（给想读代码的人）

- **DASH 分流**：B 站把高清画面与声音分成两条流，本工具分别下载后用 `-c copy` 只换封装、不重编码，
  所以合并是秒级的；`+faststart` 把索引挪到文件头，网页/播放器可立即拖动进度。
- **WBI 签名**：`w_rid = md5(排序后的查询串 + "&wts=时间戳" + mixin_key)`，其中 `mixin_key` 由
  `nav` 接口返回的 `img_url` / `sub_url` 经 64 项置换表重排得到；签名接口失败自动回退非签名接口。
- **节点优选**：对 `baseUrl` 与所有 `backupUrl` 并发 `HEAD`，谁先回应成功用谁（比延迟，不比带宽）。
- **原子写入**：`os.replace()` 在同一目录内改名在 Windows 与 POSIX 上都是原子操作。
- **Ctrl+C 响应**：主线程用 `futures.wait(timeout=0.3)` **轮询**，而不是 `as_completed` 的无限等待 —— 在 Windows 上主线程卡在无限等待里无法处理挂起的信号，表现就是"按了 Ctrl+C 没反应"；确认中断后用 `os._exit(130)` 立即退出，不再等非守护的下载线程。
- **并发/进度条**：`ThreadPoolExecutor` 最多 4 线程，各线程负责一个视频（其视频流与音频流仍在该线程内串行）；进度条用 `tqdm(position=线程槽位)` 堆叠，因此 4 线程就是 4 条互不覆盖的进度条，普通输出统一走 `tqdm.write`（它会先清行再重画，不会踩坏进度条）；playurl 调用加锁串行化并保持 0.5 秒最小间隔；探测另用临时线程池。

## 合规声明

仅供个人学习与备份自己有权访问的内容。请遵守 B 站用户协议，不要二次传播受版权保护的内容，
也不要用于批量抓取。
