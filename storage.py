"""history.json 读写与去重"""
import json
import os

from config import HISTORY_FILE
from utils import atomic_write_text, log


class HistoryError(RuntimeError):
    """历史文件损坏且备份不可用；宁可让任务失败也不要静默清空。"""


def empty_history():
    return {"jobs": []}


def _validate(data):
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("history 结构必须是 {'jobs': [...]}")
    return data


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return _validate(json.load(f))


def load_history(path=HISTORY_FILE):
    backup = path + ".bak"
    if not os.path.exists(path):
        if os.path.exists(backup):
            try:
                data = _read(backup)
                log(f"[storage] 主历史文件缺失，已使用备份 {backup}")
                return data
            except Exception as e:
                raise HistoryError(f"主历史文件缺失且备份不可用: {backup}: {e}") from e
        return empty_history()
    try:
        return _read(path)
    except Exception as e:
        if os.path.exists(backup):
            try:
                data = _read(backup)
                log(f"[storage] 历史文件损坏，已回退到备份 {backup}: {e}")
                return data
            except Exception as backup_error:
                raise HistoryError(
                    f"历史文件与备份均不可用: {path}: {e}; {backup}: {backup_error}") from backup_error
        raise HistoryError(f"历史文件损坏且无备份，请人工检查: {path}: {e}") from e


def save_history(data, path=HISTORY_FILE):
    _validate(data)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    backup = path + ".bak"
    # 备份上一份「可解析」的主文件；主文件损坏时不要覆盖仍然可用的旧备份
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                previous = f.read()
            try:
                _validate(json.loads(previous))
                atomic_write_text(backup, previous)
            except Exception:
                log("[storage] 当前主文件不可解析，保留既有备份不覆盖")
        elif not os.path.exists(backup):
            atomic_write_text(backup, text)
    except Exception as e:
        log(f"[storage] 写备份失败（不影响主文件）: {e}")
    atomic_write_text(path, text)


def snapshot_history(today, path=HISTORY_FILE):
    """首次迁移前留一份带日期的原始快照，便于本地恢复。"""
    if not os.path.exists(path):
        return ""
    target = f"{path}.pre-migration-{today}"
    if os.path.exists(target):
        return target
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        atomic_write_text(target, text)
        log(f"[storage] 已保存迁移前快照 {target}")
        return target
    except Exception as e:
        log(f"[storage] 迁移前快照失败: {e}")
        return ""


def known_ids(history):
    return {
        j.get("unique_id") for j in history.get("jobs", [])
        if isinstance(j, dict) and j.get("unique_id")
    }
