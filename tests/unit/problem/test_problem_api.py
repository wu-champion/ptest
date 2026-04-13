from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from ptest.api import PTestAPI


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
    assert detail["data"]["preservation"]["status"] == "partial"
    assert detail["problem"]["investigation"]["view"] == "problem"
    assert detail["problem"]["investigation"]["request"]["url"] == (
        "https://example.test/api/demo"
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
    assert assets["assets"]["investigation"]["view"] == "assets"
    assert assets["assets"]["investigation"]["request"]["url"] == (
        "https://example.test/api/demo"
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

    recovery = api.recover_problem(problems["data"][0]["problem_id"])
    assert recovery["success"] is True
    assert recovery["data"]["problem_type"] == "data_state"
    assert recovery["recovery"]["problem_type"] == "data_state"
    assert recovery["data"]["mode"] == "minimal_state_hints"
    assert recovery["data"]["actual_result"] == [{"value": 1}]
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
