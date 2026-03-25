from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import requests

from ptest import cli
from ptest.app import WorkflowService


class _FakeResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = {"content-type": "application/json"}
        self.text = str(body)

    def json(self) -> Any:
        return self._body


def test_cli_problem_show_uses_workspace_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    service = WorkflowService(workspace)
    service.init_environment()
    service.add_case(
        "api_failure_case",
        {
            "type": "api",
            "request": {"method": "GET", "url": "https://example.test/api/demo"},
            "expected_status": 200,
        },
    )

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(404, {"message": "missing"}),
    )
    service.run_case("api_failure_case")
    problem_id = service.list_problem_records(case_id="api_failure_case")[0][
        "problem_id"
    ]

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ptest", "problem", "show", problem_id, "--path", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert problem_id in captured.out
    assert "api_response" in captured.out


def test_cli_problem_recover_outputs_data_recovery_plan(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    service = WorkflowService(workspace)
    service.init_environment()
    service.add_case(
        "sqlite_failure_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(workspace / "sample.db"),
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 2}],
        },
    )
    service.run_case("sqlite_failure_case")
    problem_id = service.list_problem_records(
        case_id="sqlite_failure_case", problem_type="data_state"
    )[0]["problem_id"]

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ptest", "problem", "recover", problem_id, "--path", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert problem_id in captured.out
    assert "minimal_state_hints" in captured.out
