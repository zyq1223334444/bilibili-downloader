#!/usr/bin/env python3
r"""
B 站视频 / 分P / 合集 下载器（DASH 分流下载 + ffmpeg 合并）

依赖：
    pip install -r requirements.txt        # requests, tqdm
    系统需安装 ffmpeg 并加入 PATH

登录凭证（可选，用于 1080P+ / 4K / 8K / 无损音频）：
    读取顺序：① 环境变量 BILI_SESSDATA  ② 脚本目录下的 sessdata.txt 或 ~/.config 下的副本
    都没读到时会**交互式询问一次**（输入不回显），校验后自动保存到 Windows 用户环境变量，
    下次运行会直接读取（也会直查注册表，所以旧终端窗口同样有效）。
    启动时会校验凭证：失效会明确提示，并可直接回车前的 [Y/n] 当场重新输入。
    更换账号或凭证过期：加 --reset-sessdata 重新输入。
    手动设置（PowerShell，永久）：setx BILI_SESSDATA "你的SESSDATA"
    获取方法：浏览器登录 B 站 → F12 → Application → Cookies → bilibili.com → 复制 SESSDATA
    ⚠️ SESSDATA 等同账号登录凭证：不要写进源码、不要提交仓库、不要发给别人。
       一旦怀疑泄露，立刻到 B 站「设置 → 安全隐私 → 退出所有设备」使旧凭证失效。

保存结构：
    单视频      bili_downloads\<视频标题>\<视频标题>.mp4 / .mp3
    多P视频     bili_downloads\<视频标题>\P01 <分P标题>\P01 <分P标题>.mp4 / .mp3
    合集        bili_downloads\<合集标题>\<视频标题>\<视频标题>.mp4 / .mp3
    合集内的多P bili_downloads\<合集标题>\<视频标题>\P01 <分P标题>\P01 <分P标题>.mp4

用法：
    python bilibili_downloader.py BV1xx411c7mD
    python bilibili_downloader.py "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --single
    python bilibili_downloader.py BV1xx411c7mD --dry-run          # 只看将要下载什么
    python bilibili_downloader.py BV1xx411c7mD -q 720p --no-mp3
    python bilibili_downloader.py BV1xx411c7mD -j 4                # 4 个文件同时下（默认）
    python bilibili_downloader.py BV1xx411c7mD -j 1                # 串行，显示实时进度条
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed
from concurrent.futures import wait as futures_wait
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:  # 依赖缺失时给出人话提示，而不是一堆 traceback
    import requests
    from requests.adapters import HTTPAdapter
    from tqdm import tqdm
    from urllib3.util.retry import Retry
except ImportError as exc:  # pragma: no cover
    sys.exit(f"缺少依赖：{exc}\n请先执行：pip install -r requirements.txt")

# ================= 常量 =================

API_VIEW = "https://api.bilibili.com/x/web-interface/view"
API_VIEW_WBI = "https://api.bilibili.com/x/web-interface/wbi/view"
API_PLAYURL = "https://api.bilibili.com/x/player/playurl"
API_PLAYURL_WBI = "https://api.bilibili.com/x/player/wbi/playurl"
API_NAV = "https://api.bilibili.com/x/web-interface/nav"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# WBI 签名用的混淆表（来自 B 站 web 端实现，顺序不可改）
MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62,
    11, 36, 20, 34, 44, 52,
)

# 画质 id（B 站返回值）→ 人话
QUALITY_NAMES = {
    127: "8K 超高清", 126: "杜比视界", 125: "HDR 真彩", 120: "4K 超清",
    116: "1080P60", 112: "1080P+", 80: "1080P 高清", 74: "720P60",
    64: "720P 高清", 32: "480P 清晰", 16: "360P 流畅",
}

# --quality 可选值 → 允许的最高画质 id
QUALITY_LIMITS = {
    "max": 127, "8k": 127, "4k": 120, "1080p60": 116, "1080p+": 112,
    "1080p": 80, "720p60": 74, "720p": 64, "480p": 32, "360p": 16,
}

# DASH 音频流 id：30251 = Hi-Res 无损，30250 = 杜比全景声
AUDIO_LOSSLESS_IDS = {30251}

WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

CHUNK_SIZE = 256 * 1024
NAME_LIMIT = 60          # 单个目录/文件名最长字符数

# ---- 慢速连接检测：速度掉到"自身历史平均"的 30% 以下并持续 10 秒 → 丢掉连接、重开一条续传 ----
SLOW_CHECK_INTERVAL = 0.5          # 采样/判定的间隔（秒）
SLOW_CUR_WINDOW = 6.0              # "当前速度"的统计窗口（秒）
SLOW_REF_LAG = 10.0                # 参考速度 = 从开始到（此刻 - 该值）的平均速度
SLOW_RATIO = 0.30                  # 当前速度低于参考速度的该比例即视为变慢
SLOW_HOLD = 10.0                   # 变慢需持续这么久才动手
SLOW_MIN_ELAPSED = 20.0            # 至少已下载这么久才开始判定（参考滞后 + 持续时长）
SLOW_MIN_REF = 256 * 1024          # 参考速度低于此值说明本来就慢，重连也没意义
SLOW_MIN_ETA = 10.0                # 预计剩余时间小于该值（秒）就继续下，别重连
DEFAULT_MAX_RECONNECTS = 5         # 单个流最多因"变慢"重开几次连接
PATH_LIMIT = 235         # Windows 整条路径的安全上限（MAX_PATH=260，留出余量）
PART_SUFFIX = ".part"

ENV_NAME = "BILI_SESSDATA"


def _app_dir() -> Path:
    """程序所在目录：源码运行时是脚本目录，打包成 exe 后是 exe 所在目录。

    单文件打包（Nuitka onefile / PyInstaller）会把 __file__ 指向每次运行都不同的
    临时解包目录，如果直接拿它拼 sessdata.txt，用户放在 exe 旁边的凭证文件永远读不到。
    """
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        try:
            return Path(sys.argv[0]).resolve().parent
        except OSError:
            pass
    return Path(__file__).resolve().parent


SESSDATA_FILE = _app_dir() / "sessdata.txt"
SESSDATA_HOME_FILE = Path.home() / ".config" / "bilibili-downloader" / "sessdata"


class DownloadError(RuntimeError):
    """本项目所有可预期的错误（网络、接口、ffmpeg、文件系统）。"""


class Aborted(Exception):
    """用户中断（Ctrl+C）：下载线程看到它就地收手，不计入失败。"""


class SlowConnection(RuntimeError):
    """连接速度长期远低于自身历史平均：应当丢掉这条连接、重开一条续传。"""


# 中断标志：Ctrl+C 时置位，下载循环每收到一块数据就检查一次，因此能秒级停下
_ABORT = threading.Event()

# 接口调用串行化 + 最小间隔，避免多线程同时打接口触发风控
_API_LOCK = threading.Lock()
_API_MIN_INTERVAL = 0.5
_last_api_call = 0.0


def _throttle_api() -> None:
    global _last_api_call
    with _API_LOCK:
        wait = _API_MIN_INTERVAL - (time.time() - _last_api_call)
        if wait > 0:
            time.sleep(wait)
        _last_api_call = time.time()


def request_abort() -> None:
    """请求停止下载（Ctrl+C 时由主线程调用）。"""
    _ABORT.set()


def _abortable_sleep(seconds: float) -> None:
    """可被 Ctrl+C 立即打断的等待：_ABORT 一旦置位就马上返回（而不是傻等）。"""
    if _ABORT.wait(seconds):
        raise Aborted("已取消")


def _hard_exit(code: int) -> None:
    """立即结束进程，不再等待下载线程。

    被打断时工作线程可能正卡在 socket 读、重试退避或 ffmpeg 上；如果等它们收尾，
    Ctrl+C 就会变成几秒到几十秒的"没反应"。下载产物都是 .part + 可续传的，
    直接退出是安全的（下次运行会接着下）。测试里会替换这个函数。
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)


