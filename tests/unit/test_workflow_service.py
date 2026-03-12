from __future__ import annotations

from pathlib import Path

from ptest.app import WorkflowService


def test_workflow_service_persists_environment_and_objects(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    record = service.init_environment()

    assert record.root_path == str(tmp_path.resolve())
    assert (tmp_path / ".ptest" / "environment.json").exists()
    assert record.metadata["isolation"]["env_id"].startswith("env_")
    assert record.metadata["isolation"]["isolation_level"] == "basic"

    install_result = service.install_object("service", "demo_service")
    assert install_result["success"] is True

    start_result = service.start_object("demo_service")
    assert start_result["success"] is True

    reloaded = WorkflowService(tmp_path)
    status = reloaded.get_object_status("demo_service")
    assert status["success"] is True
    assert status["object"]["status"] == "running"

    tool_install = service.install_tool("demo_tool", {"version": "1.0"})
    assert tool_install["success"] is True

    tool_start = service.start_tool("demo_tool")
    assert tool_start["success"] is True

    reloaded_tool = WorkflowService(tmp_path)
    tool_status = reloaded_tool.get_tool_status("demo_tool")
    assert tool_status["success"] is True
    assert tool_status["tool"]["status"] == "running"


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
    assert (artifact_dir / "environment.json").exists()
    assert (artifact_dir / "objects.json").exists()
    assert (artifact_dir / "case.json").exists()
    assert (artifact_dir / "result.json").exists()
    assert (artifact_dir / "execution.json").exists()
    assert executions[0]["metadata"]["artifacts"]["directory"].startswith(
        ".ptest/artifacts/"
    )

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
