"""国企/央企轨道历史 soe_history.json 读写与去重"""
import hashlib
import json
import os

from config import SOE_HISTORY_FILE


def load(path=SOE_HISTORY_FILE):
    if not os.path.exists(path):
        return {"jobs": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "jobs" not in data:
            return {"jobs": []}
        return data
    except Exception as e:
        print(f"[soe_store] 读取历史失败: {e}", flush=True)
        return {"jobs": []}


def save(data, path=SOE_HISTORY_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def uid(rec):
    raw = f"{rec.get('unit', '')}|{rec.get('title', '')}|{rec.get('publish_date', '')}|{rec.get('link', '')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def known_ids(history):
    return {j.get("unique_id") for j in history["jobs"]}


def purge(history, today, grace_days=1):
    """删除过期超宽限期的岗位，并刷新存活岗位状态；返回 (history, removed)"""
    from soe_score import validity
    keep, removed = [], 0
    for j in history["jobs"]:
        status, days = validity(j.get("publish_date"), j.get("deadline"), today)
        j["status"] = status
        j["days_left"] = days
        if status == "expired" and days < -grace_days:
            removed += 1
            continue
        keep.append(j)
    history["jobs"] = keep
    return history, removed
