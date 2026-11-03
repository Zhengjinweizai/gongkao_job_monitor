"""Server酱（Turbo）微信推送 — 支持多账号（多微信号）"""
import os
import re

import requests

from utils import log, stars, to_int

API_URL = "https://sctapi.ftqq.com/{sendkey}.send"
MAX_DESP_CHARS = 3500
KEY_NAME_RE = re.compile(r"^SERVER_CHAN_KEY(?:_\d+)?$")


def get_keys():
    """收集所有 SERVER_CHAN_KEY / SERVER_CHAN_KEY_<n> 环境变量，逗号/竖线分隔，去重。"""
    keys = []
    for name in sorted(os.environ):
        if not KEY_NAME_RE.match(name):
            continue
        for part in re.split(r"[,|]", os.environ[name]):
            part = part.strip()
            if part:
                keys.append(part)
    seen, uniq = set(), []
    for key in keys:
        if key not in seen:
            seen.add(key)
            uniq.append(key)
    return uniq


def _redact(text, key):
    return str(text).replace(key, "***")


def _response_ok(response, key):
    """Server酱 配额/无效 key 时返回 HTTP 200 + code != 0，必须看业务码。"""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    code = None
    errno = None
    if isinstance(payload, dict):
        code = payload.get("code")
        data = payload.get("data")
        if isinstance(data, dict):
            errno = data.get("errno")
    ok = bool(response.ok)
    if code is not None:
        ok = ok and str(code) == "0"
    if errno is not None:
        ok = ok and str(errno) == "0"
    if not ok:
        detail = ""
        if isinstance(payload, dict):
            detail = payload.get("message") or ""
        log(f"[notifier] 推送失败（业务码 code={code} errno={errno}）: {_redact(detail, key)[:150]}")
    return ok


def push(title, desp):
    keys = get_keys()
    if not keys:
        log("[notifier] 未配置 SERVER_CHAN_KEY，跳过微信推送（仅本地记录）")
        return False
    ok = True
    for idx, key in enumerate(keys, 1):
        try:
            r = requests.post(API_URL.format(sendkey=key),
                              data={"title": title, "desp": desp}, timeout=20)
            account_ok = _response_ok(r, key)
            ok = ok and account_ok
            log(f"[notifier] 账号{idx} 推送 HTTP {r.status_code}: "
                f"{_redact(r.text[:150], key)}")
        except Exception as e:
            ok = False
            log(f"[notifier] 账号{idx} 推送异常: {_redact(e, key)}")
    return ok


TIER_LABELS = {1: "🟦 公务员", 2: "🟩 事业编制", 3: "⚪ 其他"}


def _field(job, name, default=None):
    if isinstance(job, dict):
        return job.get(name, default)
    return getattr(job, name, default)


def tier_of(job):
    try:
        value = int(_field(job, "tier", 3) or 3)
    except (TypeError, ValueError):
        value = 3
    return value if value in TIER_LABELS else 3


def _days_left(job):
    value = _field(job, "days_left")
    return 999 if value is None else to_int(value, 999)


def build_message(job):
    days_left = to_int(_field(job, "days_left"), 0)
    lines = [
        f"📢 【新岗位】{_field(job, 'title', '')}",
        f"（匹配度：{to_int(_field(job, 'score'), 0)}分 {stars(_field(job, 'score', 0))}）",
        f"📍 地点：{_field(job, 'location') or _field(job, 'city') or '详见公告'}（优先级：{_field(job, 'region_label') or '普通'}）",
        f"🏢 单位：{_field(job, 'unit') or '—'}",
        f"🏷️ 类型：{_field(job, 'job_type') or '其他'}",
    ]
    if _field(job, "status") == "expiring":
        lines.append(f"⏳ 报名截止：{_field(job, 'deadline') or '详见公告'}（⚠️ 仅剩 {max(1, days_left)} 天！）")
    elif _field(job, "deadline"):
        lines.append(f"⏳ 报名截止：{_field(job, 'deadline')}（剩余 {max(0, days_left)} 天）")
    else:
        lines.append(f"⏳ 报名截止：详见公告（有效期约 {days_left} 天）")
    lines.append(f"🔗 公告链接：{_field(job, 'link', '')}")
    lines.append(f"✅ 匹配点：{_field(job, 'match_points', '')}")
    lines.append(f"📝 备考建议：大概率考{_field(job, 'exam_advice', '')}，建议重点复习。")
    lines.append(f"💰 薪酬参考（预估）：{_field(job, 'salary_ref', '')}")
    return "\n".join(lines)


def build_batch(jobs, pages_url=""):
    jobs = sorted(jobs, key=lambda j: (tier_of(j), -to_int(_field(j, "score"), 0), _days_left(j)))
    parts = []
    cur = None
    for j in jobs:
        t = tier_of(j)
        if t != cur:
            cur = t
            parts.append(f"《{TIER_LABELS.get(t, '其他')}》")
        parts.append(build_message(j))
    body = "\n\n".join(parts)
    if pages_url:
        body += f"\n\n📊 完整历史记录（含已过期岗位）：{pages_url}"
    else:
        body += "\n\n📊 完整历史记录：请在 GitHub Actions 运行结果的 Artifacts 中下载 history.html 查看（或配置 PAGES_URL 变量后开启 GitHub Pages）"
    if len(body) > MAX_DESP_CHARS:
        body = body[:MAX_DESP_CHARS] + "\n\n…（内容过长，已截断；完整记录见历史页）"
    return body
