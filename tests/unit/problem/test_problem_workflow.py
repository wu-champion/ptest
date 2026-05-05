from __future__ import annotations

import tarfile
from pathlib import Path
from typing import Any

import requests
import pytest

from ptest.app import WorkflowService
from ptest.cases.result import TestCaseResult
from ptest.models import (
    ExecutionRecord,
    ManagedObjectRecord,
    OBJECT_STATUS_INSTALLED,
    OBJECT_STATUS_RUNNING,
    OBJECT_STATUS_START_FAILED_PRESERVED,
    ProblemAssetRecord,
    ProblemRecord,
    ProblemRecoveryRecord,
)
from ptest.objects.db_server import DatabaseServerComponent


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {"content-type": "application/json"}
        self.text = body if isinstance(body, str) else str(body)

    def json(self) -> Any:
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


def test_workflow_service_preserves_and_replays_api_problem(
    tmp_path: Path, monkeypatch
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "api_failure_case",
        {
            "type": "api",
            "request": {
                "method": "GET",
                "url": "https://example.test/api/demo",
                "headers": {"X-Test": "1"},
            },
            "expected_status": 200,
        },
    )

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(404, {"message": "missing"}),
    )

    result = service.run_case("api_failure_case")
    assert result["success"] is False

    problems = service.list_problem_records(case_id="api_failure_case")
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]
    assert problems[0]["problem_type"] == "api_response"

    problem = service.get_problem_record(problem_id)
    assert problem["success"] is True
    assert problem["problem"]["execution_id"]
    assert problem["problem"]["metadata"]["preservation"]["status"] == "success"
    assert problem["problem"]["metadata"]["capabilities"]["can_replay"] is True
    assert problem["problem"]["metadata"]["capabilities"]["can_recover"] is True
    assert problem["problem"]["capabilities"]["can_replay"] is True
    assert problem["problem"]["preservation"]["status"] == "success"
    assert problem["problem"]["investigation"]["view"] == "problem"
    assert problem["problem"]["investigation"]["problem_type"] == "api_response"
    assert problem["problem"]["investigation"]["request"]["url"] == (
        "https://example.test/api/demo"
    )
    assert problem["problem"]["investigation"]["dependency"]["signal_strength"] == (
        "none"
    )

    filtered = service.list_problem_records(
        case_id="api_failure_case",
        execution_id=problem["problem"]["execution_id"],
    )
    assert [item["problem_id"] for item in filtered] == [problem_id]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert (
        assets["assets"]["details"]["request"]["url"] == "https://example.test/api/demo"
    )
    assert "Expected status 200" in assets["assets"]["details"]["response"]["error"]
    assert assets["assets"]["preservation_status"] == "success"
    assert assets["assets"]["details"]["preservation"]["missing_assets"] == []
    assert assets["assets"]["metadata"]["preservation"]["status"] == "success"
    assert assets["assets"]["metadata"]["capabilities"]["can_replay"] is True
    assert assets["assets"]["capabilities"]["can_replay"] is True
    assert assets["assets"]["preservation"]["status"] == "success"
    assert (
        assets["assets"]["reproduction_summary"]["request"]["url"]
        == "https://example.test/api/demo"
    )
    assert assets["assets"]["reproduction_summary"]["expected"]["status_code"] == 200
    assert (
        assets["assets"]["reproduction_summary"]["observed_failure"]["status_code"]
        == 404
    )
    assert (
        assets["assets"]["reproduction_summary"]["recommended_commands"][2]
        == f"ptest problem replay {problem_id}"
    )
    assert assets["assets"]["reproduction_summary"]["dependency_hints"] == {
        "recent_predecessors": [],
        "candidate_case_ids": [],
        "recent_same_case": None,
        "immediate_predecessor": None,
        "signal_strength": "none",
        "recommended_actions": [],
    }
    assert assets["assets"]["investigation"]["view"] == "assets"
    assert assets["assets"]["investigation"]["request"]["url"] == (
        "https://example.test/api/demo"
    )
    assert assets["assets"]["investigation"]["next_actions"] == []

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok"}),
    )
    replay = service.replay_problem(problem_id)
    assert replay["success"] is True
    assert replay["replay"]["response"]["status_code"] == 200
    assert replay["replay"]["request"]["url"] == "https://example.test/api/demo"
    assert replay["replay"]["comparison"]["original_failure"]["status_code"] == 404
    assert replay["replay"]["comparison"]["replay_response"]["status_code"] == 200
    assert replay["replay"]["comparison"]["status_code_changed"] is True
    assert replay["replay"]["comparison"]["expectation"]["reproduced"] is False
    assert replay["replay"]["comparison"]["assertion_outcome"] == "not_reproduced"
    assert replay["replay"]["comparison"]["boundary"]["scope"] == "request_level"
    assert replay["replay"]["comparison"]["boundary"]["confidence"] == "request_only"
    assert (
        replay["replay"]["comparison"]["boundary"]["assessment"]
        == "diverged_from_preserved_failure"
    )
    assert replay["replay"]["comparison"]["boundary"]["dependency_hints"] == {
        "recent_predecessors": [],
        "candidate_case_ids": [],
        "recent_same_case": None,
        "immediate_predecessor": None,
        "signal_strength": "none",
        "recommended_actions": [],
    }
    assert replay["replay"]["comparison"]["boundary"]["recommended_actions"] == []
    assert (
        replay["replay"]["comparison"]["boundary"]["hidden_dependency_possible"] is True
    )
    assert replay["replay"]["comparison"]["summary"]["reproduced"] is False
    assert replay["replay"]["comparison"]["summary"]["status"] == {
        "changed": True,
        "from": 404,
        "to": 200,
    }
    assert replay["replay"]["comparison"]["summary"]["boundary"]["scope"] == (
        "request_level"
    )
    assert replay["replay"]["comparison"]["summary"]["headers"]["comparable"] is False
    assert (
        replay["replay"]["comparison"]["summary"]["body"]["change_kind"]
        == "preserved_body_unavailable"
    )
    assert replay["replay"]["comparison"]["summary"]["body"]["comparable"] is False
    assert (
        replay["replay"]["comparison"]["summary"]["body"]["preserved_preview"] is None
    )
    assert replay["replay"]["comparison"]["summary"]["body"]["replay_preview"] == {
        "message": "ok"
    }
    assert (
        "status code changed from 404 to 200"
        in replay["replay"]["comparison"]["highlights"]
    )
    assert (
        "replay no longer reproduces the original problem"
        in replay["replay"]["comparison"]["highlights"]
    )
    assert (
        "current replay only reruns the preserved request and may miss prior state changes or hidden dependencies"
        in replay["replay"]["comparison"]["highlights"]
    )
    assert "next suggested step:" not in replay["replay"]["comparison"]["highlights"]
    assert replay["replay"]["investigation"]["view"] == "replay"
    assert replay["replay"]["investigation"]["replay"] == {
        "reproduced": False,
        "assessment": "diverged_from_preserved_failure",
        "scope": "request_level",
        "confidence": "request_only",
        "hidden_dependency_possible": True,
    }
    assert replay["replay"]["investigation"]["next_actions"] == []
    assert replay["replay"]["reproduced"] is False
    assert replay["recovery_action"]["action_type"] == "replay"
    assert replay["recovery_action"]["status"] == "completed"

    problem = service.get_problem_record(problem_id)
    assert problem["success"] is True
    assert problem["problem"]["latest_action"] == "replay:completed"
    assert problem["problem"]["metadata"]["latest_recovery"]["action_type"] == "replay"
    assert problem["problem"]["investigation"]["replay"]["assessment"] == (
        "diverged_from_preserved_failure"
    )

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["metadata"]["latest_recovery"]["action_type"] == "replay"
    assert (
        assets["assets"]["metadata"]["capabilities"]["recover_mode"] == "request_replay"
    )
    assert assets["assets"]["investigation"]["replay"]["assessment"] == (
        "diverged_from_preserved_failure"
    )

    latest_recovery = service.get_problem_recovery(problem_id)
    assert latest_recovery["success"] is True
    assert latest_recovery["recovery_action"]["action_type"] == "replay"


