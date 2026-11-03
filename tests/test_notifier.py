"""Server酱 推送与消息组装测试"""

import notifier


def test_get_keys_multi_account_and_separators(clean_env):
    clean_env.setenv("SERVER_CHAN_KEY", "a, b")
    clean_env.setenv("SERVER_CHAN_KEY_2", "b|c")
    clean_env.setenv("SERVER_CHAN_KEY_X", "ignored")
    assert notifier.get_keys() == ["a", "b", "c"]


def test_get_keys_empty(clean_env):
    assert notifier.get_keys() == []


def test_push_without_keys(clean_env):
    assert notifier.push("t", "d") is False


def _fake_post(monkeypatch, *responses):
    calls = []

    def post(url, data=None, timeout=None, **kwargs):
        calls.append((url, data, timeout))
        item = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(notifier.requests, "post", post)
    return calls


def test_push_success(clean_env, fake_response, monkeypatch):
    clean_env.setenv("SERVER_CHAN_KEY", "k1")
    calls = _fake_post(monkeypatch, fake_response(
        json_data={"code": 0, "data": {"errno": 0}}, text="ok"))
    assert notifier.push("标题", "正文") is True
    assert calls[0][0] == "https://sctapi.ftqq.com/k1.send"
    assert calls[0][1] == {"title": "标题", "desp": "正文"}
    assert calls[0][2] == 20


def test_push_business_code_failure_is_false(clean_env, fake_response, monkeypatch, capsys):
    clean_env.setenv("SERVER_CHAN_KEY", "k1")
    _fake_post(monkeypatch, fake_response(
        200, json_data={"code": 40001, "message": "超过发送次数"}, text="quota"))
    assert notifier.push("t", "d") is False
    assert "code=40001" in capsys.readouterr().out


def test_push_http_failure_and_exception(clean_env, fake_response, monkeypatch):
    clean_env.setenv("SERVER_CHAN_KEY", "k1")
    _fake_post(monkeypatch, fake_response(500, json_error=True))
    assert notifier.push("t", "d") is False
    _fake_post(monkeypatch, RuntimeError("boom"))
    assert notifier.push("t", "d") is False


def test_push_multiple_accounts(clean_env, fake_response, monkeypatch):
    clean_env.setenv("SERVER_CHAN_KEY", "k1")
    clean_env.setenv("SERVER_CHAN_KEY_2", "k2")
    calls = _fake_post(monkeypatch,
                       fake_response(json_data={"code": 0}),
                       fake_response(json_data={"code": 40001}))
    assert notifier.push("t", "d") is False
    assert [c[0] for c in calls] == [
        "https://sctapi.ftqq.com/k1.send",
        "https://sctapi.ftqq.com/k2.send",
    ]


def test_push_non_json_200_is_tolerated(clean_env, fake_response, monkeypatch):
    clean_env.setenv("SERVER_CHAN_KEY", "k1")
    _fake_post(monkeypatch, fake_response(200, json_error=True))
    assert notifier.push("t", "d") is True


def test_tier_of_handles_dict_and_bad_values():
    assert notifier.tier_of({"tier": 1}) == 1
    assert notifier.tier_of({"tier": None}) == 3
    assert notifier.tier_of({"tier": "2"}) == 2
    assert notifier.tier_of({"tier": 9}) == 3
    assert notifier.tier_of(object()) == 3


def test_build_message_branches(make_job):
    expiring = make_job(status="expiring", days_left=0, deadline="2026-11-03")
    body = notifier.build_message(expiring)
    assert "仅剩 1 天" in body
    assert "公告链接" in body

    active = make_job(status="active", days_left=7, deadline="2026-11-10")
    assert "剩余 7 天" in notifier.build_message(active)

    undated = make_job(status="active", days_left=30, deadline="")
    assert "有效期约 30 天" in notifier.build_message(undated)


def test_build_batch_sorts_and_groups(make_job):
    civil = make_job(title="公务员招录", tier=1, score=8, days_left=5)
    inst_late = make_job(title="事业编 A", tier=2, score=5, days_left=9)
    inst_soon = make_job(title="事业编 B", tier=2, score=5, days_left=0)
    body = notifier.build_batch([inst_late, civil, inst_soon], "https://example.com/history.html")
    assert body.index("🟦 公务员") < body.index("🟩 事业编制")
    assert body.index("事业编 B") < body.index("事业编 A")
    assert "https://example.com/history.html" in body
    assert "Artifacts" in notifier.build_batch([civil], "")


def test_build_batch_truncates_long_body(make_job):
    jobs = [make_job(title=f"岗位{i}招聘公告", link=f"https://x/{i}") for i in range(100)]
    body = notifier.build_batch(jobs, "https://example.com/history.html")
    assert len(body) <= notifier.MAX_DESP_CHARS + 100
    assert "已截断" in body
