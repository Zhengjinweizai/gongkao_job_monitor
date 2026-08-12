"""history.json 读写与去重"""
import json
import os

from config import HISTORY_FILE


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {"jobs": []}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "jobs" not in data:
            return {"jobs": []}
        return data
    except Exception as e:
        print(f"[storage] 读取历史失败: {e}", flush=True)
        return {"jobs": []}


def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def known_ids(history):
    return {j.get("unique_id") for j in history["jobs"]}