def test_workflow_service_preserves_data_state_problem(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    db_path = tmp_path / "sample.db"
    service.add_case(
        "sqlite_failure_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 2}],
        },
    )

    result = service.run_case("sqlite_failure_case")
    assert result["success"] is False

    problems = service.list_problem_records(
        case_id="sqlite_failure_case",
        problem_type="data_state",
    )
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    problem = service.get_problem_record(problem_id)
    assert problem["success"] is True
    assert problem["problem"]["investigation"]["data_source"]["db_type"] == "sqlite"
    assert problem["problem"]["investigation"]["failure_kind"] == "value_mismatch"
    assert problem["problem"]["investigation"]["state_hints"]["mismatched_fields"] == [
        "value"
    ]
    assert problem["problem"]["investigation"]["next_actions"][0]["action"] == (
        "inspect_data_source_connectivity"
    )

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["problem_type"] == "data_state"
    assert assets["assets"]["details"]["data_source"]["db_type"] == "sqlite"
    assert assets["assets"]["details"]["operations"][0]["query"] == "SELECT 1 as value"
    assert assets["assets"]["details"]["actual_result"] == [{"value": 1}]
    assert assets["assets"]["details"]["failure_kind"] == "value_mismatch"
    assert assets["assets"]["details"]["state_hints"]["expected_row_count"] == 1
    assert assets["assets"]["details"]["state_hints"]["actual_row_count"] == 1
    assert assets["assets"]["details"]["state_hints"]["mismatched_fields"] == ["value"]
    assert assets["assets"]["details"]["origin_hints"]["classification"] == (
        "stale_field_values"
    )
    assert assets["assets"]["details"]["origin_hints"]["query_context"] == (
        "list_query"
    )
    assert assets["assets"]["details"]["origin_hints"]["signal_strength"] == (
        "direct_result_only"
    )
    assert assets["assets"]["recovery"]["mode"] == "minimal_state_hints"
    assert assets["assets"]["recovery"]["supported"] is False
    assert assets["assets"]["recovery"]["failure_kind"] == "value_mismatch"
    assert assets["assets"]["recovery"]["origin_hints"]["classification"] == (
        "stale_field_values"
    )
    assert assets["assets"]["recovery"]["boundary"]["scope"] == "query_level_plan"
    assert (
        assets["assets"]["recovery"]["boundary"]["confidence"]
        == "high_for_direct_result_mismatch"
    )
    assert assets["assets"]["recovery"]["boundary"]["needs_historical_state"] is False
    assert assets["assets"]["recovery"]["recommended_queries"][0] == {
        "purpose": "rerun_preserved_query",
        "query": "SELECT 1 as value",
    }
    assert assets["assets"]["recovery"]["suggested_repairs"][0]["action"] == (
        "align_key_field_values"
    )
    assert assets["assets"]["investigation"]["data_source"]["db_type"] == "sqlite"
    assert assets["assets"]["investigation"]["failure_kind"] == "value_mismatch"
    assert assets["assets"]["investigation"]["state_hints"]["mismatched_fields"] == [
        "value"
    ]
    assert assets["assets"]["investigation"]["origin_hints"]["classification"] == (
        "stale_field_values"
    )
    assert assets["assets"]["investigation"]["boundary"]["scope"] == (
        "query_level_plan"
    )
    assert assets["assets"]["investigation"]["next_actions"][0]["action"] == (
        "inspect_data_source_connectivity"
    )
    assert assets["assets"]["metadata"]["preservation"]["status"] == "success"
    assert assets["assets"]["metadata"]["capabilities"]["can_replay"] is False
    assert assets["assets"]["metadata"]["capabilities"]["can_recover"] is True
    assert assets["assets"]["capabilities"]["can_recover"] is True
    assert assets["assets"]["preservation"]["status"] == "success"

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "data_state"
    assert recovery["recovery"]["mode"] == "minimal_state_hints"
    assert recovery["recovery"]["actual_result"] == [{"value": 1}]
    assert recovery["recovery"]["goal"] == (
        "identify the minimal data/state correction needed before rerunning the preserved query"
    )
    assert recovery["recovery"]["failure_kind"] == "value_mismatch"
    assert recovery["recovery"]["state_hints"]["mismatched_fields"] == ["value"]
    assert recovery["recovery"]["origin_hints"]["classification"] == (
        "stale_field_values"
    )
    assert recovery["recovery"]["origin_hints"]["query_context"] == "list_query"
    assert recovery["recovery"]["boundary"]["scope"] == "query_level_plan"
    assert (
        recovery["recovery"]["boundary"]["confidence"]
        == "high_for_direct_result_mismatch"
    )
    assert recovery["recovery"]["boundary"]["assessment"] == "query_level_plan"
    assert recovery["recovery"]["boundary"]["needs_historical_state"] is False
    assert recovery["recovery"]["recommended_queries"][0] == {
        "purpose": "rerun_preserved_query",
        "query": "SELECT 1 as value",
    }
    assert recovery["recovery"]["suggested_repairs"][0]["action"] == (
        "align_key_field_values"
    )
    assert recovery["recovery"]["workspace_recovery"]["scope"] == (
        "workspace_minimum_recovery"
    )
    assert recovery["recovery"]["workspace_recovery"]["affected_objects"] == []
    assert recovery["recovery"]["workspace_recovery"]["recovery_boundary"]["scope"] == (
        "workspace_minimum_recovery"
    )
    assert recovery["recovery"]["next_actions"][1]["action"] == (
        "rerun_preserved_query_manually"
    )
    assert recovery["recovery"]["limitations"] == [
        "current recovery output is a plan only and does not execute data changes automatically",
        "current data_state recovery does not reconstruct full historical database state",
    ]
    assert recovery["recovery"]["steps"]
    assert recovery["recovery_action"]["action_type"] == "recover"
    assert recovery["recovery_action"]["status"] == "prepared"

    problem = service.get_problem_record(problem_id)
    assert problem["success"] is True
    assert problem["problem"]["latest_action"] == "recover:prepared"
    assert (
        problem["problem"]["metadata"]["latest_recovery"]["mode"]
        == "minimal_state_hints"
    )

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert (
        assets["assets"]["metadata"]["latest_recovery"]["mode"] == "minimal_state_hints"
    )

    replay = service.replay_problem(problem_id)
    assert replay["success"] is False
    assert replay["error_code"] == "problem_replay_unsupported"


def test_workflow_service_data_state_origin_hints_reflect_recent_predecessors(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    db_path = tmp_path / "sample.db"
    service.add_case(
        "setup_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    service.add_case(
        "target_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT value FROM demo where status = 'ready'",
            "expected_result": [{"value": 2}],
        },
    )

    service.run_case("setup_case")
    result = service.run_case("target_case")
    assert result["success"] is False

    problem_id = service.list_problem_records(
        case_id="target_case", problem_type="data_state"
    )[0]["problem_id"]
    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["recovery"]["origin_hints"]["candidate_case_ids"] == [
        "setup_case"
    ]
    assert (
        assets["assets"]["recovery"]["origin_hints"]["immediate_predecessor"]["case_id"]
        == "setup_case"
    )
    assert assets["assets"]["recovery"]["origin_hints"]["query_context"] == (
        "status_filtered_query"
    )
    assert (
        assets["assets"]["recovery"]["boundary"]["assessment"]
        == "possible_precondition_or_sequence_dependency"
    )
    assert assets["assets"]["recovery"]["boundary"]["needs_historical_state"] is True
    assert assets["assets"]["investigation"]["origin_hints"]["candidate_case_ids"] == [
        "setup_case"
    ]


def test_workflow_service_preserves_environment_init_problem(
    tmp_path: Path, monkeypatch
) -> None:
    service = WorkflowService(tmp_path)

    def _raise_init_failure(existing) -> dict[str, Any]:
        raise RuntimeError("engine bootstrap failed")

    monkeypatch.setattr(service, "_ensure_isolation_environment", _raise_init_failure)

    with pytest.raises(RuntimeError, match="engine bootstrap failed"):
        service.init_environment()

    problems = service.list_problem_records(problem_type="environment_init")
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["phase"] == "init"
    assert assets["assets"]["details"]["error"] == "engine bootstrap failed"
    assert assets["assets"]["preservation_status"] == "partial"
    assert assets["assets"]["details"]["preservation"]["missing_assets"] == [
        "object_snapshot"
    ]
    assert (
        assets["assets"]["details"]["preservation"]["missing_reasons"][
            "object_snapshot"
        ]
        == "related object snapshot is not available"
    )
    assert assets["assets"]["metadata"]["preservation"]["status"] == "partial"

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "environment_init"
    assert recovery["recovery"]["mode"] == "minimal_environment_recovery"


