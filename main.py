"""主流程：抓取 → 迁移/去重 → 打分 → 时效过滤 → 拉详情 → 推送 → 生成 HTML → 写历史"""
import datetime
import os
import time
from zoneinfo import ZoneInfo

import generate_html
import notifier
import storage
from config import (
    EXPIRE_PURGE_DAYS,
    GRADUATE_DATE,
    MAX_ATTACHMENT_JOBS,
    MAX_ATTACHMENT_PARSE,
    MAX_DETAIL_FETCH,
    PUSH_MIN_SCORE,
    RUN_TIME_BUDGET_SECONDS,
    TIMEZONE,
)
from details import fetch_detail, is_attachment_url, parse_attachments
from filters import check_validity, enrich, parse_date
from models import Job
from parsers import run_all
from utils import log, redact, to_int

# 高校人才网的列表栏目名曾被写进 unit；迁移时移到 category
GAOXIAOJOB_LABELS = {"甘肃", "陕西", "西安", "兰州", "高校招聘",
                     "中小学校", "医学人才", "政府与事业单位"}


def _today():
    try:
        return datetime.datetime.now(ZoneInfo(TIMEZONE)).date()
    except Exception:
        return datetime.date.today()


def _as_date(value):
    if value is None:
        return _today()
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return parse_date(value) or _today()


def resolve_pages_url():
    """确定历史记录页地址：PAGES_URL 优先，否则由 GITHUB_REPOSITORY 自动构造。"""
    url = os.getenv("PAGES_URL", "").strip()
    if url and "deployments/github-pages" in url:
        url = ""
    if url:
        return url
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if "/" in repo:
        owner, name = repo.split("/", 1)
        if name.endswith(".github.io"):
            return f"https://{name}/history.html"
        return f"https://{owner}.github.io/{name}/history.html"
    return ""


def _quality(job):
    # 同一 URL/年份的重复记录优先保留最近一次观测到的标题与截止日期
    fetched = job.get("fetched_at")
    return (job.get("status") == "expired",
            fetched if isinstance(fetched, str) else "",
            to_int(job.get("score"), 0),
            1 if job.get("deadline") else 0,
            1 if job.get("major_req") else 0)


def _merge_jobs(base, other):
    """合并同一 URL 的重复记录：保留信息更全的一条，补空字段。"""
    if _quality(other) > _quality(base):
        base, other = other, base
    merged = dict(base)
    for key, value in other.items():
        if key in ("fetched_at", "first_seen"):
            if isinstance(value, str) and value:
                current = merged.get(key)
                if not isinstance(current, str) or not current or value < current:
                    merged[key] = value
        elif key == "attachments":
            existing = merged.get(key) if isinstance(merged.get(key), list) else []
            incoming = value if isinstance(value, list) else []
            merged[key] = list(dict.fromkeys(
                x for x in existing + incoming if isinstance(x, str)
            ))
        elif key != "unique_id" and not merged.get(key) and value:
            merged[key] = value
    return merged


def _merge_job_objects(base, other):
    return Job.from_dict(_merge_jobs(base.to_dict(), other.to_dict()))


def _normalise_history_job(raw, today):
    d = dict(raw)
    if d.get("source") == "高校人才网" and d.get("unit") in GAOXIAOJOB_LABELS:
        if not d.get("category"):
            d["category"] = d.get("unit")
        d["unit"] = ""
    fetched = d.get("fetched_at")
    d["fetched_at"] = fetched if isinstance(fetched, str) else (str(fetched) if fetched else "")
    d["first_seen"] = d.get("first_seen") or d["fetched_at"] or d.get("publish_date") or today
    job = Job.from_dict(d)
    enrich(job, today, fallback_date=d["first_seen"])
    out = job.to_dict()
    out["fetched_at"] = d.get("fetched_at") or d["first_seen"]
    return out


