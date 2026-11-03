"""工作流与依赖清单的静态约束测试"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load(path):
    with open(ROOT / path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _triggers(workflow):
    return workflow.get("on", workflow.get(True, {}))


def test_monitor_workflow_contract():
    workflow = _load(".github/workflows/monitor.yml")
    assert "schedule" in _triggers(workflow)
    assert workflow["jobs"]["monitor"]["if"] == "github.ref == 'refs/heads/main'"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["monitor"]["permissions"] == {"contents": "write"}
    deploy = workflow["jobs"]["deploy"]
    assert deploy["needs"] == "monitor"
    assert deploy["permissions"] == {
        "contents": "read", "pages": "write", "id-token": "write",
    }
    assert deploy["concurrency"]["cancel-in-progress"] is False
    steps = workflow["jobs"]["monitor"]["steps"]
    upload = next(s for s in steps if s.get("name") == "Upload history site artifact")
    assert upload["with"]["name"] == "history-site"
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["overwrite"] is True


def test_workflows_pin_actions_to_full_sha():
    for path in (".github/workflows/monitor.yml", ".github/workflows/ci.yml"):
        workflow = _load(path)
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                uses = step.get("uses")
                if uses:
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", uses), (path, uses)


def test_ci_workflow_runs_quality_gates():
    workflow = _load(".github/workflows/ci.yml")
    triggers = _triggers(workflow)
    assert "push" in triggers and "pull_request" in triggers and "schedule" in triggers
    assert workflow["permissions"] == {"contents": "read"}
    run = "\n".join(step.get("run", "") for step in workflow["jobs"]["test"]["steps"])
    assert "ruff check ." in run
    assert "pytest" in run and "--cov-fail-under=85" in run
    assert "pip-audit" in run


def test_requirements_are_exact_and_complete():
    lines = [line.strip() for line in (ROOT / "requirements.txt").read_text().splitlines()
             if line.strip() and not line.startswith("#")]
    assert all("==" in line for line in lines), lines
    names = {line.split("==")[0].lower() for line in lines}
    assert "xlrd" in names
    assert "pandas" not in names
    assert not any(">=" in line for line in lines)