def test_workflow_service_preserves_dependency_object_problem(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="service_a",
            type_name="service",
            status="created",
            installed=False,
            config={},
        )
    )

    result = service.start_object("service_a")
    assert result["success"] is False

    problems = service.list_problem_records(problem_type="dependency_object")
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["phase"] == "start"
    assert assets["assets"]["details"]["object"]["name"] == "service_a"

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "dependency_object"
    assert recovery["recovery"]["mode"] == "minimal_environment_recovery"


def test_workflow_service_preserves_dependency_object_prerun_validation_problem(
    tmp_path: Path, monkeypatch
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.install_object(
        "service",
        "unreachable_service",
        {"host": "127.0.0.1", "port": 65500},
    )
    monkeypatch.setattr(service, "_is_host_port_reachable", lambda host, port: False)

    result = service.start_object("unreachable_service")
    assert result["success"] is False
    assert result["error_code"] == "object_start_validation_failed"

    problems = service.list_problem_records(problem_type="dependency_object")
    problem = next(
        item
        for item in problems
        if item["summary"]
        == "Dependency object 'unreachable_service' failed pre-run validation"
    )
    problem_id = problem["problem_id"]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["phase"] == "pre-run validation"
    assert assets["assets"]["details"]["validation"]["target"] == "127.0.0.1:65500"

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "dependency_object"
    assert recovery["recovery"]["hints"]["target"] == "127.0.0.1:65500"


def test_workflow_service_preserves_dependency_configuration_problem(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    result = service.install_object("database", "broken_db", {})
    assert result["success"] is False

    problems = service.list_problem_records(problem_type="dependency_configuration")
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["phase"] == "install"
    assert assets["assets"]["details"]["object"]["name"] == "broken_db"
    assert assets["assets"]["details"]["provided_params"] == {}

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "dependency_configuration"
    assert recovery["recovery"]["mode"] == "minimal_environment_recovery"


def test_workflow_service_preserves_mysql_missing_dependency_problem(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = tmp_path / "assets" / "mysql.tar.xz"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = tmp_path / "assets" / "fake_mysql_pkg"
    binary = stage_dir / "bin" / "mysqld"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    with tarfile.open(package_path, "w:xz") as archive:
        archive.add(stage_dir, arcname="mysql-8.4")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
        },
    )
    assert install_result["success"] is True

    monkeypatch.setattr(
        DatabaseServerComponent,
        "_check_binary_dependencies",
        lambda self, binary, env=None: ["libaio.so.1t64", "libnuma.so.1"],
    )
    monkeypatch.setattr(
        DatabaseServerComponent,
        "_check_runtime_backend_capabilities",
        lambda self: (True, "host runtime backend preflight passed"),
    )

    result = service.start_object("mysql_service")
    assert result["success"] is False

    problems = service.list_problem_records(problem_type="dependency_configuration")
    problem = next(
        item
        for item in problems
        if item["summary"] == "Dependency object 'mysql_service' failed during 'start'"
    )
    problem_id = problem["problem_id"]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["phase"] == "start"
    assert assets["assets"]["details"]["missing_libraries"] == [
        "libaio.so.1t64",
        "libnuma.so.1",
    ]
    assert assets["assets"]["details"]["dependency_requirements"] == {}

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "dependency_configuration"
    assert recovery["recovery"]["missing_libraries"] == [
        "libaio.so.1t64",
        "libnuma.so.1",
    ]


def test_workflow_service_preserves_service_runtime_problem(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "service_runtime_failure_case",
        {
            "type": "service",
            "service_name": "demo_service",
            "host": "127.0.0.1",
            "port": 65500,
            "check_type": "port",
            "timeout": 1,
        },
    )

    result = service.run_case("service_runtime_failure_case")
    assert result["success"] is False

    problems = service.list_problem_records(
        case_id="service_runtime_failure_case",
        problem_type="service_runtime",
    )
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["service"]["service_name"] == "demo_service"
    assert assets["assets"]["details"]["failure_kind"] == "port_unreachable"
    assert assets["assets"]["details"]["runtime_hints"]["failure_kind"] == (
        "port_unreachable"
    )
    object_artifacts = assets["assets"]["details"]["object_artifacts"]
    assert object_artifacts["selection"]["mode"] == "explicit_refs"
    assert object_artifacts["before"]["objects"][0]["object_name"] == "demo_service"
    assert object_artifacts["before"]["objects"][0]["object_found"] is False
    assert object_artifacts["after"]["objects"][0]["object_found"] is False
    assert object_artifacts["artifact_ref"].endswith("context/object_artifacts.json")
    assert assets["assets"]["recovery"]["mode"] == "runtime_level_plan"
    assert assets["assets"]["recovery"]["failure_kind"] == "port_unreachable"
    assert assets["assets"]["recovery"]["runtime_target"]["service_name"] == (
        "demo_service"
    )
    assert assets["assets"]["recovery"]["recommended_checks"][0]["purpose"] == (
        "inspect_runtime_status"
    )
    assert assets["assets"]["recovery"]["suggested_repairs"][0]["action"] == (
        "verify_endpoint_reachability_and_port_binding"
    )
    assert assets["assets"]["investigation"]["runtime_target"]["service_name"] == (
        "demo_service"
    )
    assert assets["assets"]["investigation"]["failure_kind"] == "port_unreachable"
    assert assets["assets"]["investigation"]["runtime_hints"]["check_type"] == "port"
    assert assets["assets"]["investigation"]["boundary"]["scope"] == (
        "runtime_level_plan"
    )
    assert assets["assets"]["investigation"]["object_artifacts"] == object_artifacts
    diagnostics = assets["assets"]["investigation"]["diagnostics"]
    assert diagnostics["status"] == "complete"
    assert diagnostics["object_refs"] == ["demo_service"]
    assert diagnostics["object_artifacts"]["artifact_ref"].endswith(
        "context/object_artifacts.json"
    )
    assert any(signal["code"] == "object_missing" for signal in diagnostics["signals"])
    assert any(
        view["view"] == "execution_artifacts" for view in diagnostics["next_views"]
    )

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "service_runtime"
    assert recovery["recovery"]["mode"] == "runtime_level_plan"
    assert recovery["recovery"]["goal"] == (
        "identify the minimal runtime correction needed before rerunning the preserved service check"
    )
    assert recovery["recovery"]["failure_kind"] == "port_unreachable"
    assert recovery["recovery"]["runtime_target"]["port"] == 65500
    assert recovery["recovery"]["boundary"]["scope"] == "runtime_level_plan"
    assert recovery["recovery"]["next_actions"][0]["action"] == (
        "inspect_recent_runtime_logs"
    )
    assert (
        recovery["recovery"]["workspace_recovery"]["affected_objects"][0]["object_name"]
        == "demo_service"
    )
    assert (
        recovery["recovery"]["workspace_recovery"]["affected_objects"][0][
            "recommended_action"
        ]
        == "reinstall"
    )


def test_workflow_service_classifies_start_failed_service_runtime_problem(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="demo_service",
            type_name="service",
            status=OBJECT_STATUS_START_FAILED_PRESERVED,
            installed=True,
            config={"runtime_backend": "managed"},
            metadata={"failure_state": {"phase": "start"}},
        )
    )
    service.add_case(
        "service_start_failed_case",
        {
            "type": "service",
            "service_name": "demo_service",
            "host": "127.0.0.1",
            "port": 65501,
            "check_type": "port",
            "timeout": 1,
        },
    )

    result = service.run_case("service_start_failed_case")
    assert result["success"] is False

    problems = service.list_problem_records(
        case_id="service_start_failed_case",
        problem_type="service_runtime",
    )
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["failure_kind"] == "startup_failed"
    runtime_backend = assets["assets"]["metadata"]["runtime_backend"]
    assert runtime_backend["status"] == "unsatisfied"
    assert runtime_backend["objects"][0]["object_name"] == "demo_service"
    assert runtime_backend["objects"][0]["runtime_backend"]["name"] == "managed"
    assert (
        "runtime_backend_unsupported:managed"
        in runtime_backend["objects"][0]["runtime_backend"]["limitations"]
    )
    assert assets["assets"]["investigation"]["runtime_backend"] == runtime_backend
    assert assets["assets"]["recovery"]["failure_kind"] == "startup_failed"
    assert assets["assets"]["recovery"]["runtime_hints"]["object_status"] == (
        OBJECT_STATUS_START_FAILED_PRESERVED
    )
    assert assets["assets"]["recovery"]["boundary"]["assessment"] == (
        "startup_failure_detected"
    )
    assert assets["assets"]["investigation"]["failure_kind"] == "startup_failed"
    assert assets["assets"]["investigation"]["boundary"]["confidence"] == (
        "high_for_preserved_start_failure"
    )