def prepare_history(history, today):
    """迁移 unique_id、按规范化 URL 去重，并用新规则重算历史打分/时效。"""
    raw_jobs = history.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []
    merged, order = {}, []
    dropped = 0
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        try:
            job = _normalise_history_job(raw, today)
        except Exception as e:
            log(f"[main] 历史记录刷新失败，已跳过: {e}")
            dropped += 1
            continue
        uid = job["unique_id"]
        if uid in merged:
            merged[uid] = _merge_jobs(merged[uid], job)
        else:
            merged[uid] = job
            order.append(uid)
    collapsed = len(raw_jobs) - len(order)
    history["jobs"] = [merged[uid] for uid in order]
    if raw_jobs and not history["jobs"]:
        raise ValueError("历史迁移失败：所有记录均无法解析，拒绝用空历史覆盖原文件")
    if collapsed or dropped:
        log(f"[main] 历史迁移：合并重复 {max(0, collapsed - dropped)} 条，跳过异常 {dropped} 条，"
            f"现有 {len(history['jobs'])} 条")
    return history


def purge_expired(history, today):
    """按宽限期删除已过期岗位，并刷新存活岗位的 status/days_left"""
    if isinstance(today, str):
        today = _as_date(today)
    keep = []
    removed = 0
    for j in history["jobs"]:
        fallback = j.get("first_seen") or j.get("fetched_at")
        status, days = check_validity(j.get("publish_date"), j.get("deadline"), today, fallback)
        j["status"] = status
        j["days_left"] = days
        if status == "expired" and days < -EXPIRE_PURGE_DAYS:
            removed += 1
            continue
        keep.append(j)
    history["jobs"] = keep
    if removed:
        log(f"[purge] 已删除过期岗位 {removed} 个（宽限 {EXPIRE_PURGE_DAYS} 天）")
    return history


def _source_summary(report):
    return "\n".join(
        f"- {item['name']}：{item['count']} 条" +
        (f"（失败：{redact(item['error'])}）" if item.get("error") else "")
        for item in report
    )


