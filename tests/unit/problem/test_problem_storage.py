from __future__ import annotations

from pathlib import Path

from ptest.models import ProblemAssetRecord, ProblemRecord, ProblemRecoveryRecord
from ptest.storage import WorkspaceStorage


def test_workspace_storage_persists_problem_records_and_assets(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    record = ProblemRecord(
        problem_id="problem_exec_001",
        problem_type="api_response",
        summary="API response problem",
        execution_id="exec_001",
        case_id="api_case_001",
        environment_id="env_001",
        object_refs=["gateway"],
    )
    assets = ProblemAssetRecord(
        problem_id="problem_exec_001",
        problem_type="api_response",
        summary="API response problem",
        execution_id="exec_001",
        case_id="api_case_001",
        environment_id="env_001",
        object_refs=["gateway"],
        recovery={"replay": {"method": "GET", "url": "https://example.test/health"}},
        details={"request": {"method": "GET", "url": "https://example.test/health"}},
    )

    storage.save_problem_record(record)
    storage.save_problem_assets(assets)

    loaded_record = storage.get_problem_record("problem_exec_001")
    loaded_assets = storage.get_problem_assets("problem_exec_001")
    execution_records = storage.list_problem_records_for_execution("exec_001")
    case_records = storage.list_problem_records_for_case("api_case_001")

    assert loaded_record is not None
    assert loaded_record.problem_type == "api_response"
    assert loaded_assets is not None
    assert loaded_assets.recovery["replay"]["url"] == "https://example.test/health"
    assert storage.list_problem_ids_for_execution("exec_001") == ["problem_exec_001"]
    assert storage.list_problem_ids_for_case("api_case_001") == ["problem_exec_001"]
    assert [item.problem_id for item in execution_records] == ["problem_exec_001"]
    assert [item.problem_id for item in case_records] == ["problem_exec_001"]

    recovery = ProblemRecoveryRecord(
        action_id="recovery_001",
        problem_id="problem_exec_001",
        problem_type="api_response",
        action_type="replay",
        mode="request_replay",
        success=True,
        status="completed",
        execution_id="exec_001",
        case_id="api_case_001",
        environment_id="env_001",
        metadata={"result": {"response": {"status_code": 200}}},
    )
    storage.save_problem_recovery(recovery)

    loaded_recovery = storage.get_problem_recovery("problem_exec_001")
    assert loaded_recovery is not None
    assert loaded_recovery.action_type == "replay"
    assert loaded_recovery.mode == "request_replay"


def test_workspace_storage_persists_problem_recovery_history(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    record = ProblemRecord(
        problem_id="problem_history_001",
        problem_type="api_response",
        summary="history test",
    )
    storage.save_problem_record(record)

    recovery_1 = ProblemRecoveryRecord(
        action_id="recovery_hist_001",
        problem_id="problem_history_001",
        problem_type="api_response",
        action_type="replay",
        mode="request_replay",
        success=True,
        status="completed",
        created_at="2026-05-01T10:00:00",
    )
    recovery_2 = ProblemRecoveryRecord(
        action_id="recovery_hist_002",
        problem_id="problem_history_001",
        problem_type="api_response",
        action_type="recover",
        mode="plan_only",
        success=True,
        status="prepared",
        created_at="2026-05-01T11:00:00",
    )

    storage.save_problem_recovery_history(recovery_1)
    storage.save_problem_recovery_history(recovery_2)

    history = storage.list_problem_recovery_history("problem_history_001")
    assert len(history) == 2
    assert history[0].action_id == "recovery_hist_002"
    assert history[1].action_id == "recovery_hist_001"


def test_workspace_storage_recovery_history_empty_when_no_history(
    tmp_path: Path,
) -> None:
    storage = WorkspaceStorage(tmp_path)
    history = storage.list_problem_recovery_history("nonexistent_problem")
    assert history == []
