"""国企/央企轨道主流程：抓取 → 0-100评分 → 去重入库 → 生成 HTML → 推送 ≥80 分新岗位

与考公轨完全隔离：独立 history json、独立 html、独立逻辑；推送在 PUSH_BATCH=1 时先暂存，
由 push_batch.py 与考公合并成一条消息；默认（不带 PUSH_BATCH）则单独推送。
整段包在 try 中，任何失败只记日志，绝不拖垮考公轨 workflow。
"""
import datetime
import os

from config import SOE_PUSH_MIN, SOE_GRADUATE, SOE_HTML_FILE
import soe_store
import soe_score
import soe_sources
import soe_html
import notifier

RECORD_MIN = 55          # >= 55 分才写入 soe_history.json（减少噪音）
MAX_PUSH = 15            # 单次推送最多条数


def _pages_url():
    """soe_history 页 URL：优先 PAGES_URL 修正，否则 GITHUB_REPOSITORY 自动构造"""
    url = os.getenv("PAGES_URL", "").strip()
    if url and "deployments/github-pages" in url:
        url = ""
    if url:
        return url
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/guoqi_history.html"
    return ""


def _footer(pages_url):
    if pages_url:
        return f"\n\n📊 完整国企/央企记录（含已过期）：{pages_url}"
    return "\n\n📊 完整国企/央企记录：请在 GitHub Actions 运行结果的 Artifacts 中下载 guoqi_history.html 查看"


def _region_label(j):
    city = j.get("s_city") or j.get("city") or ""
    return f"{city}" if city else "工作地以公告为准"


def _build_push_text(new_jobs, pages_url):
    lines = [f"目标：北工大生物医学工程 · {SOE_GRADUATE}应届 · 国企/央企研发技术岗"]
    for idx, j in enumerate(new_jobs[:MAX_PUSH], 1):
        lines.append("")
        lines.append(f"{idx}. 【{j.get('s_score', 0)}分】{j.get('title', '')}")
        lines.append(f"   类别：{j.get('s_badge', '其他')}　地点：{_region_label(j)}")
        lines.append(f"   来源：{j.get('source', '')}")
        lines.append(f"   {j.get('link', '')}")
    if len(new_jobs) > MAX_PUSH:
        lines.append(f"\n…另有 {len(new_jobs) - MAX_PUSH} 条，见完整记录。")
    if pages_url:
        lines.append(f"\n📊 完整国企/央企记录：{pages_url}")
    return "\n".join(lines)


def main():
    try:
        today = datetime.date.today().isoformat()
        history, removed = soe_store.purge(soe_store.load(), today)
        if removed:
            print(f"[soe] 已清理过期岗位 {removed} 个", flush=True)
        known = soe_store.known_ids(history)

        candidates = soe_sources.run_all()
        new_records, new_to_push = [], []
        for rec in candidates:
            soe_score.score_job(rec)
            if rec.get("s_score", 0) < RECORD_MIN:
                continue
            if rec.get("s_corp_pts", 0) < 12:   # 非央企/国企/地方国企不入库
                continue
            rec["unique_id"] = soe_store.uid(rec)
            if rec["unique_id"] in known:
                continue
            known.add(rec["unique_id"])
            rec["fetched_at"] = today
            if not rec.get("status"):
                st, days = soe_score.validity(rec.get("publish_date"), rec.get("deadline"), today)
                rec["status"], rec["days_left"] = st, days
            history["jobs"].append(rec)
            new_records.append(rec)
            if rec.get("s_score", 0) >= SOE_PUSH_MIN and rec.get("status") != "expired":
                new_to_push.append(rec)

        print(f"[soe] 新增记录 {len(new_records)}，满足推送 {len(new_to_push)}", flush=True)
        soe_store.save(history)

        soe_html.render(history, today)

        try:
            pages_url = _pages_url()
            if new_to_push:
                new_to_push.sort(key=lambda x: (-int(x.get("s_score", 0)), int(x.get("days_left", 999))))
                title = f"🏭 国企/央企今日新增匹配 {len(new_to_push)} 个（最高 {max(int(j.get('s_score', 0)) for j in new_to_push)}分）"
                notifier.push(title, _build_push_text(new_to_push, pages_url))
            else:
                notifier.push("🏭 今日无新增国企/央企匹配岗位",
                              f"今日抓取 {len(candidates)} 条候选，未发现 ≥{SOE_PUSH_MIN} 分的新岗位。"
                              f"{_footer(pages_url)}")
        except Exception as e:
            print(f"[soe] 推送异常（不影响 HTML 生成）: {e}", flush=True)

        print("[soe] 全部完成", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[soe] 主流程异常（已捕获，不影响考公轨）: {e}", flush=True)


if __name__ == "__main__":
    main()