def test_workflow_service_classifies_abnormal_exit_from_expected_running_service(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "service_abnormal_exit_case",
        {
            "type": "service",
            "service_name": "demo_service",
            "host": "127.0.0.1",
            "port": 65502,
            "check_type": "port",
            "timeout": 1,
            "expected_runtime_state": "running",
        },
    )

    result = service.run_case("service_abnormal_exit_case")
    assert result["success"] is False

    problems = service.list_problem_records(
        case_id="service_abnormal_exit_case",
        problem_type="service_runtime",
    )
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["failure_kind"] == "abnormal_exit"
    assert assets["assets"]["details"]["runtime_hints"]["failure_kind"] == (
        "abnormal_exit"
    )
    assert assets["assets"]["details"]["runtime_hints"]["expected_runtime_state"] == (
        "running"
    )
    assert assets["assets"]["recovery"]["boundary"]["confidence"] == (
        "high_for_expected_running_service"
    )
    assert assets["assets"]["recovery"]["boundary"]["assessment"] == (
        "runtime_diverged_from_expected_service_state"
    )
    assert assets["assets"]["recovery"]["suggested_repairs"][0]["action"] == (
        "inspect_exit_logs_before_restart"
    )
    assert assets["assets"]["investigation"]["failure_kind"] == "abnormal_exit"
    assert (
        assets["assets"]["investigation"]["runtime_hints"]["expected_runtime_state"]
        == "running"
    )


def test_workflow_service_preserves_crash_dump_problem(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "service.log").write_text(
        "booting service\nfatal: segmentation fault\n",
        encoding="utf-8",
    )
    dump_file = tmp_path / "crash.core"
    dump_file.write_text("fake core content", encoding="utf-8")
    service.add_case(
        "service_crash_dump_case",
        {
            "type": "service",
            "service_name": "demo_service",
            "host": "127.0.0.1",
            "port": 65503,
            "check_type": "port",
            "timeout": 1,
            "expected_runtime_state": "running",
            "dump_paths": [str(dump_file)],
        },
    )

    result = service.run_case("service_crash_dump_case")
    assert result["success"] is False

    problems = service.list_problem_records(
        case_id="service_crash_dump_case",
        problem_type="crash_dump",
    )
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    detail = service.get_problem_record(problem_id)
    assert detail["success"] is True
    assert detail["problem"]["problem_type"] == "crash_dump"
    assert detail["problem"]["investigation"]["crash_target"]["service_name"] == (
        "demo_service"
    )
    assert detail["problem"]["investigation"]["boundary"]["scope"] == (
        "crash_asset_preservation"
    )
    assert detail["problem"]["investigation"]["diagnostics"]["object_refs"] == [
        "demo_service"
    ]

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["crash_target"]["service_name"] == "demo_service"
    assert assets["assets"]["details"]["dump_refs"][0]["path"] == str(dump_file)
    assert assets["assets"]["details"]["dump_refs"][0]["exists"] is True
    assert assets["assets"]["details"]["object_summary"]["object_found"] is False
    object_artifacts = assets["assets"]["details"]["object_artifacts"]
    assert object_artifacts["before"]["objects"][0]["object_name"] == "demo_service"
    assert object_artifacts["before"]["objects"][0]["object_found"] is False
    assert object_artifacts["artifact_ref"].endswith("context/object_artifacts.json")
    assert assets["assets"]["details"]["crash_capture"]["new_dump_refs"] == []
    assert assets["assets"]["details"]["log_window"]["workspace_logs_dir"] == "logs"
    assert assets["assets"]["details"]["log_window"]["file_count"] >= 1
    assert any(
        snippet.get("path") == "logs/service.log"
        for snippet in assets["assets"]["details"]["log_window"]["snippets"]
        if isinstance(snippet, dict)
    )
    assert any(
        "fatal: segmentation fault" in snippet.get("tail", [])
        for snippet in assets["assets"]["details"]["log_window"]["snippets"]
        if isinstance(snippet, dict)
    )
    assert assets["assets"]["recovery"]["mode"] == "crash_dump_investigation"
    assert assets["assets"]["recovery"]["object_summary"]["object_found"] is False
    assert assets["assets"]["recovery"]["log_window"]["file_count"] >= 1
    assert assets["assets"]["recovery"]["boundary"]["confidence"] == (
        "high_for_existing_dump_refs"
    )
    assert assets["assets"]["investigation"]["crash_summary"]["execution_status"] == (
        "failed"
    )
    assert assets["assets"]["investigation"]["dump_refs"][0]["exists"] is True
    assert assets["assets"]["investigation"]["object_summary"]["object_found"] is False
    assert assets["assets"]["investigation"]["log_window"]["file_count"] >= 1
    assert assets["assets"]["investigation"]["object_artifacts"] == object_artifacts
    diagnostics = assets["assets"]["investigation"]["diagnostics"]
    assert diagnostics["object_artifacts"]["object_count"] == 1
    assert diagnostics["artifact_refs"]["object_artifacts"].endswith(
        "context/object_artifacts.json"
    )
    assert any(signal["code"] == "object_missing" for signal in diagnostics["signals"])

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "crash_dump"
    assert recovery["recovery"]["mode"] == "crash_dump_investigation"
    assert recovery["recovery"]["goal"] == (
        "preserve and inspect the minimal crash assets before deeper dump analysis"
    )
    assert recovery["recovery"]["dump_refs"][0]["exists"] is True
    assert recovery["recovery"]["recommended_checks"][0]["purpose"] == (
        "inspect_dump_refs"
    )
    assert (
        recovery["recovery"]["workspace_recovery"]["affected_objects"][0]["object_name"]
        == "demo_service"
    )
    assert (
        recovery["recovery"]["workspace_recovery"]["affected_objects"][0][
            "recommended_action"
        ]
        == "reinstall"
    )


def test_workflow_service_auto_discovers_new_crash_dump_refs(
    tmp_path: Path, monkeypatch
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    case_definition = {
        "data": {
            "type": "service",
            "service_name": "demo_service",
            "host": "127.0.0.1",
            "port": 65503,
            "check_type": "port",
            "timeout": 1,
            "expected_runtime_state": "running",
        }
    }

    service.add_case("service_crash_auto_case", case_definition["data"])

    dump_file = (tmp_path / "workspace_dump.core").resolve()

    def _fake_execute_case_with_bindings(case_manager, case_id, params=None):
        result = TestCaseResult(case_id)
        result.status = "failed"
        result.error_message = "connection refused after crash"
        result.output = "service exited unexpectedly"
        return result, case_definition

    snapshots = iter(
        [
            {"captured_at": "before", "directories": [], "dump_refs": []},
            {
                "captured_at": "after",
                "directories": [str(tmp_path)],
                "dump_refs": [
                    {
                        "path": str(dump_file),
                        "exists": True,
                        "kind": "core_or_dump",
                        "name": dump_file.name,
                        "size": 128,
                        "modified_at": "2026-04-23T00:00:00",
                        "source": "workspace_scan",
                        "directory": str(tmp_path),
                    }
                ],
            },
        ]
    )

    monkeypatch.setattr(
        service,
        "_execute_case_with_bindings",
        _fake_execute_case_with_bindings,
    )
    monkeypatch.setattr(
        service,
        "_capture_workspace_crash_dump_snapshot",
        lambda _case_definition: next(snapshots),
    )

    result = service.run_case("service_crash_auto_case")
    assert result["success"] is False

    problems = service.list_problem_records(
        case_id="service_crash_auto_case",
        problem_type="crash_dump",
    )
    assert len(problems) == 1
    problem_id = problems[0]["problem_id"]

    detail = service.get_problem_record(problem_id)
    assert detail["success"] is True
    assert detail["problem"]["problem_type"] == "crash_dump"
    assert detail["problem"]["investigation"]["dump_refs"][0]["path"] == str(dump_file)

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["dump_refs"][0]["path"] == str(dump_file)
    assert assets["assets"]["details"]["dump_refs"][0]["source"] == "workspace_scan"
    assert assets["assets"]["details"]["crash_capture"]["new_dump_refs"][0][
        "path"
    ] == str(dump_file)
    assert assets["assets"]["details"]["object_summary"]["object_found"] is False
    assert assets["assets"]["recovery"]["dump_refs"][0]["path"] == str(dump_file)
    assert assets["assets"]["investigation"]["boundary"]["assessment"] == (
        "dump_refs_preserved_for_followup_analysis"
    )


def test_workflow_service_returns_minimal_recovery_for_crash_dump_problem(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    problem_id = "problem_crash_001"
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id=problem_id,
            problem_type="crash_dump",
            summary="Crash dump problem",
        )
    )
    service.storage.save_problem_assets(
        ProblemAssetRecord(
            problem_id=problem_id,
            problem_type="crash_dump",
            summary="Crash dump problem",
            recovery={"supported": False, "mode": "preservation_only"},
            details={"dump_refs": ["core.001"]},
        )
    )

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "crash_dump"
    assert recovery["recovery"]["mode"] == "preservation_only"
    assert recovery["recovery"]["dump_refs"] == ["core.001"]


