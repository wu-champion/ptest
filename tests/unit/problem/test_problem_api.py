from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from ptest.api import PTestAPI
from ptest.models import ProblemRecord


class _FakeResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = {"content-type": "application/json"}
        self.text = str(body)

    def json(self) -> Any:
        return self._body


def test_api_exposes_problem_records(tmp_path: Path, monkeypatch) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    created = api.create_test_case(
        "api",
        "demo",
        content={
            "request": {"method": "GET", "url": "https://example.test/api/demo"},
            "expected_status": 200,
        },
    )
    case_id = created["data"]["case_id"]

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(500, {"error": "boom"}),
    )
    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id)
    assert problems["success"] is True
    assert len(problems["data"]) == 1
    assert len(problems["problems"]) == 1
    assert problems["count"] == 1
    assert problems["filters"] == {"case_id": case_id}

    problem_id = problems["data"][0]["problem_id"]
    detail = api.get_problem_record(problem_id)
    assert detail["success"] is True
    assert detail["data"]["problem_type"] == "api_response"
    assert detail["problem"]["problem_type"] == "api_response"
    assert detail["data"]["metadata"]["capabilities"]["can_replay"] is True
    assert detail["data"]["metadata"]["capabilities"]["can_recover"] is True
    assert detail["data"]["capabilities"]["can_replay"] is True
    assert detail["data"]["preservation"]["status"] == "success"
    assert detail["problem"]["investigation"]["view"] == "problem"
    assert detail["problem"]["investigation"]["request"]["url"] == (
        "https://example.test/api/demo"
    )
    assert detail["problem"]["investigation"]["workspace_recovery"]["scope"] == (
        "workspace_minimum_recovery"
    )

    assets = api.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["problem_type"] == "api_response"
    assert assets["assets"]["capabilities"]["can_replay"] is True
    assert (
        assets["assets"]["reproduction_summary"]["request"]["url"]
        == "https://example.test/api/demo"
    )
    assert assets["assets"]["reproduction_summary"]["expected"]["status_code"] == 200
    assert assets["assets"]["reproduction_summary"]["recommended_commands"] == [
        f"ptest problem show {problem_id}",
        f"ptest problem assets {problem_id}",
        f"ptest problem replay {problem_id}",
    ]
    assert (
        assets["assets"]["reproduction_summary"]["side_effect_hints"]["classification"]
        == "no_recent_side_effect_signal"
    )
    assert assets["assets"]["investigation"]["view"] == "assets"
    assert assets["assets"]["investigation"]["request"]["url"] == (
        "https://example.test/api/demo"
    )
    assert assets["assets"]["investigation"]["side_effect"]["classification"] == (
        "no_recent_side_effect_signal"
    )
    assert (
        assets["assets"]["investigation"]["environment_recovery"]["assessment"]
        == "no_prior_side_effect_signal_detected"
    )


def test_api_exposes_data_problem_recovery_plan(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    created = api.create_test_case(
        "database",
        "sqlite_failure",
        content={
            "db_type": "sqlite",
            "database": str(tmp_path / "sample.db"),
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 2}],
        },
    )
    case_id = created["data"]["case_id"]

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id, problem_type="data_state")
    assert problems["success"] is True
    assert len(problems["data"]) == 1

    detail = api.get_problem_record(problems["data"][0]["problem_id"])
    assert detail["success"] is True
    assert detail["problem"]["investigation"]["data_source"]["db_type"] == "sqlite"
    assert detail["problem"]["investigation"]["failure_kind"] == "value_mismatch"
    assert detail["problem"]["investigation"]["origin_hints"]["classification"] == (
        "stale_field_values"
    )
    assert detail["problem"]["investigation"]["boundary"]["scope"] == (
        "query_level_plan"
    )
    assert detail["problem"]["investigation"]["workspace_recovery"]["scope"] == (
        "workspace_minimum_recovery"
    )

    recovery = api.recover_problem(problems["data"][0]["problem_id"])
    assert recovery["success"] is True
    assert recovery["data"]["problem_type"] == "data_state"
    assert recovery["recovery"]["problem_type"] == "data_state"
    assert recovery["data"]["mode"] == "minimal_state_hints"
    assert recovery["data"]["actual_result"] == [{"value": 1}]
    assert recovery["data"]["failure_kind"] == "value_mismatch"
    assert recovery["data"]["state_hints"]["mismatched_fields"] == ["value"]
    assert recovery["data"]["origin_hints"]["classification"] == "stale_field_values"
    assert recovery["data"]["boundary"]["scope"] == "query_level_plan"
    assert recovery["data"]["boundary"]["needs_historical_state"] is False
    assert recovery["data"]["suggested_repairs"][0]["action"] == (
        "align_key_field_values"
    )
    assert recovery["data"]["workspace_recovery"]["scope"] == (
        "workspace_minimum_recovery"
    )
    assert recovery["data"]["workspace_recovery"]["recovery_boundary"]["scope"] == (
        "workspace_minimum_recovery"
    )
    assert recovery["recovery_action"]["action_type"] == "recover"

    latest_recovery = api.get_problem_recovery(problems["data"][0]["problem_id"])
    assert latest_recovery["success"] is True
    assert latest_recovery["data"]["status"] == "prepared"
    assert latest_recovery["recovery_action"]["status"] == "prepared"

    replay = api.replay_problem(problems["data"][0]["problem_id"])
    assert replay["success"] is False
    assert replay["error_code"] == "problem_replay_unsupported"
    assert replay["replay"] is None