def main(today=None):
    today_date = _as_date(today)
    today_s = today_date.isoformat()
    history = storage.load_history()
    raw_history_jobs = history.get("jobs") if isinstance(history.get("jobs"), list) else []
    if any(not isinstance(j, dict) or "first_seen" not in j for j in raw_history_jobs):
        storage.snapshot_history(today_s)
    history = prepare_history(history, today_s)
    history = purge_expired(history, today_date)
    # 先落盘迁移/清理结果：即使后续抓取超时，上一版历史也已备份到 .bak
    storage.save_history(history)
    known = storage.known_ids(history)
    log(f"[main] 开始监控，历史已知岗位 {len(known)} 个，毕业时间 {GRADUATE_DATE}")

    raw_jobs, report = run_all(return_report=True)
    log(f"[main] 共抓取 {len(raw_jobs)} 条原始公告")
    log("[main] 数据源健康度：\n" + _source_summary(report))

    new_matched = []    # 匹配度 >= 1，写入历史
    new_to_push = []    # 匹配度 >= 2 且未过期，当天推送
    candidates = {}
    detail_attempts = 0
    detail_success = 0
    attachment_jobs = 0
    scanned = 0
    skipped_expired = 0
    skipped_low = 0
    started = time.monotonic()

    for raw in raw_jobs:
        if not isinstance(raw, Job):
            try:
                job = Job.from_dict(raw)
            except Exception as e:
                log(f"[main] 非法岗位数据已跳过: {e}")
                continue
        else:
            job = raw
        scanned += 1
        job.first_seen = job.first_seen or today_s
        enrich(job, today_s, fallback_date=job.first_seen)

        uid = job.unique_id()
        if uid in candidates:
            # 同一次抓取内同一 URL/年份出现多次：合并字段，避免丢掉更全的第二条
            merged = _merge_job_objects(candidates[uid], job)
            enrich(merged, today_s, fallback_date=merged.first_seen)
            candidates[uid] = merged
            continue
        if uid in known:
            continue

        # 明确写了已过截止日期的直接跳过；仅“推定过期”的仍允许读详情确认真实截止日期
        if job.status == "expired" and job.deadline:
            skipped_expired += 1
            continue

        direct_attachment = is_attachment_url(job.link)
        if job.score < 1 and not direct_attachment:
            skipped_low += 1
            continue

        known.add(uid)
        candidates[uid] = job

    # 可报岗位优先；同状态下高匹配优先消耗详情/附件预算
    ordered = sorted(candidates.values(),
                     key=lambda j: (j.status == "expired", -j.score, -j.region_score))

    for job in ordered:
        direct_attachment = is_attachment_url(job.link)
        if not direct_attachment and \
                detail_attempts < MAX_DETAIL_FETCH and \
                time.monotonic() - started < RUN_TIME_BUDGET_SECONDS:
            detail_attempts += 1
            try:
                if fetch_detail(job):
                    detail_success += 1
                    enrich(job, today_s, fallback_date=job.first_seen)
            except Exception as e:
                log(f"[main] 详情处理异常 {job.link}: {e}")

        # 详情页里收集到的岗位表附件（以及直接指向 PDF/XLS 的链接）
        if (is_attachment_url(job.link) or job.attachments) and \
                attachment_jobs < MAX_ATTACHMENT_JOBS and \
                time.monotonic() - started < RUN_TIME_BUDGET_SECONDS:
            attachment_jobs += 1
            try:
                if parse_attachments(job, max_count=MAX_ATTACHMENT_PARSE):
                    enrich(job, today_s, fallback_date=job.first_seen)
            except Exception as e:
                log(f"[main] 附件处理异常 {job.link}: {e}")

        if job.status == "expired":
            skipped_expired += 1
            continue
        if job.score < 1:
            skipped_low += 1
            continue

        job_dict = job.to_dict()
        job_dict["fetched_at"] = today_s
        history["jobs"].append(job_dict)
        new_matched.append(job)

        if job.score >= PUSH_MIN_SCORE:
            new_to_push.append(job)
        # 每 10 条落盘一次：即使后续富化超时被取消，已确认岗位也不会丢
        if len(new_matched) % 10 == 0:
            try:
                storage.save_history(history)
            except Exception as e:
                log(f"[main] 中途落盘失败（继续处理）: {e}")

    log(f"[main] 新匹配岗位 {len(new_matched)} 个，满足推送条件 {len(new_to_push)} 个，"
        f"详情尝试 {detail_attempts} 次（成功 {detail_success}），"
        f"附件解析 {attachment_jobs} 个岗位，跳过过期 {skipped_expired} 条，低匹配 {skipped_low} 条")

    storage.save_history(history)
    pages_url = resolve_pages_url()
    generate_html.render(history, today_s, pages_url=pages_url)

    healthy = [item for item in report if item.get("count", 0) > 0]
    try:
        if new_to_push:
            new_to_push.sort(key=lambda x: (x.tier, -x.score, x.days_left))
            title = f"📢 今日新增匹配岗位 {len(new_to_push)} 个（最高 {max(j.score for j in new_to_push)}分）"
            desp = notifier.build_batch(new_to_push, pages_url)
            if not notifier.push(title, desp):
                log("[main] 微信推送未全部成功，请检查 Server酱 配额/密钥")
        elif not healthy:
            title = "⚠️ 今日抓取异常：所有数据源均无结果"
            desp = ("本次运行没有从任何数据源拿到公告，已保留原历史记录。\n\n"
                    "数据源状态：\n" + _source_summary(report))
            if pages_url:
                desp += f"\n\n📊 历史记录：{pages_url}"
            notifier.push(title, desp)
        else:
            desp = (f"今日共抓取 {len(raw_jobs)} 条公告，未发现新的高匹配岗位。\n\n"
                    f"📊 完整历史记录：{pages_url}" if pages_url else
                    f"今日共抓取 {len(raw_jobs)} 条公告，未发现新的高匹配岗位。\n\n"
                    f"历史完整记录见 history.html。")
            notifier.push("📭 今日无新增匹配岗位", desp)
    except Exception as e:
        log(f"[main] 推送异常（不影响 HTML 生成）: {e}")
    log("[main] 全部完成")
    return {
        "today": today_s,
        "scanned": scanned,
        "new": len(new_matched),
        "pushed": len(new_to_push),
        "sources": report,
        "history": len(history["jobs"]),
    }


if __name__ == "__main__":
    main()