def test_workflow_crash_dump_recovery_exposes_side_effect_hints(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_execution(
        ExecutionRecord(
            execution_id="exec_prev_crash",
            case_id="mutate_crash_case",
            status="passed",
            duration=0.1,
            start_time="2026-04-23T11:00:00",
            end_time="2026-04-23T11:00:01",
        )
    )
    service.storage.save_execution(
        ExecutionRecord(
            execution_id="exec_crash_failure",
            case_id="crash_check_case",
            status="failed",
            duration=0.1,
            start_time="2026-04-23T11:00:02",
            end_time="2026-04-23T11:00:03",
            error_message="service exited unexpectedly and produced a crash dump",
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="problem_crash_side_effect",
            problem_type="crash_dump",
            summary="crash dump after side effect",
            execution_id="exec_crash_failure",
            case_id="crash_check_case",
            object_refs=["demo_crash_service"],
        )
    )
    service.storage.save_problem_assets(
        ProblemAssetRecord(
            problem_id="problem_crash_side_effect",
            problem_type="crash_dump",
            summary="crash dump after side effect",
            execution_id="exec_crash_failure",
            case_id="crash_check_case",
            object_refs=["demo_crash_service"],
            recovery={
                "supported": True,
                "mode": "crash_dump_investigation",
                "dump_refs": [{"path": str(tmp_path / "demo.core"), "exists": True}],
                "crash_target": {
                    "service_name": "demo_crash_service",
                    "object_name": "demo_crash_service",
                },
                "boundary": {
                    "scope": "crash_asset_preservation",
                    "assessment": "dump_refs_preserved_for_followup_analysis",
                },
            },
            details={
                "crash_target": {
                    "service_name": "demo_crash_service",
                    "object_name": "demo_crash_service",
                },
                "dump_refs": [{"path": str(tmp_path / "demo.core"), "exists": True}],
                "crash_event": {
                    "execution_status": "failed",
                    "error": "segmentation fault",
                },
            },
        )
    )

    detail = service.get_problem_record("problem_crash_side_effect")
    assert detail["success"] is True
    assert detail["problem"]["investigation"]["side_effect"]["classification"] == (
        "possible_crash_inducing_side_effect"
    )
    assert (
        detail["problem"]["investigation"]["side_effect"]["likely_trigger_case_id"]
        == "mutate_crash_case"
    )
    assert (
        detail["problem"]["investigation"]["environment_recovery"]["assessment"]
        == "environment_may_have_shifted_by_prior_case"
    )

    recovery = service.recover_problem("problem_crash_side_effect")
    assert recovery["success"] is True
    assert recovery["recovery"]["side_effect_hints"]["classification"] == (
        "possible_crash_inducing_side_effect"
    )
    assert recovery["recovery"]["side_effect_hints"]["likely_trigger_case_id"] == (
        "mutate_crash_case"
    )
    assert recovery["recovery"]["environment_recovery"]["scope"] == (
        "workspace_side_effect_minimum_recovery"
    )
    assert recovery["recovery"]["environment_recovery"]["recommended_sequence"][0] == (
        "inspect_likely_trigger_case_effects"
    )


def test_workflow_service_workspace_recovery_maps_actions_for_problem_types(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="api_service",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
            installed=True,
        )
    )
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="mysql_service",
            type_name="database",
            status=OBJECT_STATUS_INSTALLED,
            installed=True,
        )
    )
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="runtime_service",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
            installed=True,
        )
    )
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="crash_service",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
            installed=True,
        )
    )

    for problem_id, problem_type, object_name in [
        ("problem_api_001", "api_response", "api_service"),
        ("problem_data_001", "data_state", "mysql_service"),
        ("problem_runtime_001", "service_runtime", "runtime_service"),
        ("problem_crash_002", "crash_dump", "crash_service"),
    ]:
        service.storage.save_problem_record(
            ProblemRecord(
                problem_id=problem_id,
                problem_type=problem_type,
                summary=f"{problem_type} problem",
                object_refs=[object_name],
            )
        )
        service.storage.save_problem_assets(
            ProblemAssetRecord(
                problem_id=problem_id,
                problem_type=problem_type,
                summary=f"{problem_type} problem",
                object_refs=[object_name],
                recovery={"supported": False, "mode": "plan_only"},
                details={},
            )
        )

    api_recovery = service.recover_problem("problem_api_001")
    assert (
        api_recovery["recovery"]["workspace_recovery"]["affected_objects"][0][
            "recommended_action"
        ]
        == "restart"
    )

    data_recovery = service.recover_problem("problem_data_001")
    assert (
        data_recovery["recovery"]["workspace_recovery"]["affected_objects"][0][
            "recommended_action"
        ]
        == "reset"
    )

    runtime_recovery = service.recover_problem("problem_runtime_001")
    assert (
        runtime_recovery["recovery"]["workspace_recovery"]["affected_objects"][0][
            "recommended_action"
        ]
        == "restart"
    )

    crash_recovery = service.recover_problem("problem_crash_002")
    assert (
        crash_recovery["recovery"]["workspace_recovery"]["affected_objects"][0][
            "recommended_action"
        ]
        == "restart"
    )


def test_workflow_service_runtime_recovery_exposes_side_effect_hints(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_execution(
        ExecutionRecord(
            execution_id="exec_prev_runtime",
            case_id="mutate_runtime_case",
            status="passed",
            duration=0.1,
            start_time="2026-04-23T10:00:00",
            end_time="2026-04-23T10:00:01",
        )
    )
    service.storage.save_execution(
        ExecutionRecord(
            execution_id="exec_runtime_failure",
            case_id="runtime_check_case",
            status="failed",
            duration=0.1,
            start_time="2026-04-23T10:00:02",
            end_time="2026-04-23T10:00:03",
            error_message="Service demo_runtime_service is not reachable at 127.0.0.1:45678",
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="problem_runtime_side_effect",
            problem_type="service_runtime",
            summary="runtime problem after side effect",
            execution_id="exec_runtime_failure",
            case_id="runtime_check_case",
            object_refs=["demo_runtime_service"],
        )
    )
    service.storage.save_problem_assets(
        ProblemAssetRecord(
            problem_id="problem_runtime_side_effect",
            problem_type="service_runtime",
            summary="runtime problem after side effect",
            execution_id="exec_runtime_failure",
            case_id="runtime_check_case",
            object_refs=["demo_runtime_service"],
            recovery={
                "supported": False,
                "mode": "runtime_level_plan",
                "failure_kind": "port_unreachable",
                "runtime_target": {
                    "service_name": "demo_runtime_service",
                    "object_name": "demo_runtime_service",
                },
                "runtime_hints": {
                    "failure_kind": "port_unreachable",
                    "check_type": "port",
                    "connectable": False,
                },
                "boundary": {
                    "scope": "runtime_level_plan",
                    "assessment": "endpoint_or_healthcheck_failure",
                },
            },
            details={
                "service": {
                    "service_name": "demo_runtime_service",
                    "host": "127.0.0.1",
                    "port": 45678,
                    "check_type": "port",
                },
                "runtime_result": {
                    "status": "failed",
                    "error": "not reachable",
                },
                "failure_kind": "port_unreachable",
            },
        )
    )

    detail = service.get_problem_record("problem_runtime_side_effect")
    assert detail["success"] is True
    assert detail["problem"]["investigation"]["side_effect"]["classification"] == (
        "possible_runtime_destabilization"
    )
    assert (
        detail["problem"]["investigation"]["side_effect"]["likely_trigger_case_id"]
        == "mutate_runtime_case"
    )
    assert detail["problem"]["investigation"]["environment_recovery"]["scope"] == (
        "workspace_side_effect_minimum_recovery"
    )
    assert (
        detail["problem"]["investigation"]["environment_recovery"]["assessment"]
        == "environment_may_have_shifted_by_prior_case"
    )

    recovery = service.recover_problem("problem_runtime_side_effect")
    assert recovery["success"] is True
    assert recovery["recovery"]["side_effect_hints"]["classification"] == (
        "possible_runtime_destabilization"
    )
    assert recovery["recovery"]["side_effect_hints"]["likely_trigger_case_id"] == (
        "mutate_runtime_case"
    )
    assert recovery["recovery"]["environment_recovery"]["scope"] == (
        "workspace_side_effect_minimum_recovery"
    )
    assert recovery["recovery"]["environment_recovery"]["recommended_sequence"][0] == (
        "inspect_likely_trigger_case_effects"
    )


def _create_filter_test_records(service: WorkflowService) -> None:
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="filter_api_001",
            problem_type="api_response",
            summary="api problem for alpha",
            status="open",
            preservation_status="success",
            environment_id="env_prod",
            object_refs=["alpha_service"],
            metadata={"capabilities": {"can_replay": True, "can_recover": True}},
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="filter_data_001",
            problem_type="data_state",
            summary="data problem for beta",
            status="resolved",
            preservation_status="partial",
            environment_id="env_staging",
            object_refs=["beta_service", "gamma_db"],
            metadata={"capabilities": {"can_replay": False, "can_recover": True}},
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="filter_runtime_001",
            problem_type="service_runtime",
            summary="runtime problem for gamma",
            status="open",
            preservation_status="failed",
            environment_id="env_prod",
            object_refs=["gamma_db"],
            metadata={"capabilities": {"can_replay": True, "can_recover": False}},
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="filter_no_caps_001",
            problem_type="crash_dump",
            summary="crash problem without capabilities",
            status="open",
            preservation_status="success",
            environment_id="env_dev",
            object_refs=["delta_service"],
        )
    )


