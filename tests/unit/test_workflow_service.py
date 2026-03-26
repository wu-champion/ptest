from __future__ import annotations

import json
from pathlib import Path

from ptest.app import WorkflowService
from ptest.contract.manager import APIContract, APIEndpoint, ContractManager
from ptest.mock import MockConfig, MockServer


def _normalized_path(path: str) -> str:
    return path.replace("\\", "/")


def test_workflow_service_persists_environment_and_objects(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    record = service.init_environment()

    assert record.root_path == str(tmp_path.resolve())
    assert (tmp_path / ".ptest" / "environment.json").exists()
    assert record.metadata["isolation"]["env_id"].startswith("env_")
    assert record.metadata["isolation"]["isolation_level"] == "basic"
    assert record.metadata["isolation"]["recovery_strategy"] == "created_new"
    assert record.metadata["isolation"]["validated"] is True
    assert record.metadata["isolation"]["health"] is True

    install_result = service.install_object("service", "demo_service")
    assert install_result["success"] is True

    start_result = service.start_object("demo_service")
    assert start_result["success"] is True

    reloaded = WorkflowService(tmp_path)
    status = reloaded.get_object_status("demo_service")
    assert status["success"] is True
    assert status["object"]["status"] == "installed"
    assert (
        status["object"]["metadata"]["recovery"]["mode"]
        == "downgraded_nonrecoverable_runtime"
    )

    tool_install = service.install_tool("demo_tool", {"version": "1.0"})
    assert tool_install["success"] is True

    tool_start = service.start_tool("demo_tool")
    assert tool_start["success"] is True

    reloaded_tool = WorkflowService(tmp_path)
    tool_status = reloaded_tool.get_tool_status("demo_tool")
    assert tool_status["success"] is True
    assert tool_status["tool"]["status"] == "running"


def test_workflow_service_reuses_persisted_isolation_level(tmp_path: Path) -> None:
    service = WorkflowService(
        tmp_path,
        config={"default_isolation_level": "basic"},
    )
    initial = service.init_environment()

    reloaded = WorkflowService(
        tmp_path,
        config={"default_isolation_level": "unsupported"},
    )
    recovered = reloaded.init_environment()

    assert (
        initial.metadata["isolation"]["env_id"]
        == recovered.metadata["isolation"]["env_id"]
    )
    assert recovered.metadata["isolation"]["isolation_level"] == "basic"
    assert recovered.metadata["isolation"]["attached"] is True
    assert recovered.metadata["isolation"]["recovery_strategy"] in {
        "attached_active",
        "reattached_recreated",
    }
    assert recovered.metadata["isolation"]["validated"] is True


def test_workflow_service_recovers_database_runtime_state(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    install_result = service.install_object(
        "database",
        "demo_db",
        {
            "db_type": "sqlite",
            "driver": "sqlite",
            "database": str(tmp_path / "runtime.db"),
        },
    )
    assert install_result["success"] is True

    start_result = service.start_object("demo_db")
    assert start_result["success"] is True

    reloaded = WorkflowService(tmp_path)
    status = reloaded.get_object_status("demo_db")
    assert status["success"] is True
    assert status["object"]["status"] == "running"
    assert status["object"]["metadata"]["recovery"]["mode"] == "rebuild_connector"
    assert status["object"]["metadata"]["recovery"]["recovered"] is True


def test_workflow_service_runs_case_and_generates_report(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    db_path = tmp_path / "sample.db"
    case_data = {
        "type": "database",
        "db_type": "sqlite",
        "database": str(db_path),
        "query": "SELECT 1 as value",
        "expected_result": [{"value": 1}],
    }

    add_result = service.add_case("sqlite_smoke", case_data)
    assert add_result["success"] is True

    run_result = service.run_case("sqlite_smoke")
    assert run_result["success"] is True
    assert run_result["status"] == "passed"

    report_path = Path(service.generate_report("json"))
    assert report_path.exists()
    assert report_path.parent == tmp_path / "reports"

    executions = service.list_execution_records("sqlite_smoke")
    assert len(executions) == 1
    assert executions[0]["status"] == "passed"
    artifact_dir = tmp_path / ".ptest" / "artifacts" / executions[0]["execution_id"]
    assert artifact_dir.exists()
    assert (artifact_dir / "context" / "environment.json").exists()
    assert (artifact_dir / "context" / "objects.json").exists()
    assert (artifact_dir / "case" / "case.json").exists()
    assert (artifact_dir / "result" / "result.json").exists()
    assert (artifact_dir / "result" / "execution.json").exists()
    assert (artifact_dir / "indexes" / "artifact_index.json").exists()
    assert (artifact_dir / "logs" / "log_index.json").exists()
    artifacts = executions[0]["metadata"]["artifacts"]
    assert _normalized_path(artifacts["directory"]).startswith(".ptest/artifacts/")
    assert _normalized_path(artifacts["files"]["environment"]).endswith(
        "context/environment.json"
    )
    assert _normalized_path(artifacts["files"]["execution"]).endswith(
        "result/execution.json"
    )
    assert _normalized_path(artifacts["indexes"]["artifact_index"]).endswith(
        "indexes/artifact_index.json"
    )
    assert _normalized_path(artifacts["indexes"]["log_index"]).endswith(
        "logs/log_index.json"
    )
    artifact_index = json.loads(
        (artifact_dir / "indexes" / "artifact_index.json").read_text(encoding="utf-8")
    )
    log_index = json.loads(
        (artifact_dir / "logs" / "log_index.json").read_text(encoding="utf-8")
    )
    assert _normalized_path(artifact_index["files"]["execution"]).endswith(
        "result/execution.json"
    )
    assert _normalized_path(artifact_index["indexes"]["log_index"]).endswith(
        "logs/log_index.json"
    )
    assert log_index["workspace_logs_dir"] == "logs"

    suite_result = service.create_suite(
        {
            "name": "sqlite_suite",
            "cases": [
                {
                    "case_id": "sqlite_smoke",
                    "order": 1,
                }
            ],
        }
    )
    assert suite_result["success"] is True

    suite_run = service.run_suite("sqlite_suite")
    assert suite_run["success"] is True
    assert suite_run["total"] == 1

    suites = service.list_suites()
    assert "sqlite_suite" in suites

    destroy_result = service.destroy_environment()
    assert destroy_result["success"] is True
    assert destroy_result["isolation_cleanup"]["success"] is True
    artifact_root = tmp_path / ".ptest" / "artifacts"
    assert artifact_root.exists()
    assert list(artifact_root.iterdir()) == []

    env_status = service.get_environment_status()
    assert env_status["initialized"] is False
    assert env_status["status"] == "destroyed"


def test_workflow_service_can_reinitialize_after_destroy(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)

    first = service.init_environment()
    assert first.status == "ready"

    destroyed = service.destroy_environment()
    assert destroyed["success"] is True

    second = service.init_environment()
    assert second.status == "ready"
    assert second.root_path == str(tmp_path.resolve())
    assert second.metadata["isolation"]["env_id"]


def test_workflow_service_supports_data_contract_and_mock_workspace_assets(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    save_template = service.save_data_template(
        "user_template",
        {"username": "{{username}}", "email": "{{email}}"},
    )
    assert save_template["success"] is True

    template_list = service.list_data_templates()
    assert template_list["success"] is True
    assert "user_template" in template_list["data"]

    generated = service.generate_data_from_template("user_template", count=2)
    assert generated["success"] is True
    assert len(generated["data"]["results"]) == 2

    contract_manager = ContractManager(tmp_path / ".ptest" / "contracts")
    contract_manager._save_contract(  # noqa: SLF001
        APIContract(
            name="demo_contract",
            version="1.0.0",
            title="Demo",
            endpoints=[
                APIEndpoint(
                    path="/health",
                    method="GET",
                    summary="health",
                    responses={"200": {"description": "ok"}},
                )
            ],
        )
    )

    contract_list = service.list_contracts()
    assert contract_list["success"] is True
    assert "demo_contract" in contract_list["data"]

    generated_cases = service.generate_cases_from_contract(
        "demo_contract", persist=True
    )
    assert generated_cases["success"] is True
    assert generated_cases["data"]["persisted_case_ids"]

    mock_server = MockServer(MockConfig(name="demo_mock", port=18080))
    mock_server.save_config(tmp_path / ".ptest" / "mocks" / "demo_mock.json")

    mock_list = service.list_mock_servers()
    assert mock_list["success"] is True
    assert any(item["name"] == "demo_mock" for item in mock_list["data"])

    route_result = service.add_mock_route(
        "demo_mock",
        "/health",
        "GET",
        {"status": 200, "body": {"ok": True}},
    )
    assert route_result["success"] is True

    mock_status = service.get_mock_server_status("demo_mock")
    assert mock_status["success"] is True
    assert mock_status["data"]["name"] == "demo_mock"
    assert len(mock_status["data"]["routes"]) == 1


def test_workflow_service_returns_structured_contract_import_errors(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    result = service.import_contract(tmp_path / "missing-openapi.yaml")

    assert result["success"] is False
    assert result["status"] == "error"
    assert result["error_code"] in {
        "contract_import_failed",
        "contract_import_dependency_missing",
    }


def test_workflow_service_marks_detached_mock_runtime_as_stale(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    mock_server = MockServer(MockConfig(name="detached_mock", port=18081))
    mock_server.save_config(tmp_path / ".ptest" / "mocks" / "detached_mock.json")
    service._save_mock_state("detached_mock", {"status": "running"})  # noqa: SLF001

    reloaded = WorkflowService(tmp_path)
    status = reloaded.get_mock_server_status("detached_mock")

    assert status["success"] is True
    assert status["status"] == "stale"
    assert status["data"]["running"] is False
    assert status["data"]["runtime_state"]["status"] == "running"
