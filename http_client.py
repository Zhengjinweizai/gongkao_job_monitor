"""统一 HTTP 层：忽略坏代理、自动重试、Reader 兜底"""
import os
import random
import socket
import time

import requests

from config import ATTACHMENT_TIMEOUT, HTTP_TIMEOUT
from utils import log

DEFAULT_READER_PROXY = "https://r.jina.ai/"
ANTI_BOT_STATUS = {403, 412}
RETRYABLE_STATUS = {408, 425, 429}
MAX_RETRY_AFTER = 30
DEFAULT_MAX_DOWNLOAD = 15 * 1024 * 1024

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]


def force_ipv4():
    """优先 IPv4 解析，规避 GitHub runner 无 IPv6 出口导致的 Network unreachable"""
    try:
        import urllib3.util.connection as _uc
        _uc.HAS_IPV6 = False
    except Exception:
        pass
    try:
        socket.setdefaulttimeout(30)
    except Exception:
        pass


def fetch_proxy():
    return os.getenv("FETCH_PROXY", "").strip()


def reader_proxy():
    # 注意：未定义的 Actions variable 会以空字符串注入，必须用 `or` 回落到默认值
    return (os.getenv("READER_PROXY") or DEFAULT_READER_PROXY).strip()


def browser_headers(referer=""):
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }
    if referer:
        h["Referer"] = referer
    return h


def _new_session(ua=True):
    s = requests.Session()
    s.trust_env = False
    if ua:
        s.headers.update(browser_headers())
    proxy = fetch_proxy()
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    return s


_session = None


def get_session():
    global _session
    if _session is None:
        _session = _new_session()
    return _session


def reset_session():
    global _session
    _session = None


def _reader_url(url, proxy=None):
    proxy = proxy if proxy is not None else reader_proxy()
    if not proxy:
        return ""
    if "{url}" in proxy:
        return proxy.format(url=url)
    return proxy + url


def _reader_fetch(url, timeout):
    """直连失败后经第三方 Reader 兜底抓取（返回 markdown 文本）。

    Reader 返回的是 UTF-8 markdown，不能套用原站点的 GBK 编码。
    """
    proxy = reader_proxy()
    if not proxy:
        return None
    try:
        s = _new_session(ua=False)
        r = s.get(_reader_url(url, proxy), timeout=timeout + 20)
        if r.status_code == 200 and len(r.text or "") > 300:
            r.is_markdown = True
            return r
        log(f"[http] reader 兜底异常状态 {r.status_code}: {url}")
    except Exception as e:
        log(f"[http] reader 兜底失败 {url}: {_safe_error(e)}")
    return None


def _safe_error(exc):
    """异常信息可能带 SendKey/代理口令，日志中做脱敏。"""
    text = str(exc)
    for name in ("SERVER_CHAN_KEY", "FETCH_PROXY"):
        value = os.getenv(name, "")
        if value:
            text = text.replace(value, "***")
    return text


def _fetch_once(sess, method, url, timeout, headers=None, **kw):
    r = sess.request(method, url, headers=headers, timeout=timeout, **kw)
    if r.status_code in ANTI_BOT_STATUS:
        raise requests.HTTPError(f"{r.status_code} WAF/anti-bot for {url}", response=r)
    r.raise_for_status()
    return r


def _retry_after(response):
    if response is None:
        return None
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0, min(MAX_RETRY_AFTER, int(value)))
    except (TypeError, ValueError):
        return None


def _request_retry(method, url, timeout, headers=None, encoding=None,
                   reader_fallback=True, retries=3, **kw):
    sess = get_session()
    last = None
    for attempt in range(retries):
        try:
            r = _fetch_once(sess, method, url, timeout, headers=headers, **kw)
            if encoding:
                r.encoding = encoding
            return r
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in ANTI_BOT_STATUS:
                last = e
                break  # 反爬 4xx 重试无意义，直接交给 reader 兜底
            if code in RETRYABLE_STATUS:
                last = e
                if attempt + 1 < retries:
                    time.sleep(_retry_after(e.response)
                               or (1.2 ** attempt + random.uniform(0, 0.5)))
                continue
            if 400 <= code < 500:
                raise  # 404 等确定性错误不重试
            last = e
        except Exception as e:
            last = e
        if attempt + 1 < retries:
            time.sleep(1.2 ** attempt + random.uniform(0, 0.5))
    if reader_fallback:
        rr = _reader_fetch(url, timeout)
        if rr is not None:
            log(f"[http] 直连失败，已用 reader 兜底 {url}")
            return rr
    if last is None:
        raise requests.ConnectionError(f"direct fetch failed: {url}")
    raise last


def http_get(url, timeout=HTTP_TIMEOUT, encoding=None, headers=None, reader_fallback=True):
    return _request_retry("GET", url, timeout, headers=headers,
                          encoding=encoding, reader_fallback=reader_fallback)


def http_post(url, data=None, timeout=HTTP_TIMEOUT, headers=None):
    return _request_retry("POST", url, timeout, headers=headers,
                          data=data, reader_fallback=False)


def http_download(url, timeout=ATTACHMENT_TIMEOUT, max_bytes=DEFAULT_MAX_DOWNLOAD):
    r = _request_retry("GET", url, timeout, reader_fallback=False)
    content = r.content
    if len(content) > max_bytes:
        raise ValueError(f"附件超过大小限制 {max_bytes} 字节: {url}")
    return content