def test_list_problem_records_filters_by_object_name(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    _create_filter_test_records(service)

    results = service.list_problem_records(object_name="alpha_service")
    assert len(results) == 1
    assert results[0]["problem_id"] == "filter_api_001"

    results = service.list_problem_records(object_name="gamma_db")
    assert len(results) == 2
    problem_ids = {r["problem_id"] for r in results}
    assert problem_ids == {"filter_data_001", "filter_runtime_001"}

    results = service.list_problem_records(object_name="nonexistent")
    assert results == []


def test_list_problem_records_filters_by_environment_id(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    _create_filter_test_records(service)

    results = service.list_problem_records(environment_id="env_prod")
    assert len(results) == 2
    problem_ids = {r["problem_id"] for r in results}
    assert problem_ids == {"filter_api_001", "filter_runtime_001"}

    results = service.list_problem_records(environment_id="env_staging")
    assert len(results) == 1
    assert results[0]["problem_id"] == "filter_data_001"


def test_list_problem_records_filters_by_status(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    _create_filter_test_records(service)

    results = service.list_problem_records(status="open")
    assert len(results) == 3
    problem_ids = {r["problem_id"] for r in results}
    assert problem_ids == {"filter_api_001", "filter_runtime_001", "filter_no_caps_001"}

    results = service.list_problem_records(status="resolved")
    assert len(results) == 1
    assert results[0]["problem_id"] == "filter_data_001"


def test_list_problem_records_filters_by_preservation_status(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    _create_filter_test_records(service)

    results = service.list_problem_records(preservation_status="partial")
    assert len(results) == 1
    assert results[0]["problem_id"] == "filter_data_001"

    results = service.list_problem_records(preservation_status="failed")
    assert len(results) == 1
    assert results[0]["problem_id"] == "filter_runtime_001"

    results = service.list_problem_records(preservation_status="success")
    assert len(results) == 2
    problem_ids = {r["problem_id"] for r in results}
    assert problem_ids == {"filter_api_001", "filter_no_caps_001"}


def test_list_problem_records_filters_by_can_replay(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    _create_filter_test_records(service)

    results = service.list_problem_records(can_replay=True)
    assert len(results) == 2
    problem_ids = {r["problem_id"] for r in results}
    assert problem_ids == {"filter_api_001", "filter_runtime_001"}


def test_list_problem_records_filters_by_can_recover(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    _create_filter_test_records(service)

    results = service.list_problem_records(can_recover=True)
    assert len(results) == 2
    problem_ids = {r["problem_id"] for r in results}
    assert problem_ids == {"filter_api_001", "filter_data_001"}


def test_list_problem_records_filters_by_multiple_conditions(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    _create_filter_test_records(service)

    results = service.list_problem_records(
        environment_id="env_prod",
        status="open",
        can_replay=True,
    )
    assert len(results) == 2
    problem_ids = {r["problem_id"] for r in results}
    assert problem_ids == {"filter_api_001", "filter_runtime_001"}

    results = service.list_problem_records(
        environment_id="env_prod",
        can_recover=True,
    )
    assert len(results) == 1
    assert results[0]["problem_id"] == "filter_api_001"


def test_list_problem_records_returns_empty_when_no_match(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    _create_filter_test_records(service)

    results = service.list_problem_records(
        object_name="alpha_service",
        environment_id="env_staging",
    )
    assert results == []

    results = service.list_problem_records(status="closed")
    assert results == []


def test_list_problem_records_ordered_by_created_at_desc(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    for i, pid in enumerate(["problem_first", "problem_second", "problem_third"]):
        service.storage.save_problem_record(
            ProblemRecord(
                problem_id=pid,
                problem_type="api_response",
                summary=f"problem {i}",
                object_refs=["my_service"],
                created_at=f"2026-05-01T10:00:0{i}",
            )
        )

    results = service.list_problem_records(object_name="my_service")
    assert len(results) == 3
    assert results[0]["problem_id"] == "problem_third"
    assert results[1]["problem_id"] == "problem_second"
    assert results[2]["problem_id"] == "problem_first"


def test_workflow_service_recovery_history_after_multiple_replays(
    tmp_path: Path, monkeypatch
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "history_case",
        {
            "type": "api",
            "request": {
                "method": "GET",
                "url": "https://example.test/api/history",
            },
            "expected_status": 200,
        },
    )

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(404, {"message": "missing"}),
    )
    result = service.run_case("history_case")
    assert result["success"] is False

    problems = service.list_problem_records(case_id="history_case")
    problem_id = problems[0]["problem_id"]

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok"}),
    )
    service.replay_problem(problem_id)

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok again"}),
    )
    service.replay_problem(problem_id)

    history = service.list_problem_recovery_history(problem_id)
    assert history["success"] is True
    assert history["history"]["count"] == 2
    assert len(history["history"]["actions"]) == 2
    assert all(a["action_type"] == "replay" for a in history["history"]["actions"])
    assert history["history"]["latest_action"] == "replay:completed"


def test_workflow_service_recovery_history_after_replay_and_recover(
    tmp_path: Path, monkeypatch
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "mixed_case",
        {
            "type": "api",
            "request": {
                "method": "GET",
                "url": "https://example.test/api/mixed",
            },
            "expected_status": 200,
        },
    )

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(404, {"message": "missing"}),
    )
    result = service.run_case("mixed_case")
    assert result["success"] is False

    problems = service.list_problem_records(case_id="mixed_case")
    problem_id = problems[0]["problem_id"]

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok"}),
    )
    service.replay_problem(problem_id)
    service.recover_problem(problem_id)

    history = service.list_problem_recovery_history(problem_id)
    assert history["success"] is True
    assert history["history"]["count"] == 2
    action_types = [a["action_type"] for a in history["history"]["actions"]]
    assert "replay" in action_types
    assert "recover" in action_types

    latest = service.storage.get_problem_recovery(problem_id)
    assert latest is not None
    assert latest.action_type == "recover"

    detail = service.get_problem_record(problem_id)
    assert detail["problem"]["metadata"]["latest_recovery"]["action_type"] == "recover"


def test_workflow_service_recovery_history_fallback_from_recovery_json(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="fallback_problem",
            problem_type="api_response",
            summary="fallback test",
        )
    )
    service.storage.save_problem_recovery(
        ProblemRecoveryRecord(
            action_id="recovery_fallback_001",
            problem_id="fallback_problem",
            problem_type="api_response",
            action_type="replay",
            mode="request_replay",
            success=True,
            status="completed",
            created_at="2026-05-01T10:00:00",
        )
    )

    history = service.list_problem_recovery_history("fallback_problem")
    assert history["success"] is True
    assert history["history"]["count"] == 1
    assert history["history"]["actions"][0]["action_id"] == "recovery_fallback_001"
    assert history["history"]["latest_action"] == "replay:completed"


def test_workflow_service_recovery_history_existing_problem_without_any_history(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="no_history_problem",
            problem_type="api_response",
            summary="no history yet",
        )
    )

    history = service.list_problem_recovery_history("no_history_problem")
    assert history["success"] is True
    assert history["history"]["count"] == 0
    assert history["history"]["actions"] == []
    assert history["history"]["latest_action"] is None


def test_workflow_service_recovery_history_not_found(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    history = service.list_problem_recovery_history("nonexistent")
    assert history["success"] is False


def test_update_problem_record_status(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="upd_001",
            problem_type="api_response",
            summary="to update",
            status="open",
        )
    )

    result = service.update_problem_record("upd_001", status="investigating")
    assert result["success"] is True
    assert result["problem"]["status"] == "investigating"
    assert result["problem"]["latest_action"] == "status:investigating"

    record = service.storage.get_problem_record("upd_001")
    assert record is not None
    assert record.status == "investigating"
    assert record.latest_action == "status:investigating"


def test_update_problem_record_notes(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="upd_002",
            problem_type="api_response",
            summary="to note",
        )
    )

    result = service.update_problem_record("upd_002", notes="replay still fails")
    assert result["success"] is True
    assert result["problem"]["notes"] == "replay still fails"
    assert result["problem"]["latest_action"] == "note:updated"


def test_update_problem_record_status_and_notes(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="upd_003",
            problem_type="api_response",
            summary="both",
        )
    )

    result = service.update_problem_record(
        "upd_003", status="resolved", notes="fixed upstream"
    )
    assert result["success"] is True
    assert result["problem"]["status"] == "resolved"
    assert result["problem"]["notes"] == "fixed upstream"
    assert result["problem"]["latest_action"] == "status:resolved"


