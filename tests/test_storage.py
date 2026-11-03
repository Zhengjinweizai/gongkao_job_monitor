"""history.json 持久化测试"""
import json

import pytest

import storage


def test_load_missing_returns_empty(tmp_path):
    assert storage.load_history(str(tmp_path / "missing.json")) == {"jobs": []}


def test_save_and_load_roundtrip_unicode(tmp_path):
    path = tmp_path / "history.json"
    data = {"jobs": [{"title": "天水岗位", "unique_id": "abc"}]}
    storage.save_history(data, str(path))
    assert storage.load_history(str(path)) == data
    assert "天水" in path.read_text(encoding="utf-8")
    assert path.with_name("history.json.bak").exists()


def test_load_falls_back_to_backup(tmp_path, capsys):
    path = tmp_path / "history.json"
    storage.save_history({"jobs": [{"unique_id": "good"}]}, str(path))
    path.write_text("{broken", encoding="utf-8")
    assert storage.load_history(str(path)) == {"jobs": [{"unique_id": "good"}]}
    assert "已回退到备份" in capsys.readouterr().out


def test_load_corrupt_without_backup_raises(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(storage.HistoryError):
        storage.load_history(str(path))


def test_load_invalid_schema_raises(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"jobs": None}), encoding="utf-8")
    with pytest.raises(storage.HistoryError):
        storage.load_history(str(path))
    path.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(storage.HistoryError):
        storage.load_history(str(path))


def test_save_rejects_invalid_schema(tmp_path):
    with pytest.raises(ValueError):
        storage.save_history({"jobs": None}, str(tmp_path / "x.json"))


def test_known_ids_skips_missing_and_empty():
    history = {"jobs": [
        {"unique_id": "a"}, {"unique_id": ""}, {}, {"unique_id": None}, "bad",
    ]}
    assert storage.known_ids(history) == {"a"}


def test_save_is_atomic_no_temp_files(tmp_path):
    path = tmp_path / "history.json"
    storage.save_history({"jobs": []}, str(path))
    storage.save_history({"jobs": [{"unique_id": "1"}]}, str(path))
    assert not list(tmp_path.glob(".tmp-*"))
    assert json.loads(path.read_text(encoding="utf-8"))["jobs"][0]["unique_id"] == "1"


def test_backup_holds_previous_state(tmp_path):
    path = tmp_path / "history.json"
    storage.save_history({"jobs": [{"unique_id": "first"}]}, str(path))
    storage.save_history({"jobs": [{"unique_id": "second"}]}, str(path))
    backup = json.loads((tmp_path / "history.json.bak").read_text(encoding="utf-8"))
    assert backup["jobs"][0]["unique_id"] == "first"
    assert json.loads(path.read_text(encoding="utf-8"))["jobs"][0]["unique_id"] == "second"


def test_missing_main_uses_backup(tmp_path, capsys):
    path = tmp_path / "history.json"
    storage.save_history({"jobs": [{"unique_id": "only"}]}, str(path))
    assert path.exists()
    path.unlink()
    assert storage.load_history(str(path)) == {"jobs": [{"unique_id": "only"}]}
    assert "主历史文件缺失" in capsys.readouterr().out


def test_corrupt_main_does_not_overwrite_good_backup(tmp_path):
    path = tmp_path / "history.json"
    storage.save_history({"jobs": [{"unique_id": "good"}]}, str(path))
    path.write_text("{broken", encoding="utf-8")
    storage.save_history({"jobs": [{"unique_id": "new"}]}, str(path))
    backup = json.loads((tmp_path / "history.json.bak").read_text(encoding="utf-8"))
    assert backup["jobs"][0]["unique_id"] == "good"


def test_pre_migration_snapshot(tmp_path):
    path = tmp_path / "history.json"
    storage.save_history({"jobs": [{"unique_id": "old"}]}, str(path))
    snapshot = tmp_path / "history.json.pre-migration-2026-11-04"
    assert storage.snapshot_history("2026-11-04", str(path)) == str(snapshot)
    assert snapshot.exists()
    assert "old" in snapshot.read_text(encoding="utf-8")
    # 第二次调用不覆盖已有快照
    path.write_text('{"jobs": []}', encoding="utf-8")
    storage.snapshot_history("2026-11-04", str(path))
    assert "old" in snapshot.read_text(encoding="utf-8")
