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

    problem_id = problems["data"][0]["problem_id"]
    detail = api.get_problem_record(problem_id)
    assert detail["success"] is True
    assert detail["data"]["problem_type"] == "api_response"


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
    assert recovery["data"]["mode"] == "minimal_state_hints"
    assert recovery["data"]["actual_result"] == [{"value": 1}]
    assert recovery["recovery_action"]["action_type"] == "recover"

    latest_recovery = api.get_problem_recovery(problems["data"][0]["problem_id"])
    assert latest_recovery["success"] is True
    assert latest_recovery["data"]["status"] == "prepared"
