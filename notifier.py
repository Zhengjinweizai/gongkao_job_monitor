"""Server酱（Turbo）微信推送 — 支持多账号（多微信号）"""
import json
import os

import requests

API_URL = "https://sctapi.ftqq.com/{sendkey}.send"
PUSH_PAYLOAD = os.getenv("PUSH_PAYLOAD_FILE", "push_payload.json")


def get_keys():
    """收集所有 SERVER_CHAN_KEY* 环境变量，逗号/竖线分隔，去重返回 key 列表"""
    keys = []
    for name in sorted(os.environ):
        if name.startswith("SERVER_CHAN_KEY"):
            for part in os.environ[name].split(","):
                part = part.strip()
                if part:
                    keys.append(part)
    seen, uniq = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


def _send(title, desp):
    keys = get_keys()
    if not keys:
        print("[notifier] 未配置 SERVER_CHAN_KEY，跳过微信推送（仅本地记录）", flush=True)
        return False
    ok = True
    for idx, key in enumerate(keys, 1):
        try:
            r = requests.post(API_URL.format(sendkey=key),
                              data={"title": title, "desp": desp}, timeout=20)
            ok = ok and r.ok
            print(f"[notifier] 账号{idx} 推送 HTTP {r.status_code}: {r.text[:150]}", flush=True)
        except Exception as e:
            ok = False
            print(f"[notifier] 账号{idx} 推送失败: {e}", flush=True)
    return ok


def append_payload(track, title, desp):
    """批量模式：把一段内容写入 push_payload.json，由 push_batch.py 合并发送"""
    entries = []
    if os.path.exists(PUSH_PAYLOAD):
        try:
            with open(PUSH_PAYLOAD, "r", encoding="utf-8") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                entries = []
        except Exception:
            entries = []
    entries.append({"track": track, "title": title, "desp": desp})
    with open(PUSH_PAYLOAD, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"[notifier] 批量模式：已暂存「{track}」推送内容（累计 {len(entries)} 段）", flush=True)
    return True


def push(title, desp):
    if os.getenv("PUSH_BATCH") == "1":
        track = "国企央企" if "🏭" in title else ("考公" if "📢" in title or "📭" in title else "其他")
        return append_payload(track, title, desp)
    return _send(title, desp)


def stars(score):
    score = max(0, min(10, int(score)))
    return "⭐" * max(1, round(score / 2))


TIER_LABELS = {1: "🟦 公务员", 2: "🟩 事业编制", 3: "⚪ 其他"}


def tier_of(job):
    return int(getattr(job, "tier", 3) or 3)


def build_message(job):
    lines = [
        f"📢 【新岗位】{job.title}",
        f"（匹配度：{job.score}分 {stars(job.score)}）",
        f"📍 地点：{job.location or job.city or '详见公告'}（优先级：{job.region_label}）",
        f"🏢 单位：{job.unit or '—'}",
        f"🏷️ 类型：{job.job_type or '其他'}",
    ]
    if job.status == "expiring":
        lines.append(f"⏳ 报名截止：{job.deadline or '详见公告'}（⚠️ 仅剩 {max(1, job.days_left)} 天！）")
    elif job.deadline:
        lines.append(f"⏳ 报名截止：{job.deadline}（剩余 {max(0, job.days_left)} 天）")
    else:
        lines.append(f"⏳ 报名截止：详见公告（有效期约 {job.days_left} 天）")
    lines.append(f"🔗 公告链接：{job.link}")
    lines.append(f"✅ 匹配点：{job.match_points}")
    lines.append(f"📝 备考建议：大概率考{job.exam_advice}，建议重点复习。")
    lines.append(f"💰 薪酬参考（预估）：{job.salary_ref}")
    return "\n".join(lines)


def build_batch(jobs, pages_url=""):
    jobs = sorted(jobs, key=lambda j: (tier_of(j), -int(j.score or 0), int(j.days_left or 999)))
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
    return body
