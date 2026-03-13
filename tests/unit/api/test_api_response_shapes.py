from __future__ import annotations

from pathlib import Path

from ptest.api import PTestAPI


def test_api_returns_structured_environment_responses(tmp_path: Path) -> None:
    api = PTestAPI(work_path=str(tmp_path))

    init_result = api.init_environment()
    assert init_result["success"] is True
    assert init_result["status"] == "ready"
    assert init_result["data"]["root_path"] == str(tmp_path.resolve())

    status_result = api.get_environment_status()
    assert status_result["success"] is True
    assert status_result["status"] == "ready"
    assert status_result["data"]["path"] == str(tmp_path.resolve())


def test_api_returns_structured_case_responses(tmp_path: Path) -> None:
    api = PTestAPI(work_path=str(tmp_path))
    api.init_environment()

    create_result = api.create_test_case(
        test_type="database",
        name="sqlite_case",
        content={
            "type": "database",
            "db_type": "sqlite",
            "database": str(tmp_path / "sample.db"),
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    assert create_result["success"] is True
    case_id = create_result["data"]["case_id"]

    list_result = api.list_test_cases()
    assert list_result["success"] is True
    assert isinstance(list_result["data"], list)
    assert any(item["id"] == case_id for item in list_result["data"])

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is True
    assert run_result["status"] == "passed"
    assert "message" in run_result

    records_result = api.list_execution_records(case_id=case_id)
    assert records_result["success"] is True
    execution_id = records_result["data"][0]["execution_id"]

    execution_result = api.get_execution_record(execution_id)
    assert execution_result["success"] is True
    assert execution_result["data"]["execution_id"] == execution_id

    artifacts_result = api.get_execution_artifacts(execution_id)
    assert artifacts_result["success"] is True
    assert artifacts_result["data"]["execution_id"] == execution_id
    assert artifacts_result["data"]["files"]["execution"].endswith(
        "result/execution.json"
    )