def test_update_problem_record_invalid_status(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="upd_004",
            problem_type="api_response",
            summary="bad status",
            status="open",
        )
    )

    result = service.update_problem_record("upd_004", status="bogus")
    assert result["success"] is False
    assert result["error_code"] == "problem_status_invalid"

    record = service.storage.get_problem_record("upd_004")
    assert record is not None
    assert record.status == "open"


def test_update_problem_record_empty_update(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="upd_005",
            problem_type="api_response",
            summary="empty",
        )
    )

    result = service.update_problem_record("upd_005")
    assert result["success"] is False
    assert result["error_code"] == "problem_update_empty"


def test_update_problem_record_not_found(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    result = service.update_problem_record("nonexistent", status="resolved")
    assert result["success"] is False
    assert result["error_code"] == "problem_not_found"


def test_update_problem_record_syncs_assets_status(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="upd_006",
            problem_type="api_response",
            summary="with assets",
            status="open",
        )
    )
    service.storage.save_problem_assets(
        ProblemAssetRecord(
            problem_id="upd_006",
            problem_type="api_response",
            summary="with assets",
            status="open",
        )
    )

    original_record = service.storage.get_problem_record("upd_006")
    original_assets = service.storage.get_problem_assets("upd_006")
    assert original_record is not None
    assert original_assets is not None
    original_record_updated = original_record.updated_at
    original_assets_updated = original_assets.updated_at

    result = service.update_problem_record("upd_006", status="closed")
    assert result["success"] is True

    record = service.storage.get_problem_record("upd_006")
    assets = service.storage.get_problem_assets("upd_006")
    assert record is not None
    assert assets is not None
    assert assets.status == "closed"
    assert record.updated_at != original_record_updated
    assert assets.updated_at != original_assets_updated
    assert record.updated_at == assets.updated_at


def test_update_problem_record_notes_empty_string_clears(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="upd_007",
            problem_type="api_response",
            summary="clear notes",
            notes="old note",
        )
    )

    result = service.update_problem_record("upd_007", notes="")
    assert result["success"] is True
    assert result["problem"]["notes"] == ""

    record = service.storage.get_problem_record("upd_007")
    assert record is not None
    assert record.notes == ""


def test_update_problem_record_then_list_by_status(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="upd_008",
            problem_type="api_response",
            summary="listable",
            status="open",
            object_refs=["svc"],
        )
    )

    service.update_problem_record("upd_008", status="resolved")
    results = service.list_problem_records(status="resolved")
    assert len(results) == 1
    assert results[0]["problem_id"] == "upd_008"


def test_verification_summary_no_history(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_001",
            problem_type="api_response",
            summary="no history",
        )
    )

    result = service.get_problem_record("vs_001")
    assert result["success"] is True
    vs = result["problem"]["verification_summary"]
    assert vs["status"] == "open"
    assert vs["history_count"] == 0
    assert vs["has_notes"] is False
    assert vs["last_verified_at"] is None
    assert vs["last_action"] is None
    assert vs["latest_replay"]["available"] is False
    assert vs["latest_recover"]["available"] is False
    assert vs["suggested_next_action"]["action"] == "run_replay_or_recover"


def test_verification_summary_after_multiple_replays(
    tmp_path: Path, monkeypatch
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "vs_case",
        {
            "type": "api",
            "request": {"method": "GET", "url": "https://example.test/vs"},
            "expected_status": 200,
        },
    )

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(404, {"message": "missing"}),
    )
    service.run_case("vs_case")
    problems = service.list_problem_records(case_id="vs_case")
    problem_id = problems[0]["problem_id"]

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok"}),
    )
    service.replay_problem(problem_id)

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok again"}),
    )
    service.replay_problem(problem_id)

    result = service.get_problem_record(problem_id)
    vs = result["problem"]["verification_summary"]
    assert vs["history_count"] == 2
    assert vs["latest_replay"]["available"] is True
    assert vs["latest_replay"]["reproduced"] is False
    assert vs["last_action"] is not None
    assert vs["last_action"]["action_type"] == "replay"
    assert vs["last_verified_at"] is not None
    assert vs["suggested_next_action"]["action"] == "update_status"


def test_verification_summary_resolved_gives_no_action(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_003",
            problem_type="api_response",
            summary="resolved",
            status="resolved",
        )
    )

    result = service.get_problem_record("vs_003")
    vs = result["problem"]["verification_summary"]
    assert vs["status"] == "resolved"
    assert vs["suggested_next_action"]["action"] == "no_action"


def test_verification_summary_closed_gives_no_action(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_004",
            problem_type="api_response",
            summary="closed",
            status="closed",
        )
    )

    result = service.get_problem_record("vs_004")
    vs = result["problem"]["verification_summary"]
    assert vs["suggested_next_action"]["action"] == "no_action"


def test_verification_summary_fallback_from_recovery_json(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_005",
            problem_type="api_response",
            summary="fallback",
        )
    )
    service.storage.save_problem_recovery(
        ProblemRecoveryRecord(
            action_id="recovery_vs_005",
            problem_id="vs_005",
            problem_type="api_response",
            action_type="replay",
            mode="request_replay",
            success=True,
            status="completed",
            created_at="2026-05-02T10:00:00",
        )
    )

    result = service.get_problem_record("vs_005")
    vs = result["problem"]["verification_summary"]
    assert vs["history_count"] == 1
    assert vs["last_action"]["action_id"] == "recovery_vs_005"
    assert vs["latest_replay"]["available"] is True
    assert vs["latest_replay"]["reproduced"] is None
    assert vs["suggested_next_action"]["action"] == "inspect_history"


def test_verification_summary_recover_without_replay(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_006",
            problem_type="data_state",
            summary="recover only",
        )
    )
    service.storage.save_problem_recovery_history(
        ProblemRecoveryRecord(
            action_id="recovery_vs_006",
            problem_id="vs_006",
            problem_type="data_state",
            action_type="recover",
            mode="plan_only",
            success=True,
            status="prepared",
            created_at="2026-05-02T11:00:00",
        )
    )

    result = service.get_problem_record("vs_006")
    vs = result["problem"]["verification_summary"]
    assert vs["history_count"] == 1
    assert vs["latest_recover"]["available"] is True
    assert vs["latest_recover"]["status"] == "prepared"
    assert vs["latest_replay"]["available"] is False
    assert vs["suggested_next_action"]["action"] == "inspect_recovery_plan"