def test_api_replay_exposes_comparison_summary(tmp_path: Path, monkeypatch) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    created = api.create_test_case(
        "api",
        "demo",
        content={
            "request": {"method": "GET", "url": "https://example.test/api/demo"},
            "expected_status": 200,
        },
    )
    case_id = created["data"]["case_id"]

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(404, {"message": "missing"}),
    )
    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id)
    problem_id = problems["data"][0]["problem_id"]

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok"}),
    )
    replay = api.replay_problem(problem_id)

    assert replay["success"] is True
    assert replay["replay"]["comparison"]["original_failure"]["status_code"] == 404
    assert replay["replay"]["comparison"]["replay_response"]["status_code"] == 200
    assert replay["replay"]["comparison"]["status_code_changed"] is True
    assert replay["replay"]["comparison"]["expectation"]["reproduced"] is False
    assert replay["replay"]["comparison"]["assertion_outcome"] == "not_reproduced"
    assert replay["replay"]["comparison"]["boundary"]["scope"] == "request_level"
    assert replay["replay"]["comparison"]["boundary"]["confidence"] == "request_only"
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
    assert replay["replay"]["comparison"]["summary"]["status"]["changed"] is True
    assert replay["replay"]["comparison"]["summary"]["status"]["from"] == 404
    assert replay["replay"]["comparison"]["summary"]["status"]["to"] == 200
    assert replay["replay"]["comparison"]["summary"]["boundary"]["assessment"] == (
        "diverged_from_preserved_failure"
    )
    assert replay["replay"]["comparison"]["summary"]["headers"]["comparable"] is False
    assert (
        replay["replay"]["comparison"]["summary"]["body"]["change_kind"]
        == "preserved_body_unavailable"
    )
    assert replay["replay"]["comparison"]["summary"]["body"]["comparable"] is False
    assert replay["replay"]["comparison"]["summary"]["body"]["replay_preview"] == {
        "message": "ok"
    }
    assert (
        "replay no longer reproduces the original problem"
        in replay["replay"]["comparison"]["highlights"]
    )
    assert (
        "current replay only reruns the preserved request and may miss prior state changes or hidden dependencies"
        in replay["replay"]["comparison"]["highlights"]
    )
    assert replay["replay"]["investigation"]["view"] == "replay"
    assert replay["replay"]["investigation"]["replay"]["assessment"] == (
        "diverged_from_preserved_failure"
    )
    assert replay["replay"]["reproduced"] is False


def test_api_problem_list_reports_empty_results_with_filters(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()

    problems = api.list_problem_records(
        problem_type="service_runtime",
        case_id="missing_case",
    )

    assert problems["success"] is True
    assert problems["data"] == []
    assert problems["problems"] == []
    assert problems["count"] == 0
    assert problems["filters"] == {
        "problem_type": "service_runtime",
        "case_id": "missing_case",
    }


def test_api_list_problem_records_passes_new_filters(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_filter_001",
            problem_type="api_response",
            summary="api problem",
            status="open",
            environment_id="env_prod",
            object_refs=["my_service"],
            metadata={"capabilities": {"can_replay": True, "can_recover": True}},
        )
    )
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_filter_002",
            problem_type="data_state",
            summary="data problem",
            status="resolved",
            environment_id="env_staging",
            object_refs=["other_service"],
        )
    )

    result = api.list_problem_records(object_name="my_service")
    assert result["success"] is True
    assert result["count"] == 1
    assert result["problems"][0]["problem_id"] == "api_filter_001"
    assert result["filters"]["object_name"] == "my_service"

    result = api.list_problem_records(can_replay=True)
    assert result["count"] == 1
    assert result["problems"][0]["problem_id"] == "api_filter_001"
    assert result["filters"]["can_replay"] is True

    result = api.list_problem_records(environment_id="env_staging")
    assert result["count"] == 1
    assert result["problems"][0]["problem_id"] == "api_filter_002"


