from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests

from ptest import cli
from ptest.app import WorkflowService
from ptest.models import ProblemRecord, ProblemRecoveryRecord


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
    assert '"workspace_recovery"' in captured.out
    assert '"scope": "workspace_minimum_recovery"' in captured.out


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
    assert '"diagnostics"' in captured.out
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


def test_cli_problem_list_filters_by_object_name(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    service = WorkflowService(workspace)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_obj_001",
            problem_type="api_response",
            summary="api problem",
            status="open",
            object_refs=["alpha_service"],
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_obj_002",
            problem_type="data_state",
            summary="data problem",
            status="open",
            object_refs=["beta_service"],
        )
    )

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "problem",
            "list",
            "--object-name",
            "alpha_service",
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["count"] == 1
    assert payload["problems"][0]["problem_id"] == "cli_obj_001"
    assert payload["filters"]["object_name"] == "alpha_service"


def test_cli_problem_list_filters_by_can_replay(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    service = WorkflowService(workspace)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_replay_001",
            problem_type="api_response",
            summary="replayable",
            status="open",
            object_refs=["svc_a"],
            metadata={"capabilities": {"can_replay": True, "can_recover": True}},
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_replay_002",
            problem_type="data_state",
            summary="not replayable",
            status="open",
            object_refs=["svc_b"],
            metadata={"capabilities": {"can_replay": False, "can_recover": True}},
        )
    )

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "problem",
            "list",
            "--can-replay",
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["count"] == 1
    assert payload["problems"][0]["problem_id"] == "cli_replay_001"
    assert payload["filters"]["can_replay"] is True
    assert "can_recover" not in payload["filters"]


def test_cli_problem_list_filters_by_multiple_args(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    service = WorkflowService(workspace)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_multi_001",
            problem_type="api_response",
            summary="match all",
            status="open",
            environment_id="env_prod",
            object_refs=["svc"],
            metadata={"capabilities": {"can_replay": True, "can_recover": True}},
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_multi_002",
            problem_type="data_state",
            summary="wrong env",
            status="open",
            environment_id="env_staging",
            object_refs=["svc"],
            metadata={"capabilities": {"can_replay": True, "can_recover": True}},
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_multi_003",
            problem_type="api_response",
            summary="no replay",
            status="open",
            environment_id="env_prod",
            object_refs=["svc"],
            metadata={"capabilities": {"can_replay": False, "can_recover": True}},
        )
    )

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "problem",
            "list",
            "--object-name",
            "svc",
            "--environment-id",
            "env_prod",
            "--can-replay",
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["count"] == 1
    assert payload["problems"][0]["problem_id"] == "cli_multi_001"
    assert payload["filters"] == {
        "object_name": "svc",
        "environment_id": "env_prod",
        "can_replay": True,
    }


def test_cli_problem_history_outputs_json(tmp_path: Path, monkeypatch, capsys) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    service = WorkflowService(workspace)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_hist_001",
            problem_type="api_response",
            summary="history cli test",
            object_refs=["svc"],
        )
    )
    service.storage.save_problem_recovery_history(
        ProblemRecoveryRecord(
            action_id="recovery_cli_001",
            problem_id="cli_hist_001",
            problem_type="api_response",
            action_type="replay",
            mode="request_replay",
            success=True,
            status="completed",
            created_at="2026-05-01T10:00:00",
        )
    )
    service.storage.save_problem_recovery_history(
        ProblemRecoveryRecord(
            action_id="recovery_cli_002",
            problem_id="cli_hist_001",
            problem_type="api_response",
            action_type="recover",
            mode="plan_only",
            success=True,
            status="prepared",
            created_at="2026-05-01T11:00:00",
        )
    )

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "problem",
            "history",
            "cli_hist_001",
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["problem_id"] == "cli_hist_001"
    assert payload["count"] == 2
    assert len(payload["actions"]) == 2
    assert payload["latest_action"] == "recover:prepared"


def test_cli_problem_history_existing_problem_without_any_history(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    service = WorkflowService(workspace)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="cli_hist_empty",
            problem_type="api_response",
            summary="empty history",
        )
    )

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "problem",
            "history",
            "cli_hist_empty",
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["problem_id"] == "cli_hist_empty"
    assert payload["count"] == 0
    assert payload["actions"] == []
    assert payload["latest_action"] is None


def test_cli_problem_history_not_found(tmp_path: Path, monkeypatch, capsys) -> None:
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
            "history",
            "nonexistent",
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()

    assert exit_code == 1
