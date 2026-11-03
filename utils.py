"""通用工具：日志、星级、URL 规范化与原子写入"""
import datetime
import hashlib
import os
import re
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 去重时忽略的跟踪参数（保留真正决定内容的查询参数）
TRACKING_QUERY_KEYS = {"from", "source", "spm", "ref", "referer"}


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def stars(score):
    score = max(0, min(10, to_int(score)))
    return "⭐" * max(1, round(score / 2))


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def md5_hex(text):
    return hashlib.md5(str(text).encode("utf-8")).hexdigest()


def redact(text):
    """日志/告警中脱敏 Server酱 key 与代理口令。"""
    text = str(text)
    for name in ("SERVER_CHAN_KEY", "FETCH_PROXY"):
        for key in os.environ:
            if key.startswith(name) and os.environ.get(key):
                text = text.replace(os.environ[key], "***")
    return text


def canonicalize_url(url):
    """规范化 URL 作为去重标识；非法/非 http(s) 链接返回空字符串。"""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError:
        return ""
    if scheme not in ("http", "https") or not host:
        return ""
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_QUERY_KEYS
    ))
    return urlunsplit((scheme, netloc, path, query, ""))


def safe_url(url):
    """仅允许 http(s) 链接进入 HTML/附件，阻止 javascript: 等协议。"""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return ""
    return url


def atomic_write_text(path, text):
    """同目录临时文件 + fsync + os.replace，避免进程中断留下半截文件。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