# ---- 多线程进度条：每个下载线程固定占用一条进度条（position），4 线程 = 4 条 ----
_SLOT_LOCK = threading.Lock()
_SLOT_COUNTER = 0
_SLOT_LOCAL = threading.local()
_bars_active = threading.Event()


def _reset_progress() -> None:
    global _SLOT_COUNTER
    _SLOT_COUNTER = 0
    _bars_active.clear()


def _claim_bar_slot() -> int:
    """给当前线程分配固定的进度条位置：同线程复用，不同线程互不冲突。"""
    global _SLOT_COUNTER
    slot = getattr(_SLOT_LOCAL, "slot", None)
    if slot is None:
        with _SLOT_LOCK:
            slot = _SLOT_COUNTER
            _SLOT_COUNTER += 1
        _SLOT_LOCAL.slot = slot
    return slot


def emit(message: str = "", *, err: bool = False) -> None:
    """统一输出。

    进度条激活时必须走 tqdm.write：它会先清掉自己那几行、写完再重画，
    否则普通 print 会把进度条踩花。
    """
    stream = sys.stderr if err else sys.stdout
    if _bars_active.is_set():
        tqdm.write(message, file=stream)
    else:
        print(message, file=stream)


# ================= 小工具 =================


def _setup_console() -> None:
    """Windows 控制台默认 GBK：遇到装不下的字符降级替换，别让脚本崩掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


def clean_name(name: str, limit: int = NAME_LIMIT) -> str:
    """清洗成合法文件名：去掉 Windows 非法字符、首尾空格与点、限制长度。"""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(name))
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > limit:
        name = name[:limit].rstrip(" .")
    if not name:
        return "untitled"
    if name.split(".")[0].upper() in WINDOWS_RESERVED:
        name = "_" + name
    return name


def fit_path(path: Path, limit: int = PATH_LIMIT) -> Path:
    """整条路径过长时，从最深的组件开始缩短（补短哈希防重名），规避 Windows MAX_PATH。"""
    if len(str(path)) <= limit:
        return path

    parts = list(path.parts)
    suffix = path.suffix
    for index in range(len(parts) - 1, 0, -1):        # 不动盘符/根目录
        over = len(str(Path(*parts))) - limit
        if over <= 0:
            break
        piece = parts[index]
        digest = hashlib.md5(piece.encode("utf-8")).hexdigest()[:6]
        if index == len(parts) - 1 and suffix:
            base = piece[: -len(suffix)]
            candidate = f"{base[:max(6, len(base) - over - 7)]}_{digest}{suffix}"
        else:
            candidate = f"{piece[:max(4, len(piece) - over - 7)]}_{digest}"
        if len(candidate) < len(piece):               # 只接受确实变短的
            parts[index] = candidate
    return Path(*parts)


def host_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc or url
    except ValueError:
        return url


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _clip(text: str, limit: int) -> str:
    """截断过长的显示文本（进度条描述等），避免撑爆行宽。"""
    text = str(text)
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"[: max(0, limit)]
    return text[: limit - 1] + "…"


_NESTED_ERROR = re.compile(r"(\w*Error)\((-?\d+),\s*'([^']*)'")


def short_error(exc: BaseException, limit: int = 150) -> str:
    """把异常压成一行可读文本。

    requests 的网络异常常把嵌套异常塞进 args，例如
    "Connection broken: ConnectionResetError(10054, '远程主机强迫关闭了一个现有的连接。', None, 10054, None)"，
    这里收拾成"远程主机强迫关闭了一个现有的连接。（ConnectionResetError 10054）"。
    """
    args = getattr(exc, "args", None) or ()
    text = str(args[0]) if args and str(args[0]).strip() else str(exc)
    text = " ".join(text.split())

    nested = _NESTED_ERROR.search(text)
    if nested:
        text = f"{nested.group(3)}（{nested.group(1)} {nested.group(2)}）"

    if not text:
        text = type(exc).__name__
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


# ================= HTTP 会话 =================


def build_headers(sessdata: str = "") -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    return headers


def build_session() -> requests.Session:
    """带自动重试的会话（对 429/5xx 指数退避）。"""
    session = requests.Session()
    retry = Retry(
        total=3, connect=3, read=3, backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ================= SESSDATA 凭证 =================


_sessdata_origin = ""


def _windows_user_env(name: str | None = None) -> str:
    """直接读注册表里的「用户环境变量」。

    已经打开的终端、常驻服务进程持有的是启动时的环境副本，os.environ 里可能
    读不到刚设置的变量（Windows 只在进程启动时注入环境变量），所以这里直查注册表兜底。
    """
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name or ENV_NAME)
        return str(value).strip()
    except OSError:
        return ""


def sessdata_origin() -> str:
    """最近一次 load_sessdata() 命中的来源（用于日志）。"""
    return _sessdata_origin


def load_sessdata() -> str:
    """按「进程环境变量 → 用户环境变量(注册表) → sessdata.txt → 用户配置」读取凭证。"""
    global _sessdata_origin

    value = os.environ.get(ENV_NAME, "").strip()
    if value:
        _sessdata_origin = "环境变量"
        return value

    value = _windows_user_env()
    if value:
        _sessdata_origin = "用户环境变量"
        return value

    for path in (SESSDATA_FILE, SESSDATA_HOME_FILE):
        try:
            if path.is_file():
                found = path.read_text(encoding="utf-8").strip()
                if found:
                    _sessdata_origin = f"凭证文件 {path.name}"
                    return found
        except OSError:
            continue

    _sessdata_origin = ""
    return ""


def _vip_label_text(raw) -> str:
    """取会员标签的可读文字。

    老版 nav 接口的 vip_label 是字符串；新版是对象（含 text / img_label_uri_* 等字段）。
    这里统一取文字，避免把整个对象打印给用户。
    """
    if isinstance(raw, dict):
        raw = raw.get("text")
    return str(raw or "").strip()


def probe_account(session: requests.Session, headers: dict, timeout: float) -> dict:
    """查询凭证的登录/会员状态。

    返回 {"login": bool, "vip": bool, "vip_label": str}；
    网络异常或接口不可用时返回空字典（表示"无法判断"，不要当成未登录）。
    """
    try:
        resp = session.get(API_NAV, headers=headers, timeout=timeout)
        data = (resp.json() or {}).get("data") or {}
    except Exception:
        return {}
    if not data:                     # 响应体异常时不要误判成"未登录"
        return {}
    return {
        "login": bool(data.get("isLogin")),
        "vip": bool(data.get("vipStatus") or data.get("vipType")),
        "vip_label": _vip_label_text(data.get("vip_label")),
    }


def check_sessdata(session: requests.Session, headers: dict,
                   timeout: float) -> bool | None:
    """用 nav 接口校验凭证：True/False 为校验结果，None 表示无法判断（网络问题）。"""
    info = probe_account(session, headers, timeout)
    return None if not info else bool(info["login"])


def _broadcast_env_change() -> None:
    """best-effort：通知资源管理器环境变量已变更。"""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None
        )
    except Exception:
        pass


def save_sessdata(value: str) -> str:
    """持久化凭证，返回给用户看的说明。

    Windows：写入用户环境变量（REG_SZ，不会被 % 展开）；
    其他系统：写入 ~/.config/bilibili-downloader/sessdata（权限 600）。
    """
    value = (value or "").strip()
    if not value:
        return "未保存（空值）"

    if os.name == "nt":
        try:
            import winreg

            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, ENV_NAME, 0, winreg.REG_SZ, value)
            _broadcast_env_change()
            os.environ[ENV_NAME] = value          # 让当前进程也立刻一致
            return f"Windows 用户环境变量 {ENV_NAME}"
        except OSError as exc:
            return f"写入环境变量失败（{exc}）"

    try:
        SESSDATA_HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSDATA_HOME_FILE.write_text(value, encoding="utf-8")
        SESSDATA_HOME_FILE.chmod(0o600)
        return str(SESSDATA_HOME_FILE)
    except OSError as exc:
        return f"写入配置文件失败（{exc}）"


def prompt_sessdata(session: requests.Session, timeout: float, *,
                    expired: bool = False) -> str:
    """交互式询问 SESSDATA（不回显），校验后保存；留空表示使用游客模式。

    expired=True 用于「已有凭证但校验失效」的场景：只给一行极简提示，不重复新手教程。
    """
    if expired:
        label = "粘贴新的 SESSDATA（留空跳过，用游客模式）："
    else:
        print("\n未检测到 SESSDATA，进入凭证设置：")
        print("  · 无凭证只能拿到较低画质（一般 480P/720P），也没有无损音频。")
        print("  · 获取方法：浏览器登录 B 站 → F12 → Application → Cookies")
        print("              → 选中 https://www.bilibili.com → 复制名为 SESSDATA 的值")
        print("  · 输入不会回显（粘贴后直接回车）；它只保存在本机，请勿外传。")
        label = "SESSDATA（留空跳过）："

    try:
        value = getpass.getpass(label).strip()
    except Exception:
        value = input(label).strip()

    if not value:
        print("已跳过，使用游客模式。\n")
        return ""

    info = probe_account(session, build_headers(value), timeout)
    if info.get("login"):
        print(f"[OK] 凭证校验通过（{'大会员' if info.get('vip') else '普通账号'}）")
    elif info:
        print("[!] 校验显示未登录：可能已过期或复制不完整；仍会保存，"
              "之后可用 --reset-sessdata 重设")
    else:
        print("（无法联网校验，按原样保存）")

    where = save_sessdata(value)
    print(f"已保存到：{where}（下次运行自动读取）")
    print()
    return value


def _is_interactive(args: argparse.Namespace) -> bool:
    """只有真正的交互式终端才提问：输出被重定向、或加了 -y/--yes，都不问。"""
    if getattr(args, "yes", False):
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def ensure_credential(session: requests.Session,
                      args: argparse.Namespace) -> tuple[str, dict]:
    """拿到可用凭证：读取 → 校验 → 失效则明确告警并可直接重输。返回 (sessdata, headers)。"""
    sessdata = "" if args.reset_sessdata else load_sessdata()

    if sessdata:
        print(f"[凭证] 已从{sessdata_origin()}读取 SESSDATA")
        info = probe_account(session, build_headers(sessdata), args.timeout)
        if info.get("login"):
            role = info.get("vip_label") or ("大会员" if info.get("vip") else "普通账号")
            print(f"[凭证] 校验通过（{role}）")
        elif info:
            if _is_interactive(args):
                print("[!] 凭证已失效：现在只能以游客身份下载，一般最高 480P/360P。")
                try:
                    answer = input("现在重新输入 SESSDATA？[Y/n] ").strip().lower()
                except EOFError:
                    answer = "n"
                if answer not in {"n", "no"}:
                    sessdata = prompt_sessdata(session, args.timeout, expired=True)
            else:
                print("[!] 凭证已失效（接口返回未登录）：现在只能以游客身份下载，"
                      "一般最高 480P/360P，也没有无损音频。")
                print("    换新凭证：加 --reset-sessdata 重新输入，或在浏览器重新登录后重跑。")
        else:
            print("[凭证] 网络不可用，跳过校验")

    if not sessdata:
        sessdata = prompt_sessdata(session, args.timeout)

    headers = build_headers(sessdata)
    if not sessdata:
        print("[提示] 游客模式：通常最高 480P/720P，且拿不到无损音频。")
    return sessdata, headers


# ================= WBI 签名 =================

_mixin_key_cache: dict = {"key": "", "at": 0.0}


def derive_mixin_key(img_key: str, sub_key: str) -> str:
    """按混淆表从 img_key+sub_key 推出 32 位 mixin_key。"""
    merged = img_key + sub_key
    return "".join(merged[i] for i in MIXIN_KEY_ENC_TAB if i < len(merged))[:32]


def _url_stem(url: str) -> str:
    tail = url.rsplit("/", 1)[-1]
    return tail.split(".")[0]


def fetch_mixin_key(session: requests.Session, headers: dict, timeout: float,
                    force: bool = False) -> str:
    """从 nav 接口取 wbi 密钥（未登录也会返回，因此不看 code）。"""
    now = time.time()
    if not force and _mixin_key_cache["key"] and now - _mixin_key_cache["at"] < 1800:
        return _mixin_key_cache["key"]
    resp = session.get(API_NAV, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = (resp.json() or {}).get("data") or {}
    wbi = data.get("wbi_img") or {}
    img_url, sub_url = wbi.get("img_url") or "", wbi.get("sub_url") or ""
    if not img_url or not sub_url:
        raise DownloadError("无法获取 WBI 签名密钥（nav 接口未返回 wbi_img）")
    key = derive_mixin_key(_url_stem(img_url), _url_stem(sub_url))
    _mixin_key_cache.update(key=key, at=now)
    return key


def wbi_query(params: dict, mixin_key: str, wts: int | None = None) -> str:
    """拼出带 wts 与 w_rid 的查询串（w_rid = md5(查询串 + mixin_key)）。"""
    clean = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in params.items()
    }
    query = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted(clean.items())
    )
    stamp = int(time.time() if wts is None else wts)
    query = f"{query}&wts={stamp}" if query else f"wts={stamp}"
    digest = hashlib.md5(f"{query}{mixin_key}".encode()).hexdigest()
    return f"{query}&w_rid={digest}"


# ================= B 站 API =================


def api_get(session: requests.Session, api: str, params: dict, headers: dict,
            timeout: float, mixin_key: str | None = None) -> dict:
    """调用接口并返回 data；业务错误码统一抛 DownloadError。"""
    if mixin_key:
        url = f"{api}?{wbi_query(params, mixin_key)}"
        resp = session.get(url, headers=headers, timeout=timeout)
    else:
        resp = session.get(api, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json() or {}
    code = payload.get("code", 0)
    if code != 0:
        raise DownloadError(f"{payload.get('message') or '接口返回错误'}（code={code}）")
    return payload.get("data") or {}


def fetch_view(session: requests.Session, headers: dict, timeout: float,
               bvid: str | None = None, aid: int | None = None) -> dict:
    """取视频详细信息（含 pages 分P / ugc_season 合集）。"""
    params = {"bvid": bvid} if bvid else {"aid": aid}
    return api_get(session, API_VIEW, params, headers, timeout)


def fetch_streams(session: requests.Session, headers: dict, timeout: float,
                  bvid: str, cid: int) -> dict:
    """取 DASH 流地址：优先带 WBI 签名的接口，失败回退旧接口。"""
    params = {
        "bvid": bvid, "cid": cid,
        "qn": 127,        # 请求最高画质（实际以返回为准）
        "fnver": 0,
        "fnval": 4048,    # 一次要齐 DASH/4K/HDR/8K/杜比 等全部特性
        "fourk": 1,
    }
    try:
        key = fetch_mixin_key(session, headers, timeout)
        data = api_get(session, API_PLAYURL_WBI, params, headers, timeout, mixin_key=key)
    except DownloadError as exc:
        emit(f"[重试] WBI 签名接口未成功（{short_error(exc)}），改用旧接口重试")
        data = api_get(session, API_PLAYURL, params, headers, timeout)
    dash = data.get("dash")
    if not dash:
        raise DownloadError("该视频没有 DASH 流（可能是番剧/老视频，或需要登录）")
    return dash


def resolve_input(session: requests.Session, headers: dict, timeout: float,
                  raw: str) -> tuple[str, int | None]:
    """把任意输入（链接 / BV 号 / av 号 / b23.tv 短链）解析成 (bvid, 分P序号)。"""
    text = (raw or "").strip()
    if not text:
        raise DownloadError("输入为空")

    page = None
    m = re.search(r"[?&]p=(\d+)", text)
    if m:
        page = max(1, int(m.group(1)))

    m = re.search(r"(BV[0-9A-Za-z]{10})", text)
    if m:
        return m.group(1), page

    m = re.fullmatch(r"av(\d+)", text, re.IGNORECASE)
    if m:
        data = fetch_view(session, headers, timeout, aid=int(m.group(1)))
        return data.get("bvid") or "", page

    if text.lower().startswith(("http://", "https://")):
        resp = session.get(text, headers=headers, timeout=timeout, allow_redirects=True)
        for candidate in (resp.url or "", (resp.text or "")[:200000]):
            m = re.search(r"(BV[0-9A-Za-z]{10})", candidate)
            if m:
                return m.group(1), page

    raise DownloadError(f"无法识别的输入：{raw}")


# ================= 下载计划 =================


@dataclass
class Item:
    """一个最小下载单位：某个视频的某一个分P（或单P视频本身）。"""

    bvid: str
    cid: int
    label: str            # 显示与命名用（已清洗）
    out_dir: Path         # 成品所在目录
    quality_hint: str = ""

    @property
    def mp4(self) -> Path:
        return fit_path(self.out_dir / f"{self.label}.mp4")

    @property
    def mp3(self) -> Path:
        return fit_path(self.out_dir / f"{self.label}.mp3")

    @property
    def video_m4s(self) -> Path:
        return self.out_dir / f"{self.label}.video.m4s"

    @property
    def audio_m4s(self) -> Path:
        return self.out_dir / f"{self.label}.audio.m4s"


def _pages_of(entry: dict) -> list[dict]:
    return [p for p in (entry.get("pages") or []) if p.get("cid")]


def build_plan(session: requests.Session, headers: dict, inputs: Sequence[str], *,
               root: Path, single: bool = False, timeout: float = 15.0,
               log: Callable[[str], None] = print) -> list[Item]:
    """把输入链接展开成下载清单（自动展开合集 / 多P）。"""
    items: list[Item] = []
    seen: set[tuple[str, int]] = set()

    def add(bvid: str, cid: int, label: str, out_dir: Path) -> None:
        if not bvid or not cid:
            return
        if (bvid, cid) in seen:
            return
        seen.add((bvid, cid))
        items.append(Item(bvid=bvid, cid=cid, label=label, out_dir=out_dir))

    for raw in inputs:
        bvid, page = resolve_input(session, headers, timeout, raw)
        if not bvid:
            raise DownloadError(f"{raw}：没有解析出 BV 号")
        data = fetch_view(session, headers, timeout, bvid=bvid)

        if data.get("redirect_url"):
            raise DownloadError(
                f"{bvid} 是番剧/影视内容（{data.get('redirect_url')}），"
                "本工具只支持普通投稿（UGC）"
            )

        title = clean_name(data.get("title") or bvid)
        pages = _pages_of(data)
        season = data.get("ugc_season")

        # ---- 合集：bili_downloads\<合集名>\<视频名>\... ----
        if season and not single:
            season_title = clean_name(season.get("title") or "合集")
            if season.get("is_pay_season"):
                raise DownloadError(f"《{season_title}》是付费合集，无法下载")
            episodes: list[dict] = []
            for section in season.get("sections") or []:
                episodes.extend(section.get("episodes") or section.get("archives") or [])
            log(f"  合集《{season_title}》：{len(episodes)} 个视频")
            for ep in episodes:
                ep_bvid = ep.get("bvid") or ""
                ep_pages = _pages_of(ep)
                ep_title = clean_name(
                    ep.get("title") or (ep.get("arc") or {}).get("title") or ep_bvid
                )
                if len(ep_pages) > 1:
                    for p in ep_pages:
                        label = clean_name(f"P{int(p.get('page', 1)):02d} {p.get('part') or ''}")
                        add(ep_bvid, int(p["cid"]), label,
                            root / season_title / ep_title / label)
                else:
                    cid = int(ep.get("cid") or (ep_pages[0]["cid"] if ep_pages else 0))
                    add(ep_bvid, cid, ep_title, root / season_title / ep_title)
            continue

        # ---- 多P：bili_downloads\<视频标题>\<Pxx 分P标题>\... ----
        if len(pages) > 1:
            selected = pages
            if single and page and page <= len(pages):
                selected = [pages[page - 1]]
            for p in selected:
                label = clean_name(f"P{int(p.get('page', 1)):02d} {p.get('part') or ''}")
                add(bvid, int(p["cid"]), label, root / title / label)
            continue

        # ---- 单视频：bili_downloads\<视频标题>\<视频标题>.mp4 ----
        if single and page and page > 1 and not pages:
            raise DownloadError(f"{bvid}：该视频没有第 {page} 个分P")
        cid = int(pages[0]["cid"]) if pages else int(data.get("cid") or 0)
        if not cid:
            raise DownloadError(f"{bvid}：接口没有返回 cid，无法下载")
        label = title if not (single and page) else clean_name(f"P{page:02d} {title}")
        add(bvid, cid, label, root / title if not (single and page) else root / title / label)

    return items


# ================= 下载实现 =================


def collect_urls(stream: dict) -> list[str]:
    """主地址 + 所有备份地址，去重。"""
    urls: list[str] = []
    if stream.get("baseUrl"):
        urls.append(stream["baseUrl"])
    for extra in stream.get("backupUrl") or []:
        if extra and extra not in urls:
            urls.append(extra)
    return urls


def probe_first_ok(session: requests.Session, urls: list[str], headers: dict,
                   timeout: float) -> str | None:
    """并发 HEAD 探测，返回最先响应的可用节点（不是测速，只比谁先回应）。"""
    def probe(url: str) -> str:
        resp = session.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400:
            raise DownloadError(f"HTTP {resp.status_code}")
        return url

    with ThreadPoolExecutor(max_workers=max(1, len(urls))) as pool:
        futures = [pool.submit(probe, url) for url in urls]
        try:
            for future in as_completed(futures):
                try:
                    return future.result()
                except Exception:
                    continue
        finally:
            for future in futures:
                future.cancel()
    return None


def _expected_total(resp: requests.Response, already: int) -> int:
    """从响应头推断文件总大小（0 表示无法判断）。"""
    content_range = resp.headers.get("Content-Range") or ""
    if "/" in content_range:
        tail = content_range.rsplit("/", 1)[1].strip()
        if tail.isdigit():
            return int(tail)
    length = resp.headers.get("Content-Length") or ""
    if length.isdigit():
        return already + int(length)
    return 0


class SpeedWatchdog:
    """速度看门狗：速度掉到"自身历史平均"的 30% 以下并持续 10 秒，就判定这条连接已废。

    - 参考速度 = 从开始下载到（当前时刻 - SLOW_REF_LAG）的平均速度；
    - 当前速度 = 最近 SLOW_CUR_WINDOW 秒的平均速度；
    - 例外：若按当前速度算出的**预计剩余时间小于 SLOW_MIN_ETA（10 秒）**，
      说明马上就下完了，保持这条连接继续下，不重连；
    - 本来就慢（参考速度低于 SLOW_MIN_REF）时不判定；
    - 时间由调用方传入（now），因此可以脱离真实时钟做单元测试。
    """

    def __init__(self, started_at: float, start_bytes: int, total: int, *,
                 check_interval: float | None = None, cur_window: float | None = None,
                 ref_lag: float | None = None, ratio: float | None = None,
                 hold: float | None = None, min_elapsed: float | None = None,
                 min_ref: int | None = None, min_eta: float | None = None) -> None:
        self.started_at = started_at
        self.start_bytes = start_bytes
        self.total = total
        self.check_interval = SLOW_CHECK_INTERVAL if check_interval is None else check_interval
        self.cur_window = SLOW_CUR_WINDOW if cur_window is None else cur_window
        self.ref_lag = SLOW_REF_LAG if ref_lag is None else ref_lag
        self.ratio = SLOW_RATIO if ratio is None else ratio
        self.hold = SLOW_HOLD if hold is None else hold
        self.min_elapsed = SLOW_MIN_ELAPSED if min_elapsed is None else min_elapsed
        self.min_ref = SLOW_MIN_REF if min_ref is None else min_ref
        self.min_eta = SLOW_MIN_ETA if min_eta is None else min_eta
        self._samples: deque[tuple[float, int]] = deque()
        self._slow_since: float | None = None
        self._last_check = started_at
        self._max_gap = 0.0            # 观察到的最长采样间隔（连接越慢间隔越大）

    def due(self, now: float) -> bool:
        """是否到了该判定的时刻（约每 check_interval 秒一次）。"""
        return now - self._last_check >= self.check_interval

    def sample(self, now: float, done: int) -> str | None:
        """喂一个采样点；返回"变慢"的原因（给用户看）或 None。"""
        self._last_check = now
        if self._samples:
            self._max_gap = max(self._max_gap, now - self._samples[-1][0])
        self._samples.append((now, done))
        # 保留足够长的历史：既要覆盖 ref_lag，也要容纳一次"采样间隔"（慢连接可能几十秒一块），
        # 否则算参考速度时需要的那个老采样点会被裁掉，看门狗就永远不会触发。
        keep_from = (now - max(self.ref_lag, self.cur_window)
                     - self._max_gap - 1.0)
        while len(self._samples) > 2 and self._samples[0][0] < keep_from:
            self._samples.popleft()

        if now - self.started_at < self.min_elapsed:
            return None

        ref_t, ref_bytes = self.started_at, self.start_bytes
        for stamp, amount in self._samples:          # 取 (now - ref_lag) 之前最后一个采样
            if stamp <= now - self.ref_lag:
                ref_t, ref_bytes = stamp, amount
            else:
                break
        ref_elapsed = ref_t - self.started_at
        if ref_elapsed <= 0 or ref_bytes <= self.start_bytes:
            return None
        ref_speed = (ref_bytes - self.start_bytes) / ref_elapsed
        if ref_speed < self.min_ref:
            self._slow_since = None                  # 本来就慢，不折腾
            return None

        # 当前速度 = 最近一段"至少覆盖 min_span 秒"的采样区间（取尽可能新的那个采样点）：
        # 采样密时约等于最近 1 秒的速度，采样稀（连接慢、一块要等很久）时自然退化成
        # "上一块到这一块"的平均速度 —— 否则当前速度会跨过整段快速期，永远判不出变慢。
        min_span = min(1.0, self.cur_window)
        cur_t, cur_bytes = None, None
        for stamp, amount in reversed(self._samples):
            if now - stamp >= min_span:
                cur_t, cur_bytes = stamp, amount
                break
        if cur_t is None or now - cur_t <= 0:
            return None
        cur_speed = max(0.0, (done - cur_bytes) / (now - cur_t))

        if cur_speed >= self.ratio * ref_speed:
            self._slow_since = None                  # 恢复正常，重新计时
            return None

        # 例外：按当前速度估算马上就下完了（剩余时间 < SLOW_MIN_ETA），就保持连接继续下
        if self.total:
            remaining = max(0, self.total - done)
            eta = remaining / cur_speed if cur_speed > 0 else float("inf")
            if eta < self.min_eta:
                return None

        if self._slow_since is None:
            self._slow_since = now
            return None
        held = now - self._slow_since
        if held < self.hold:
            return None
        eta_text = ""
        if self.total and cur_speed > 0:
            eta_text = f"，按此速度还需 {(self.total - done) / cur_speed:.0f} 秒"
        return (f"速度只有 {human_size(int(cur_speed))}/s，"
                f"是此前平均 {human_size(int(ref_speed))}/s 的 "
                f"{cur_speed / ref_speed * 100:.0f}%，已持续 {held:.0f} 秒{eta_text}")


def download_to_file(session: requests.Session, url: str, dest: Path, desc: str,
                     headers: dict, timeout: float, *,
                     bar_position: int | None = None, prefix: str = "",
                     bar_desc: str | None = None, slow_check: bool = True) -> None:
    """下载 url 到 dest：写 <dest>.part，支持断点续传 + 完整性校验，成功后原子改名。

    bar_position 为进度条位置（多线程时每个线程一个，互不覆盖）；
    为 None 表示不放进度条，改为每 15 秒打一行进度（输出被重定向时用）。
    bar_desc 可覆盖进度条标题（用来写清"这是哪个视频的哪条流"）。
    slow_check 打开速度看门狗：速度长期掉到历史平均的 30% 以下会抛 SlowConnection。
    """
    part = dest.with_name(dest.name + PART_SUFFIX)
    already = part.stat().st_size if part.exists() else 0

    request_headers = dict(headers)
    request_headers["Accept-Encoding"] = "identity"   # 防止压缩破坏续传
    if already:
        request_headers["Range"] = f"bytes={already}-"

    with session.get(url, headers=request_headers, stream=True, timeout=timeout) as resp:
        if already and resp.status_code == 416:
            part.unlink(missing_ok=True)
            raise DownloadError("服务器拒绝续传（416），已清除断点，请重试")
        resp.raise_for_status()
        resuming = already > 0 and resp.status_code == 206
        if not resuming:
            already = 0
        total = _expected_total(resp, already)

        mode = "ab" if resuming else "wb"
        done = already
        last_report = time.time()
        watchdog = (SpeedWatchdog(time.time(), already, total)
                    if slow_check and total else None)
        with open(part, mode) as fh, tqdm(
            total=total or None, initial=already, unit="B", unit_scale=True,
            unit_divisor=1024, desc=bar_desc or f"{prefix}{desc}", leave=False,
            position=bar_position or 0, disable=bar_position is None,
            file=sys.stdout,
        ) as bar:
            quiet = bool(getattr(bar, "disable", True))    # 进度条被禁用（输出被重定向）
            for chunk in resp.iter_content(CHUNK_SIZE):
                if _ABORT.is_set():
                    raise Aborted(f"{desc}：已取消")
                if chunk:
                    fh.write(chunk)
                    done += len(chunk)
                    bar.update(len(chunk))
                    if quiet and time.time() - last_report >= 15:
                        last_report = time.time()
                        percent = f"{done * 100 // total}%" if total else "?"
                        amount = (f"{human_size(done)}/{human_size(total)}"
                                  if total else human_size(done))
                        emit(f"{prefix}{desc} {percent} {amount}")
                now = time.time()
                if watchdog is not None and watchdog.due(now):
                    reason = watchdog.sample(now, done)
                    if reason:
                        raise SlowConnection(reason)

    size = part.stat().st_size
    if total and size != total:
        raise DownloadError(f"下载不完整：期望 {human_size(total)}，实际 {human_size(size)}")
    if size == 0:
        raise DownloadError("下载结果为空文件")
    part.replace(dest)


def download_stream(session: requests.Session, stream: dict, dest: Path, desc: str, *,
                    headers: dict, retries: int = 2, timeout: float = 15.0,
                    use_probe: bool = True, bar_position: int | None = None,
                    prefix: str = "", bar_desc: str | None = None,
                    max_reconnects: int = DEFAULT_MAX_RECONNECTS) -> None:
    """多节点 + 多次重试 + 退避，任一节点成功即返回。

    输出带明确状态：[跳过] 已有缓存 / [重试] 某节点某次失败 / [重连] 速度变慢换连接 /
    [成功] 最终成功，这样即使中间失败过，也能一眼看出最后到底成没成。
    max_reconnects 为"因速度变慢而重开连接"的上限（0 = 关闭该检测）。
    """
    if _ABORT.is_set():
        raise Aborted(f"{desc}：已取消")
    if dest.exists() and dest.stat().st_size > 0:
        emit(f"{prefix}{desc}：[跳过] 已有缓存 {human_size(dest.stat().st_size)}，不重复下载")
        return

    urls = collect_urls(stream)
    if not urls:
        raise DownloadError(f"{desc}：没有可用的下载地址")

    if use_probe and len(urls) > 1:
        try:
            fast = probe_first_ok(session, urls, headers, timeout)
            if fast:
                urls = [fast] + [u for u in urls if u != fast]
                emit(f"{prefix}{desc}：已优选节点 {host_of(fast)}（候选 {len(urls)} 个）")
            else:
                emit(f"{prefix}{desc}：[!] {len(urls)} 个候选节点都没通过探测，按原顺序尝试")
        except Exception as exc:
            emit(f"{prefix}{desc}：[!] 节点优选失败（{short_error(exc)}），按原顺序尝试")

    last_error: Exception | None = None
    had_failure = False
    reconnects = 0
    node_index = 0
    attempt = 0            # 当前节点第几次尝试
    fails_here = 0         # 当前节点连续失败次数（用于退避）
    while True:
        attempt += 1
        started = time.time()
        try:
            download_to_file(session, urls[node_index], dest, desc, headers, timeout,
                             bar_position=bar_position, prefix=prefix, bar_desc=bar_desc,
                             slow_check=max_reconnects > 0)
        except (Aborted, KeyboardInterrupt):
            raise
        except SlowConnection as exc:
            if reconnects >= max_reconnects:
                raise DownloadError(
                    f"{desc}：[失败] 速度反复变慢，已重开 {reconnects} 次连接仍无改善（{exc}）")
            reconnects += 1
            node_index = (node_index + 1) % len(urls)   # 换一条连接（顺便换 CDN）再续传
            attempt = 0                                 # 重连不消耗失败重试次数
            fails_here = 0
            emit(f"{prefix}{desc}：[重连] {exc}；已丢掉这条连接，"
                 f"换节点 {node_index + 1}/{len(urls)} 续传（第 {reconnects}/{max_reconnects} 次）")
            _abortable_sleep(0.5)
            continue
        except Exception as exc:
            last_error = exc
            had_failure = True
            fails_here += 1
            more_nodes = node_index + 1 < len(urls)
            if fails_here < retries:
                action = "同一节点重试"
            else:
                action = "换下一个节点" if more_nodes else "已无可用节点"
            emit(f"{prefix}{desc}：[重试] 节点 {node_index + 1}/{len(urls)} "
                 f"第 {fails_here} 次失败（{short_error(exc)}）→ {action}")
            if fails_here >= retries:
                if not more_nodes:
                    break
                node_index += 1
                fails_here = 0
                attempt = 0
            _abortable_sleep(min(1.5 * fails_here if fails_here else 1.5, 6.0))
            continue
        else:
            size = dest.stat().st_size if dest.exists() else 0
            if had_failure or reconnects:   # 只有折腾过才播报，正常情况不刷屏
                emit(f"{prefix}{desc}：[成功] 第 {node_index + 1} 个节点第 {attempt} 次尝试成功"
                     f"（{human_size(size)}，用时 {time.time() - started:.0f}s）")
            return

    raise DownloadError(f"{desc}：[失败] {len(urls)} 个节点全部尝试失败，"
                        f"最后一次错误：{short_error(last_error) if last_error else '未知'}")


# ================= ffmpeg =================


@lru_cache(maxsize=1)
def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise DownloadError(
            "未找到 ffmpeg，请先安装并加入 PATH\n"
            "    Windows: choco install ffmpeg   或   scoop install ffmpeg\n"
            "    macOS:   brew install ffmpeg\n"
            "    Linux:   sudo apt install ffmpeg"
        )
    return exe


def run_ffmpeg(args: list, err_msg: str) -> None:
    cmd = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    proc = subprocess.run(
        cmd, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise DownloadError(f"{err_msg}：{(proc.stderr or '').strip()[:800]}")


def _ffmpeg_to_file(args: list, dest: Path, err_msg: str) -> None:
    """跑 ffmpeg 写 <dest>.part，成功再原子改名，失败不留半成品。"""
    tmp = dest.with_name(f"{dest.stem}{PART_SUFFIX}{dest.suffix}")
    try:
        run_ffmpeg([*args, str(tmp)], err_msg)
        if not tmp.exists() or tmp.stat().st_size == 0:
            raise DownloadError(f"{err_msg}：输出为空")
        tmp.replace(dest)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def merge_av(video_m4s: Path, audio_m4s: Path, out_mp4: Path) -> None:
    """-c copy 直接封装（不重新编码，秒级完成），并把索引前置便于在线播放。"""
    _ffmpeg_to_file(
        ["-i", str(video_m4s), "-i", str(audio_m4s),
         "-c", "copy", "-movflags", "+faststart"],
        out_mp4, "合并音视频失败",
    )


def export_mp3(audio_m4s: Path, out_mp3: Path, bitrate: str) -> None:
    _ffmpeg_to_file(
        ["-i", str(audio_m4s), "-vn", "-c:a", "libmp3lame", "-b:a", f"{bitrate}k"],
        out_mp3, "导出 MP3 失败",
    )


# ================= 选流 =================


def pick_video(dash: dict, max_id: int) -> dict:
    streams = [s for s in (dash.get("video") or []) if s.get("baseUrl")]
    if not streams:
        raise DownloadError("没有可用的视频流")
    for stream in sorted(streams, key=lambda s: s.get("id", 0), reverse=True):
        if stream.get("id", 0) <= max_id:
            return stream
    return min(streams, key=lambda s: s.get("id", 0))   # 请求的清晰度都没有，退回最低


def pick_audio(dash: dict) -> dict:
    candidates: list[dict] = [s for s in (dash.get("audio") or []) if s.get("baseUrl")]

    flac = (dash.get("flac") or {}).get("audio")
    if isinstance(flac, dict) and flac.get("baseUrl"):
        candidates.append(flac)

    dolby = (dash.get("dolby") or {}).get("audio")
    if isinstance(dolby, dict) and dolby.get("baseUrl"):
        candidates.append(dolby)
    elif isinstance(dolby, list):
        candidates.extend(s for s in dolby if s.get("baseUrl"))

    if not candidates:
        raise DownloadError("没有可用的音频流")
    lossless = [s for s in candidates if s.get("id") in AUDIO_LOSSLESS_IDS]
    pool = lossless or candidates
    return max(pool, key=lambda s: s.get("bandwidth", 0))


# ================= 单个视频的处理流程 =================


@dataclass
class Stats:
    ok: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_done: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def already_done(item: Item, want_mp4: bool, want_mp3: bool) -> bool:
    def good(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    if want_mp4 and not good(item.mp4):
        return False
    if want_mp3 and not good(item.mp3):
        return False
    return True


def process_item(session: requests.Session, item: Item, *, headers: dict,
                 stream_getter: Callable[[Item], dict], timeout: float = 15.0,
                 retries: int = 2, use_probe: bool = True,
                 want_mp4: bool = True, want_mp3: bool = True,
                 mp3_bitrate: str = "320", max_quality: int = 127,
                 force: bool = False, tag: str = "",
                 bar_position: int | None = None, bar_prefix: str = "",
                 quiet: bool = False,
                 max_reconnects: int = DEFAULT_MAX_RECONNECTS) -> int:
    """下载并生成成品，返回新增文件的总字节数。

    已存在抛 FileExistsError（不算失败）；失败抛 DownloadError；被打断抛 Aborted。
    tag 用于多线程模式下标记输出行属于哪一项；bar_position 是该线程的进度条位置；
    bar_prefix 非空时进度条标题会带上"哪个视频的哪条流"；quiet 表示不要打印逐项标题行。
    """
    if _ABORT.is_set():
        raise Aborted("已取消")
    if not force and already_done(item, want_mp4, want_mp3):
        emit(f"{tag}[跳过] 成品已存在（{item.out_dir.name}），不重新下载")
        raise FileExistsError("已存在")

    item.out_dir.mkdir(parents=True, exist_ok=True)
    dash = stream_getter(item)
    video = pick_video(dash, max_quality)
    audio = pick_audio(dash)
    picked = int(video.get("id", 0))
    quality = QUALITY_NAMES.get(picked, f"未知({picked})")
    if max_quality < 127 and picked < max_quality:
        quality += f"（低于请求上限 {QUALITY_NAMES.get(max_quality, max_quality)}）"
    elif picked <= 32:
        quality += "（游客或权限受限，通常是凭证失效/非大会员）"
    if not quiet:
        emit(f"{tag}画质 {quality}   音频 {audio.get('id')} "
             f"{int(audio.get('bandwidth', 0) / 1000)} kbps")

    # 进度条标题：并行模式下直接写出"哪个视频的哪条流"，省掉逐项标题行
    quality_short = quality.split(" ")[0]
    video_bar = f"{bar_prefix}{quality_short} 视频流" if bar_prefix else None
    audio_bar = f"{bar_prefix}音频流" if bar_prefix else None

    written = 0
    ok = False
    try:
        if want_mp4:
            download_stream(session, video, item.video_m4s, "视频流",
                            headers=headers, retries=retries, timeout=timeout,
                            use_probe=use_probe, bar_position=bar_position,
                            prefix=tag, bar_desc=video_bar, max_reconnects=max_reconnects)
        download_stream(session, audio, item.audio_m4s, "音频流",
                        headers=headers, retries=retries, timeout=timeout,
                        use_probe=use_probe, bar_position=bar_position,
                        prefix=tag, bar_desc=audio_bar, max_reconnects=max_reconnects)

        if want_mp4:
            merge_av(item.video_m4s, item.audio_m4s, item.mp4)
            written += item.mp4.stat().st_size
            emit(f"{tag}[完成] {item.mp4.name}（{human_size(item.mp4.stat().st_size)}）")
        if want_mp3:
            export_mp3(item.audio_m4s, item.mp3, mp3_bitrate)
            written += item.mp3.stat().st_size
            emit(f"{tag}[完成] {item.mp3.name}（{human_size(item.mp3.stat().st_size)}）")
        ok = True
        return written
    finally:
        if ok:   # 成功才清理中间流文件；失败则保留，方便下次续传
            for temp in (item.video_m4s, item.audio_m4s):
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass


# ================= 下载范围选择 =================


def parse_selection(text: str, total: int) -> list[int] | None:
    """解析"要下载哪些序号"。

    y / yes / all / 空      → 全部（1..total）
    n / no / q / quit       → None（不下载）
    其余按逗号分隔的序号或区间解析，如 "1,3,5,6-20"；
    重复、空项（"1,,3"）、空格、全角逗号都会自动忽略。
    解析失败抛 ValueError（调用方负责提示重输）。
    """
    raw = (text or "").strip().lower()
    if raw in {"", "y", "yes", "all", "a"}:
        return list(range(1, total + 1))
    if raw in {"n", "no", "q", "quit", "exit"}:
        return None

    picked: set[int] = set()
    for token in raw.replace("，", ",").replace("－", "-").split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            left, _, right = token.partition("-")
            left, right = left.strip(), right.strip()
            if not (left.isdigit() and right.isdigit()):
                raise ValueError(f"看不懂的区间“{token}”，应形如 6-20")
            start, end = int(left), int(right)
            if start > end:
                start, end = end, start
            if start < 1 or end > total:
                raise ValueError(f"区间 {start}-{end} 超出范围 1-{total}")
            picked.update(range(start, end + 1))
        else:
            if not token.isdigit():
                raise ValueError(f"看不懂的序号“{token}”，只能是数字或区间")
            number = int(token)
            if not 1 <= number <= total:
                raise ValueError(f"序号 {number} 超出范围 1-{total}")
            picked.add(number)
    return sorted(picked)


def compact_ranges(numbers: Sequence[int]) -> str:
    """把 [1,2,3,5,6,9] 压成 "1-3,5-6,9"（回显用）。"""
    parts: list[str] = []
    start: int | None = None
    prev: int | None = None
    for number in sorted(numbers):
        if start is None:
            start = prev = number
        elif prev is not None and number == prev + 1:
            prev = number
        else:
            parts.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = number
    if start is not None:
        parts.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def ask_selection(total: int, attempts: int = 3) -> list[int] | None:
    """交互式挑选要下载的序号：返回序号列表；None 表示不下载。"""
    print(f"\n共 {total} 项。回车 / y = 全部下载，n = 不下载，"
          f"也可只下部分（如 1,3,5,6-20）：")
    while attempts > 0:
        try:
            raw = input("> ").strip()
        except EOFError:                     # 输入被关闭：按"全部"继续
            return list(range(1, total + 1))
        try:
            picked = parse_selection(raw, total)
        except ValueError as exc:
            attempts -= 1
            print(f"[!] {exc}" + ("" if attempts else "（多次无效输入，已取消）"))
            continue
        if picked is None:
            return None
        if not picked:
            print("[!] 没有选中任何项目，请重新输入")
            continue
        return picked
    return None


# ================= 命令行 =================


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="B 站视频 / 分P / 合集下载器（DASH 分流 + ffmpeg 合并）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("inputs", nargs="*",
                        help="视频链接 / BV 号 / av 号，可给多个；不填则交互式输入")
    parser.add_argument("-o", "--output", default="./bili_downloads",
                        help="保存根目录")
    parser.add_argument("-q", "--quality", default="max",
                        choices=sorted(QUALITY_LIMITS), help="允许的最高画质")
    parser.add_argument("--mp3-bitrate", default="320", choices=["128", "192", "256", "320"],
                        help="导出 MP3 的码率 kbps")
    parser.add_argument("--audio-only", action="store_true", help="只导出 MP3（不下载视频流）")
    parser.add_argument("--no-mp3", action="store_true", help="只保存 MP4")
    parser.add_argument("--single", action="store_true",
                        help="只下载输入链接指向的那一个视频/分P（忽略合集）")
    parser.add_argument("--force", action="store_true", help="已存在也重新下载")
    parser.add_argument("--reset-sessdata", action="store_true",
                        help="忽略已保存的凭证，重新交互式输入")
    parser.add_argument("-j", "--jobs", type=int, default=4, choices=(1, 2, 3, 4),
                        help="并发下载线程数（最多 4；1 = 串行并显示实时进度条）")
    parser.add_argument("--max-reconnects", type=int, default=DEFAULT_MAX_RECONNECTS,
                        metavar="N",
                        help="单个流因“速度掉到历史平均 30%% 以下”而重开连接的次数上限（0 = 关闭）")
    parser.add_argument("--no-probe", action="store_true", help="关闭节点优选探测")
    parser.add_argument("--retries", type=int, default=2, help="每个节点重试次数")
    parser.add_argument("--timeout", type=float, default=15.0, help="网络超时（秒）")
    parser.add_argument("--dry-run", action="store_true", help="只列出计划，不下载")
    parser.add_argument("-y", "--yes", action="store_true", help="不询问，直接开始")
    args = parser.parse_args(argv)

    if args.audio_only and args.no_mp3:
        parser.error("--audio-only 与 --no-mp3 不能同时使用")
    if args.retries < 1:
        parser.error("--retries 至少为 1")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    return args


def _cancelled() -> int:
    """Ctrl+C 的收尾：一句人话 + 退出码 130，绝不打 traceback。"""
    print("\n[中断] 已取消；已下载的部分会保留，重新运行可续传。")
    return 130


def main(argv: Sequence[str] | None = None) -> int:
    """入口：把 Ctrl+C 统一收成退出码 130；任何意外错误也只给人话，不打 traceback。"""
    try:
        return _main_impl(argv)
    except KeyboardInterrupt:
        return _cancelled()
    except Exception as exc:              # 兜底：不让用户看到 traceback
        print(f"\n[失败] {short_error(exc, limit=300)}", file=sys.stderr)
        return 1


def _main_impl(argv: Sequence[str] | None = None) -> int:
    _setup_console()
    args = parse_args(argv)

    session = build_session()
    sessdata, headers = ensure_credential(session, args)

    inputs = [x for x in (args.inputs or []) if x.strip()]
    if not inputs:
        try:
            raw = input("请输入 B 站视频链接 / BV 号（多个用空格分隔）：")
        except EOFError:
            print("没有收到输入")
            return 2
        inputs = [x for x in raw.split() if x.strip()]
    if not inputs:
        print("输入不能为空")
        return 2

    root = Path(args.output).expanduser()
    want_mp4 = not args.audio_only
    want_mp3 = not args.no_mp3

    print("正在获取视频信息…")
    try:
        items = build_plan(session, headers, inputs, root=root,
                           single=args.single, timeout=args.timeout)
    except KeyboardInterrupt:
        print("\n已取消")
        return 130
    except DownloadError as exc:
        print(f"[失败] {short_error(exc, limit=300)}")
        return 1

    if not items:
        print("[!] 没有找到可下载的内容")
        return 1

    print(f"\n计划下载 {len(items)} 项 → {root.resolve()}")
    for index, item in enumerate(items, 1):
        try:
            shown = item.out_dir.relative_to(root)
        except ValueError:
            shown = item.out_dir
        print(f"  {index:>3}. {shown}\\{item.label}")

    if args.dry_run:
        print("\n（--dry-run：未下载）")
        return 0

    if len(items) > 1 and _is_interactive(args):
        picked = ask_selection(len(items))
        if picked is None:
            print("已取消")
            return 0
        if len(picked) < len(items):
            print(f"[选择] 已选 {len(picked)}/{len(items)} 项：{compact_ranges(picked)}")
            selected = [(i, items[i - 1]) for i in picked]
        else:
            selected = list(enumerate(items, 1))
    else:
        selected = list(enumerate(items, 1))

    total = len(selected)

    stats = Stats()
    started = time.time()
    _ABORT.clear()                       # 允许同一进程内重复调用 main()
    _reset_progress()

    workers = max(1, min(args.jobs, total))
    # 终端里每个下载线程一条进度条（4 线程 = 4 条堆叠）；输出被重定向时退回"每 15 秒一行"
    use_bars = bool(getattr(sys.stdout, "isatty", lambda: False)())
    quiet = use_bars and workers > 1   # 并行+进度条：底部 4 行就是实时表，不再逐项刷标题
    if use_bars:
        _bars_active.set()

    def stream_getter(item: Item) -> dict:
        _throttle_api()                  # 接口调用串行 + 最小间隔，避免触发风控
        return fetch_streams(session, headers, args.timeout, item.bvid, item.cid)

    # 进度条标题会和"百分比/大小/速度/剩余时间"抢同一行宽度：按终端宽度给标题算预算，
    # 宽终端显示更长的标题，窄终端收短标题（并先丢掉最不重要的"第几个/共几个"），
    # 把宽度尽量留给进度条本身，避免计数和速度被挤掉。
    term_cols = shutil.get_terminal_size((100, 24)).columns
    head_cols = 22 if term_cols >= 84 else 12
    label_budget = max(6, min(24, term_cols - head_cols - 70))

    def work(position: int, origin: int, item: Item) -> int:
        tag = f"#{origin} "              # 用清单里的原始序号，方便对照上面那份列表
        if not quiet:
            emit(f"\n[{position}/{total}] {item.label}")
        slot = _claim_bar_slot() if use_bars else None
        if quiet:
            head = (f"[{position}/{total}] #{origin} " if term_cols >= 84
                    else f"#{origin} ")
            bar_prefix = f"{head}{_clip(item.label, label_budget)} · "
        else:
            bar_prefix = ""
        return process_item(
            session, item, headers=headers, stream_getter=stream_getter,
            timeout=args.timeout, retries=args.retries,
            use_probe=not args.no_probe, want_mp4=want_mp4, want_mp3=want_mp3,
            mp3_bitrate=args.mp3_bitrate,
            max_quality=QUALITY_LIMITS[args.quality], force=args.force,
            tag=tag, bar_position=slot, bar_prefix=bar_prefix, quiet=quiet,
            max_reconnects=args.max_reconnects,
        )

    emit(f"\n开始下载（{workers} 个线程）…")

    aborted = False
    aborting = False                     # 已被 Ctrl+C 打断：收尾时绝不再等下载线程
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dl")
    futures = {pool.submit(work, position, origin, item): (origin, item)
               for position, (origin, item) in enumerate(selected, 1)}
    try:
        # 用"带超时的轮询"而不是 as_completed 的无限等待：主线程每 0.3 秒都会回到
        # 字节码层处理挂起的信号，否则在 Windows 上卡在无限等待里会收不到 Ctrl+C。
        pending = set(futures)
        while pending:
            done, pending = futures_wait(pending, timeout=0.3)
            for future in done:
                origin, item = futures[future]
                try:
                    stats.bytes_done += future.result()
                    stats.ok += 1
                except FileExistsError:
                    stats.skipped += 1
                except Aborted:
                    aborted = True       # 用户中断：不计入失败
                except Exception as exc:  # 单个文件失败不影响整批
                    stats.failed += 1
                    stats.errors.append((item.label, short_error(exc, limit=400)))
                    emit(f"#{origin} [失败] {short_error(exc)}", err=True)
    except KeyboardInterrupt:
        request_abort()
        aborting = True
        emit("\n[中断] 已停止下载；已下载的 .part/.m4s 会保留，重跑即续传。", err=True)
        pool.shutdown(wait=False, cancel_futures=True)
        _hard_exit(130)                  # 不再等下载线程，直接退出（不返回）
    finally:
        pool.shutdown(wait=not aborting, cancel_futures=True)
    _bars_active.clear()                 # 收工后再用普通输出打总结

    elapsed = time.time() - started
    emit(f"\n[结果] 成功 {stats.ok} / 跳过 {stats.skipped} / 失败 {stats.failed}"
         f"，新增 {human_size(stats.bytes_done)}，用时 {elapsed:.1f} 秒")
    if stats.errors:
        emit("[结果] 失败明细：")
        for label, reason in stats.errors[:20]:
            emit(f"  - {label}：{reason}")
        if len(stats.errors) > 20:
            emit(f"  …另有 {len(stats.errors) - 20} 项，详见上方日志")
    emit(f"保存目录：{root.resolve()}")
    if aborted:
        emit("[中断] 已停止；已下载的 .part/.m4s 会保留，重跑即续传。")
        return 130
    return 1 if stats.failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:          # 双保险：任何漏网的中断都不打 traceback
        print("\n[中断] 已取消")
        sys.exit(130)