def test_verification_summary_in_assets(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_007",
            problem_type="api_response",
            summary="assets check",
            status="open",
        )
    )
    service.storage.save_problem_assets(
        ProblemAssetRecord(
            problem_id="vs_007",
            problem_type="api_response",
            summary="assets check",
            status="open",
        )
    )

    result = service.get_problem_assets("vs_007")
    assert result["success"] is True
    vs = result["assets"]["verification_summary"]
    assert vs["status"] == "open"
    assert vs["history_count"] == 0
    assert vs["suggested_next_action"]["action"] == "run_replay_or_recover"


def test_verification_summary_failed_replay_suggests_inspect_history(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_008",
            problem_type="api_response",
            summary="failed replay",
            status="open",
        )
    )
    service.storage.save_problem_recovery_history(
        ProblemRecoveryRecord(
            action_id="recovery_vs_008",
            problem_id="vs_008",
            problem_type="api_response",
            action_type="replay",
            mode="request_replay",
            success=False,
            status="failed",
            created_at="2026-05-02T12:00:00",
        )
    )

    result = service.get_problem_record("vs_008")
    vs = result["problem"]["verification_summary"]
    assert vs["latest_replay"]["available"] is True
    assert vs["latest_replay"]["reproduced"] is None
    assert vs["suggested_next_action"]["action"] == "inspect_history"
    assert "failed" in vs["suggested_next_action"]["reason"]


def test_verification_summary_can_replay_from_assets_metadata(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_010",
            problem_type="api_response",
            summary="can_replay from assets",
            status="open",
        )
    )
    service.storage.save_problem_assets(
        ProblemAssetRecord(
            problem_id="vs_010",
            problem_type="api_response",
            summary="can_replay from assets",
            status="open",
            metadata={"capabilities": {"can_replay": True, "can_recover": True}},
        )
    )
    service.storage.save_problem_recovery_history(
        ProblemRecoveryRecord(
            action_id="recovery_vs_010",
            problem_id="vs_010",
            problem_type="api_response",
            action_type="recover",
            mode="plan_only",
            success=True,
            status="prepared",
            created_at="2026-05-02T14:00:00",
        )
    )

    result = service.get_problem_record("vs_010")
    vs = result["problem"]["verification_summary"]
    assert vs["latest_recover"]["available"] is True
    assert vs["latest_replay"]["available"] is False
    assert vs["suggested_next_action"]["action"] == "run_replay"


def test_verification_summary_recover_with_can_replay_suggests_run_replay(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="vs_009",
            problem_type="api_response",
            summary="recover with can_replay",
            status="open",
            metadata={"capabilities": {"can_replay": True, "can_recover": True}},
        )
    )
    service.storage.save_problem_recovery_history(
        ProblemRecoveryRecord(
            action_id="recovery_vs_009",
            problem_id="vs_009",
            problem_type="api_response",
            action_type="recover",
            mode="request_replay",
            success=True,
            status="prepared",
            created_at="2026-05-02T13:00:00",
        )
    )

    result = service.get_problem_record("vs_009")
    vs = result["problem"]["verification_summary"]
    assert vs["latest_recover"]["available"] is True
    assert vs["latest_replay"]["available"] is False
    assert vs["suggested_next_action"]["action"] == "run_replay"


def test_list_problem_records_with_assets_summary(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="as_001",
            problem_type="api_response",
            summary="api problem with assets",
            status="open",
        )
    )
    service.storage.save_problem_assets(
        ProblemAssetRecord(
            problem_id="as_001",
            problem_type="api_response",
            summary="api problem with assets",
            recovery={"supported": True, "mode": "request_replay"},
            details={},
        )
    )

    result = service.list_problem_records(include_assets_summary=True)
    assert len(result) == 1
    assert "assets_summary" in result[0]
    summary = result[0]["assets_summary"]
    assert summary["problem_id"] == "as_001"
    assert summary["assets_available"] is True

    result_no_summary = service.list_problem_records(include_assets_summary=False)
    assert "assets_summary" not in result_no_summary[0]


def test_list_problem_records_assets_missing_summary(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="as_002",
            problem_type="crash_dump",
            summary="crash without assets",
            status="open",
        )
    )

    result = service.list_problem_records(include_assets_summary=True)
    assert len(result) == 1
    summary = result[0]["assets_summary"]
    assert summary["problem_id"] == "as_002"
    assert summary["assets_available"] is False


def test_list_problem_records_filters_with_assets_summary(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="as_003",
            problem_type="api_response",
            summary="api",
            status="open",
            object_refs=["svc_a"],
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="as_004",
            problem_type="data_state",
            summary="data",
            status="open",
            object_refs=["svc_b"],
        )
    )

    result = service.list_problem_records(
        object_name="svc_a", include_assets_summary=True
    )
    assert len(result) == 1
    assert result[0]["problem_id"] == "as_003"
    assert "assets_summary" in result[0]


def test_execution_artifacts_includes_problem_summary(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    exec_id = "exec_problem_summary"
    service.storage.save_execution(
        ExecutionRecord(
            execution_id=exec_id,
            case_id="case_ps",
            status="failed",
            duration=0.1,
            start_time="2026-05-03T10:00:00",
            end_time="2026-05-03T10:00:01",
        )
    )
    artifact_dir = tmp_path / ".ptest" / "artifacts" / exec_id / "indexes"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "artifact_index.json").write_text("{}", encoding="utf-8")

    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="ps_exec_001",
            problem_type="api_response",
            summary="linked to exec",
            execution_id=exec_id,
        )
    )

    result = service.get_execution_artifacts(exec_id)
    assert result["success"] is True
    problem_summary = result["artifacts"]["problem_summary"]
    assert problem_summary["total_count"] == 1
    assert problem_summary["recent_problems"][0]["problem_id"] == "ps_exec_001"


def test_object_status_diagnostics_includes_problem_summary(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="svc_diag",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="diag_001",
            problem_type="service_runtime",
            summary="runtime issue",
            object_refs=["svc_diag"],
        )
    )

    result = service.get_object_status("svc_diag")
    assert result["success"] is True
    diagnostics = result["object"]["diagnostics"]
    assert "problem_summary" in diagnostics
    assert diagnostics["problem_summary"]["total_count"] == 1
    assert (
        diagnostics["problem_summary"]["recent_problems"][0]["problem_id"] == "diag_001"
    )


def test_object_problem_summary_ordering_and_limit(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="svc_many",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
        )
    )

    for i in range(12):
        service.storage.save_problem_record(
            ProblemRecord(
                problem_id=f"multi_{i:03}",
                problem_type="api_response",
                summary=f"problem #{i}",
                object_refs=["svc_many"],
                created_at=f"2026-05-01T10:00:{i:02d}",
            )
        )

    result = service.get_object_status("svc_many")
    assert result["success"] is True
    summary = result["object"]["diagnostics"]["problem_summary"]
    assert summary["total_count"] == 12
    assert len(summary["recent_problems"]) == 10

    recent_ids = [p["problem_id"] for p in summary["recent_problems"]]
    expected_ids = [f"multi_{i:03}" for i in range(11, 1, -1)]
    assert recent_ids == expected_ids


def test_list_problem_records_corrupted_assets_graceful_degradation(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="corrupt_001",
            problem_type="api_response",
            summary="corrupted assets",
        )
    )

    assets_dir = tmp_path / ".ptest" / "problems" / "corrupt_001"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "assets.json").write_text("{invalid json", encoding="utf-8")

    result = service.list_problem_records(include_assets_summary=True)
    assert len(result) == 1
    summary = result[0]["assets_summary"]
    assert summary["assets_available"] is False
    assert summary["diagnostics_status"] == "unavailable"
    assert "error" in summary


def test_build_problem_asset_summary_default_diagnostics_unavailable(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="diag_default_001",
            problem_type="api_response",
            summary="no assets",
        )
    )

    result = service.list_problem_records(include_assets_summary=True)
    summary = result[0]["assets_summary"]
    assert summary["diagnostics_status"] == "unavailable"


def test_problem_collection_suggested_views_are_structured(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.storage.upsert_object(
        ManagedObjectRecord(
            name="svc_sv",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
        )
    )
    service.storage.save_problem_record(
        ProblemRecord(
            problem_id="sv_001",
            problem_type="api_response",
            summary="structured views",
            object_refs=["svc_sv"],
        )
    )

    result = service.get_object_status("svc_sv")
    summary = result["object"]["diagnostics"]["problem_summary"]
    views = summary["suggested_views"]
    assert len(views) >= 1
    for view in views:
        assert "view" in view
        assert "command" in view
        assert "reason" in view
