from __future__ import annotations

import tarfile
from pathlib import Path
from typing import Any

import requests
import pytest

from ptest.app import WorkflowService
from ptest.models import ManagedObjectRecord, ProblemAssetRecord, ProblemRecord
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
    assert problem["problem"]["metadata"]["preservation"]["status"] == "partial"
    assert problem["problem"]["metadata"]["capabilities"]["can_replay"] is True
    assert problem["problem"]["metadata"]["capabilities"]["can_recover"] is True
    assert problem["problem"]["capabilities"]["can_replay"] is True
    assert problem["problem"]["preservation"]["status"] == "partial"

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
    assert assets["assets"]["preservation_status"] == "partial"
    assert assets["assets"]["details"]["preservation"]["missing_assets"] == [
        "log_index"
    ]
    assert (
        assets["assets"]["details"]["preservation"]["missing_reasons"]["log_index"]
        == "log index is not available"
    )
    assert assets["assets"]["metadata"]["preservation"]["status"] == "partial"
    assert assets["assets"]["metadata"]["capabilities"]["can_replay"] is True
    assert assets["assets"]["capabilities"]["can_replay"] is True
    assert assets["assets"]["preservation"]["status"] == "partial"
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
    assert replay["replay"]["reproduced"] is False
    assert replay["recovery_action"]["action_type"] == "replay"
    assert replay["recovery_action"]["status"] == "completed"

    problem = service.get_problem_record(problem_id)
    assert problem["success"] is True
    assert problem["problem"]["latest_action"] == "replay:completed"
    assert problem["problem"]["metadata"]["latest_recovery"]["action_type"] == "replay"

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["metadata"]["latest_recovery"]["action_type"] == "replay"
    assert (
        assets["assets"]["metadata"]["capabilities"]["recover_mode"] == "request_replay"
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

    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["problem_type"] == "data_state"
    assert assets["assets"]["details"]["data_source"]["db_type"] == "sqlite"
    assert assets["assets"]["details"]["operations"][0]["query"] == "SELECT 1 as value"
    assert assets["assets"]["details"]["actual_result"] == [{"value": 1}]
    assert assets["assets"]["recovery"]["mode"] == "minimal_state_hints"
    assert assets["assets"]["recovery"]["supported"] is False
    assert assets["assets"]["metadata"]["preservation"]["status"] == "partial"
    assert assets["assets"]["metadata"]["capabilities"]["can_replay"] is False
    assert assets["assets"]["metadata"]["capabilities"]["can_recover"] is True
    assert assets["assets"]["capabilities"]["can_recover"] is True
    assert assets["assets"]["preservation"]["status"] == "partial"

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "data_state"
    assert recovery["recovery"]["mode"] == "minimal_state_hints"
    assert recovery["recovery"]["actual_result"] == [{"value": 1}]
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
    assert assets["assets"]["recovery"]["mode"] == "basic_runtime_validation"

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["problem_type"] == "service_runtime"
    assert recovery["recovery"]["mode"] == "basic_runtime_validation"


def test_workflow_service_rejects_recover_for_unsupported_problem_type(
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
    assert recovery["success"] is False
    assert recovery["error_code"] == "problem_recover_unsupported"
