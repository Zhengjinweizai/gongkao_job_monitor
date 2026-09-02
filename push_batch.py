"""合并推送：读取 push_payload.json（考公+国企央企两段），合成一条 Server酱 消息发送。
用于 monitor.yml：main.py 与 soe_main.py 以 PUSH_BATCH=1 先暂存，本脚本统一发一次。
发送后清空 payload，避免下次重复推送。
"""
import json
import os

import notifier

PAYLOAD = os.getenv("PUSH_PAYLOAD_FILE", "push_payload.json")
MAX_LEN = 14000


def load():
    if not os.path.exists(PAYLOAD):
        return []
    try:
        with open(PAYLOAD, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[push_batch] 读取 payload 失败: {e}", flush=True)
        return []


def clear():
    try:
        os.remove(PAYLOAD)
    except OSError:
        pass


def compose(entries):
    if len(entries) == 1:
        return entries[0]["title"], entries[0]["desp"]
    title = "📢 每日岗位推送汇总（考公 + 国企央企）"
    parts = []
    for en in entries:
        head = f"▶ {en.get('track', '其他')}：{en.get('title', '')}"
        parts.append(head + "\n\n" + en.get("desp", ""))
    desp = "\n\n━━━━━━━━━━━━━━━━━━\n\n".join(parts)
    if len(desp) > MAX_LEN:
        desp = desp[:MAX_LEN] + "\n\n…（内容较长已截断，完整明细见 history.html / guoqi_history.html）"
    return title, desp


def main():
    entries = load()
    if not entries:
        print("[push_batch] 无待合并内容（payload 为空），跳过推送", flush=True)
        return
    title, desp = compose(entries)
    ok = notifier._send(title, desp)
    clear()
    print(f"[push_batch] 合并 {len(entries)} 段推送完成，发送成功={ok}", flush=True)


if __name__ == "__main__":
    main()