def test_api_list_problem_records_filters_contain_only_non_none(
    tmp_path: Path,
) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()

    result = api.list_problem_records(
        object_name="some_service",
        status="open",
    )
    assert result["filters"] == {
        "object_name": "some_service",
        "status": "open",
    }
    assert "environment_id" not in result["filters"]
    assert "preservation_status" not in result["filters"]
    assert "can_replay" not in result["filters"]
    assert "can_recover" not in result["filters"]


def test_api_list_problem_records_count_matches_problems_length(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="count_001",
            problem_type="api_response",
            summary="first",
            status="open",
            object_refs=["svc"],
        )
    )
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="count_002",
            problem_type="api_response",
            summary="second",
            status="open",
            object_refs=["svc"],
        )
    )

    result = api.list_problem_records(object_name="svc")
    assert result["count"] == len(result["problems"])


def test_api_list_problem_recovery_history(tmp_path: Path, monkeypatch) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    created = api.create_test_case(
        "api",
        "history_test",
        content={
            "request": {"method": "GET", "url": "https://example.test/api/history"},
            "expected_status": 200,
        },
    )
    case_id = created["data"]["case_id"]

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(404, {"message": "missing"}),
    )
    api.run_test_case(case_id)

    problems = api.list_problem_records(case_id=case_id)
    problem_id = problems["data"][0]["problem_id"]

    monkeypatch.setattr(
        requests,
        "request",
        lambda **kwargs: _FakeResponse(200, {"message": "ok"}),
    )
    api.replay_problem(problem_id)

    result = api.list_problem_recovery_history(problem_id)
    assert result["success"] is True
    assert result["count"] >= 1
    assert result["history"]["count"] >= 1
    assert len(result["actions"]) == result["count"]


def test_api_update_problem_record_status(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_upd_001",
            problem_type="api_response",
            summary="api update test",
            status="open",
            object_refs=["svc"],
        )
    )

    result = api.update_problem_record("api_upd_001", status="investigating")
    assert result["success"] is True
    assert result["data"]["status"] == "investigating"
    assert result["problem"]["latest_action"] == "status:investigating"


def test_api_update_problem_record_notes(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_upd_002",
            problem_type="api_response",
            summary="notes test",
        )
    )

    result = api.update_problem_record("api_upd_002", notes="still broken")
    assert result["success"] is True
    assert result["data"]["notes"] == "still broken"
    assert result["problem"]["latest_action"] == "note:updated"


def test_api_update_problem_record_invalid_status(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_upd_003",
            problem_type="api_response",
            summary="invalid",
        )
    )

    result = api.update_problem_record("api_upd_003", status="bogus")
    assert result["success"] is False
    assert result["error_code"] == "problem_status_invalid"


def test_api_update_problem_record_empty_update(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_upd_004",
            problem_type="api_response",
            summary="empty",
        )
    )

    result = api.update_problem_record("api_upd_004")
    assert result["success"] is False
    assert result["error_code"] == "problem_update_empty"


def test_api_get_problem_record_has_verification_summary(tmp_path: Path) -> None:
    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_vs_001",
            problem_type="api_response",
            summary="api vs test",
            status="open",
        )
    )

    result = api.get_problem_record("api_vs_001")
    assert result["success"] is True
    assert "verification_summary" in result["data"]
    assert result["data"]["verification_summary"]["history_count"] == 0
    assert result["data"]["verification_summary"]["status"] == "open"


def test_api_get_problem_assets_has_verification_summary(tmp_path: Path) -> None:
    from ptest.models import ProblemAssetRecord

    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_vs_002",
            problem_type="api_response",
            summary="api vs assets",
        )
    )
    api.workflow.storage.save_problem_assets(
        ProblemAssetRecord(
            problem_id="api_vs_002",
            problem_type="api_response",
            summary="api vs assets",
        )
    )

    result = api.get_problem_assets("api_vs_002")
    assert result["success"] is True
    assert "verification_summary" in result["data"]
    assert result["data"]["verification_summary"]["history_count"] == 0


def test_api_verification_summary_fallback_from_recovery_json(
    tmp_path: Path,
) -> None:
    from ptest.models import ProblemRecoveryRecord

    api = PTestAPI(work_path=tmp_path)
    api.init_environment()
    api.workflow.storage.save_problem_record(
        ProblemRecord(
            problem_id="api_vs_003",
            problem_type="api_response",
            summary="fallback",
        )
    )
    api.workflow.storage.save_problem_recovery(
        ProblemRecoveryRecord(
            action_id="recovery_api_vs_003",
            problem_id="api_vs_003",
            problem_type="api_response",
            action_type="replay",
            mode="request_replay",
            success=True,
            status="completed",
            created_at="2026-05-02T10:00:00",
        )
    )

    result = api.get_problem_record("api_vs_003")
    assert result["success"] is True
    vs = result["data"]["verification_summary"]
    assert vs["history_count"] == 1
    assert vs["latest_replay"]["available"] is True
