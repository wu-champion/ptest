from __future__ import annotations

import json
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
    assert '"capabilities"' in captured.out


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
    assert '"failure_kind": "value_mismatch"' in captured.out
    assert '"origin_hints"' in captured.out
    assert '"boundary"' in captured.out
    assert '"scope": "query_level_plan"' in captured.out
    assert '"suggested_repairs"' in captured.out
    assert '"align_key_field_values"' in captured.out


def test_cli_problem_replay_reports_unsupported_for_data_problem(
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
        ["ptest", "problem", "replay", problem_id, "--path", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "does not support replay" in captured.out


def test_cli_problem_replay_outputs_comparison_summary(
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

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok"}),
    )
    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ptest", "problem", "replay", problem_id, "--path", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"comparison"' in captured.out
    assert '"status_code_changed": true' in captured.out
    assert '"assertion_outcome": "not_reproduced"' in captured.out
    assert '"summary"' in captured.out
    assert '"boundary"' in captured.out
    assert '"scope": "request_level"' in captured.out
    assert '"hidden_dependency_possible": true' in captured.out
    assert '"change_kind": "preserved_body_unavailable"' in captured.out
    assert '"investigation"' in captured.out
    assert '"replay_preview": {' in captured.out
    assert "replay no longer reproduces the original problem" in captured.out
    assert (
        "current replay only reruns the preserved request and may miss prior state changes or hidden dependencies"
        in captured.out
    )


def test_cli_problem_assets_outputs_reproduction_summary(
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
        ["ptest", "problem", "assets", problem_id, "--path", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"reproduction_summary"' in captured.out
    assert '"investigation"' in captured.out
    assert '"url": "https://example.test/api/demo"' in captured.out
    assert f'"ptest problem replay {problem_id}"' in captured.out


def test_cli_problem_list_reports_filters_and_empty_results(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    service = WorkflowService(workspace)
    service.init_environment()

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "problem",
            "list",
            "--type",
            "service_runtime",
            "--case-id",
            "missing_case",
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["count"] == 0
    assert payload["problems"] == []
    assert payload["filters"] == {
        "problem_type": "service_runtime",
        "case_id": "missing_case",
    }
