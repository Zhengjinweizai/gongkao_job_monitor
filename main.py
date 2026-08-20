"""主流程：抓取 → 打分 → 时效过滤 → 去重 → 拉详情 → 推送 → 生成 HTML → 写历史"""
import datetime
import os

from parsers import run_all, try_extract_attachment, fetch_detail
from filters import enrich, check_validity, infer_types
from config import PUSH_MIN_SCORE, GRADUATE_DATE, REGION_HIGH, EXPIRE_PURGE_DAYS
import storage
import notifier
import generate_html

MAX_DETAIL_FETCH = 30   # 每次运行最多为高价值岗位拉取详情条数


def purge_expired(history, today):
    """按宽限期删除已过期岗位，并刷新存活岗位的 status/days_left"""
    keep = []
    removed = 0
    for j in history["jobs"]:
        status, days = check_validity(j.get("publish_date"), j.get("deadline"), today)
        j["status"] = status
        j["days_left"] = days
        if status == "expired" and days < -EXPIRE_PURGE_DAYS:
            removed += 1
            continue
        keep.append(j)
    history["jobs"] = keep
    if removed:
        print(f"[purge] 已删除过期岗位 {removed} 个（宽限 {EXPIRE_PURGE_DAYS} 天）", flush=True)
    return history


def main():
    today = datetime.date.today().isoformat()
    history = storage.load_history()
    history = purge_expired(history, today)
    for j in history["jobs"]:   # 旧数据重算档位，保证公务员/事业编置顶
        t, ty = infer_types(j.get("title", ""), j.get("unit", ""), j.get("source", ""))
        j["tier"] = t
        j["job_type"] = ty
    known = storage.known_ids(history)
    print(f"[main] 开始监控，历史已知岗位 {len(known)} 个，毕业时间 {GRADUATE_DATE}", flush=True)

    raw_jobs = run_all()
    print(f"[main] 共抓取 {len(raw_jobs)} 条原始公告", flush=True)

    new_matched = []    # 匹配度 >= 1，写入历史
    new_to_push = []    # 匹配度 >= 2 且未过期，当天推送
    detail_fetched = 0

    for job in raw_jobs:
        try:
            try_extract_attachment(job)
        except Exception as e:
            print(f"[main] 附件解析跳过: {e}", flush=True)

        enrich(job, today)

        if job.score < 1:
            continue

        uid = job.unique_id()
        if uid in known:
            continue
        known.add(uid)

        if detail_fetched < MAX_DETAIL_FETCH and (job.score >= 2 or job.region_score >= REGION_HIGH):
            try:
                fetch_detail(job)
                detail_fetched += 1
                enrich(job, today)   # 详情可能更新截止时间，重算时效/状态
            except Exception as e:
                print(f"[main] 详情抓取异常: {e}", flush=True)

        job_dict = job.to_dict()
        job_dict["fetched_at"] = today
        history["jobs"].append(job_dict)
        new_matched.append(job)

        if job.score >= PUSH_MIN_SCORE and job.status != "expired":
            new_to_push.append(job)

    print(f"[main] 新匹配岗位 {len(new_matched)} 个，满足推送条件 {len(new_to_push)} 个，拉取详情 {detail_fetched} 条", flush=True)

    storage.save_history(history)

    pages_url = os.getenv("PAGES_URL", "").strip()

    generate_html.render(history, today)

    try:
        if new_to_push:
            new_to_push.sort(key=lambda x: (x.tier, -x.score, x.days_left))
            title = f"📢 今日新增匹配岗位 {len(new_to_push)} 个（最高 {max(j.score for j in new_to_push)}分）"
            desp = notifier.build_batch(new_to_push, pages_url)
            notifier.push(title, desp)
        else:
            notifier.push("📭 今日无新增匹配岗位",
                          f"今日共抓取 {len(raw_jobs)} 条公告，未发现新的高匹配岗位。\n\n历史完整记录见 history.html。")
    except Exception as e:
        print(f"[main] 推送异常（不影响 HTML 生成）: {e}", flush=True)
    print("[main] 全部完成", flush=True)


if __name__ == "__main__":
    main()
