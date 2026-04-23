from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

from ptest.api import PTestAPI


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVICE_SCRIPT = (
    PROJECT_ROOT
    / "examples"
    / "06_stateful_api_replay"
    / "service"
    / "stateful_api_server.py"
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_service(port: int, *, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/state/check"
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=0.5)
            if response.status_code == 200:
                return
        except requests.RequestException:
            time.sleep(0.1)
    raise RuntimeError(f"stateful api service did not start on port {port}")


def _start_service(port: int) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            str(SERVICE_SCRIPT),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _wait_for_service(port)
    return process


def test_stateful_api_direct_problem_replay_remains_reproducible(
    tmp_path: Path,
) -> None:
    port = _find_free_port()
    process = _start_service(port)
    try:
        api = PTestAPI(work_path=tmp_path / "direct")
        api.init_environment()
        created = api.create_test_case(
            "api",
            "direct_body_mismatch",
            content={
                "request": {
                    "method": "GET",
                    "url": f"http://127.0.0.1:{port}/api/orders",
                },
                "expected_status": 200,
                "expected_response": {"status": "stale"},
            },
        )
        case_id = created["data"]["case_id"]

        run_result = api.run_test_case(case_id)
        assert run_result["success"] is False

        problems = api.list_problem_records(case_id=case_id)
        assert problems["count"] == 1
        problem_id = problems["data"][0]["problem_id"]

        assets = api.get_problem_assets(problem_id)
        assert assets["success"] is True
        assert assets["assets"]["reproduction_summary"]["request"]["url"] == (
            f"http://127.0.0.1:{port}/api/orders"
        )
        assert assets["assets"]["investigation"]["view"] == "assets"
        assert assets["assets"]["investigation"]["request"]["url"] == (
            f"http://127.0.0.1:{port}/api/orders"
        )
        assert assets["assets"]["reproduction_summary"]["dependency_hints"] == {
            "recent_predecessors": [],
            "candidate_case_ids": [],
            "recent_same_case": None,
            "immediate_predecessor": None,
            "signal_strength": "none",
            "recommended_actions": [],
        }

        replay = api.replay_problem(problem_id)
        assert replay["success"] is True
        assert replay["replay"]["reproduced"] is True
        assert replay["replay"]["comparison"]["boundary"]["scope"] == "request_level"
        assert (
            replay["replay"]["comparison"]["boundary"]["confidence"]
            == "request_reproduced"
        )
        assert (
            replay["replay"]["comparison"]["summary"]["boundary"]["assessment"]
            == "reproduced_under_current_workspace_state"
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
        assert replay["replay"]["investigation"]["view"] == "replay"
        assert replay["replay"]["investigation"]["replay"]["assessment"] == (
            "reproduced_under_current_workspace_state"
        )
        assert (
            replay["replay"]["comparison"]["summary"]["body"]["change_kind"] == "same"
        )
        assert replay["replay"]["comparison"]["summary"]["body"]["replay_preview"] == {
            "failure_armed": False,
            "orders": "[... x1]",
            "status": "ok",
        }
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_stateful_api_hidden_dependency_replay_exposes_request_level_boundary(
    tmp_path: Path,
) -> None:
    port = _find_free_port()
    process = _start_service(port)
    try:
        api = PTestAPI(work_path=tmp_path / "hidden")
        api.init_environment()

        enable_case = api.create_test_case(
            "api",
            "enable_hidden_failure",
            content={
                "request": {
                    "method": "POST",
                    "url": f"http://127.0.0.1:{port}/state/enable-failure",
                },
                "expected_status": 200,
                "expected_response": {
                    "status": "armed",
                    "failure_armed": True,
                },
            },
        )
        enable_case_id = enable_case["data"]["case_id"]
        affected_case = api.create_test_case(
            "api",
            "orders_after_hidden_state",
            content={
                "request": {
                    "method": "GET",
                    "url": f"http://127.0.0.1:{port}/api/orders",
                },
                "expected_status": 200,
                "expected_response": {
                    "status": "ok",
                    "orders": [{"id": "A100", "state": "ready"}],
                },
            },
        )
        affected_case_id = affected_case["data"]["case_id"]

        assert api.run_test_case(enable_case_id)["success"] is True
        affected_run = api.run_test_case(affected_case_id)
        assert affected_run["success"] is False

        problems = api.list_problem_records(case_id=affected_case_id)
        assert problems["count"] == 1
        problem_id = problems["data"][0]["problem_id"]

        assets = api.get_problem_assets(problem_id)
        assert assets["success"] is True
        assert assets["assets"]["reproduction_summary"]["request"]["url"] == (
            f"http://127.0.0.1:{port}/api/orders"
        )
        assert assets["assets"]["investigation"]["view"] == "assets"
        assert assets["assets"]["reproduction_summary"]["dependency_hints"][
            "candidate_case_ids"
        ] == [enable_case_id]
        assert (
            assets["assets"]["reproduction_summary"]["dependency_hints"][
                "signal_strength"
            ]
            == "recent_sequence"
        )
        assert (
            assets["assets"]["reproduction_summary"]["dependency_hints"][
                "immediate_predecessor"
            ]["case_id"]
            == enable_case_id
        )
        assert (
            assets["assets"]["reproduction_summary"]["dependency_hints"][
                "recommended_actions"
            ][0]["action"]
            == "inspect_immediate_predecessor"
        )
        assert (
            assets["assets"]["reproduction_summary"]["dependency_hints"][
                "recommended_actions"
            ][1]["action"]
            == "rerun_candidate_predecessors_before_replay"
        )
        assert (
            assets["assets"]["reproduction_summary"]["side_effect_hints"][
                "classification"
            ]
            == "possible_request_side_effect"
        )
        assert (
            assets["assets"]["reproduction_summary"]["side_effect_hints"][
                "likely_trigger_case_id"
            ]
            == enable_case_id
        )
        assert assets["assets"]["investigation"]["side_effect"]["classification"] == (
            "possible_request_side_effect"
        )
        assert (
            assets["assets"]["investigation"]["environment_recovery"]["assessment"]
            == "environment_may_have_shifted_by_prior_case"
        )

        recovery = api.recover_problem(problem_id)
        assert recovery["success"] is True
        assert recovery["recovery"]["side_effect_hints"]["classification"] == (
            "possible_request_side_effect"
        )
        assert recovery["recovery"]["side_effect_hints"]["likely_trigger_case_id"] == (
            enable_case_id
        )
        assert recovery["recovery"]["environment_recovery"]["scope"] == (
            "workspace_side_effect_minimum_recovery"
        )
        assert recovery["recovery"]["environment_recovery"]["recommended_sequence"][
            0
        ] == "inspect_likely_trigger_case_effects"

        replay = api.replay_problem(problem_id)
        assert replay["success"] is True
        assert replay["replay"]["reproduced"] is False
        assert replay["replay"]["comparison"]["boundary"]["scope"] == "request_level"
        assert (
            replay["replay"]["comparison"]["boundary"]["confidence"] == "request_only"
        )
        assert (
            replay["replay"]["comparison"]["boundary"]["assessment"]
            == "diverged_from_preserved_failure"
        )
        assert (
            replay["replay"]["comparison"]["boundary"]["hidden_dependency_possible"]
            is True
        )
        assert (
            replay["replay"]["comparison"]["boundary"]["dependency_hints"][
                "signal_strength"
            ]
            == "recent_sequence"
        )
        assert replay["replay"]["comparison"]["boundary"]["dependency_hints"][
            "candidate_case_ids"
        ] == [enable_case_id]
        assert (
            replay["replay"]["comparison"]["boundary"]["dependency_hints"][
                "immediate_predecessor"
            ]["case_id"]
            == enable_case_id
        )
        assert (
            replay["replay"]["comparison"]["summary"]["body"]["change_kind"]
            == "top_level_fields_changed"
        )
        assert replay["replay"]["comparison"]["summary"]["boundary"]["scope"] == (
            "request_level"
        )
        assert replay["replay"]["comparison"]["summary"]["boundary"][
            "dependency_hints"
        ]["candidate_case_ids"] == [enable_case_id]
        assert replay["replay"]["investigation"]["view"] == "replay"
        assert replay["replay"]["investigation"]["dependency"][
            "candidate_case_ids"
        ] == [enable_case_id]
        assert (
            replay["replay"]["comparison"]["boundary"]["recommended_actions"][0][
                "action"
            ]
            == "inspect_immediate_predecessor"
        )
        assert (
            replay["replay"]["comparison"]["boundary"]["recommended_actions"][1][
                "action"
            ]
            == "rerun_candidate_predecessors_before_replay"
        )
        assert replay["replay"]["comparison"]["summary"]["body"][
            "changed_top_level_fields"
        ] == ["orders", "status"]
        assert replay["replay"]["comparison"]["summary"]["body"][
            "removed_top_level_fields"
        ] == ["reason"]
        assert replay["replay"]["comparison"]["summary"]["body"][
            "preserved_preview"
        ] == {
            "failure_armed": False,
            "orders": "[... x0]",
            "reason": "hidden dependency triggered",
        }
        assert replay["replay"]["comparison"]["summary"]["body"]["replay_preview"] == {
            "failure_armed": False,
            "orders": "[... x1]",
            "status": "ok",
        }
        assert (
            "replay no longer reproduces the original problem"
            in replay["replay"]["comparison"]["highlights"]
        )
        assert any(
            "current replay only reruns the preserved request and may miss prior state changes or hidden dependencies"
            in item
            for item in replay["replay"]["comparison"]["highlights"]
        )
        assert any(
            f"recent preceding cases: {enable_case_id}" in item
            for item in replay["replay"]["comparison"]["highlights"]
        )
        assert (
            "next suggested step: inspect_immediate_predecessor"
            in replay["replay"]["comparison"]["highlights"]
        )
    finally:
        process.terminate()
        process.wait(timeout=5)
