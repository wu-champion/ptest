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

        replay = api.replay_problem(problem_id)
        assert replay["success"] is True
        assert replay["replay"]["reproduced"] is True
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

        assert api.run_test_case(enable_case["data"]["case_id"])["success"] is True
        affected_run = api.run_test_case(affected_case["data"]["case_id"])
        assert affected_run["success"] is False

        problems = api.list_problem_records(case_id=affected_case["data"]["case_id"])
        assert problems["count"] == 1
        problem_id = problems["data"][0]["problem_id"]

        assets = api.get_problem_assets(problem_id)
        assert assets["success"] is True
        assert assets["assets"]["reproduction_summary"]["request"]["url"] == (
            f"http://127.0.0.1:{port}/api/orders"
        )

        replay = api.replay_problem(problem_id)
        assert replay["success"] is True
        assert replay["replay"]["reproduced"] is False
        assert (
            replay["replay"]["comparison"]["summary"]["body"]["change_kind"]
            == "top_level_fields_changed"
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
    finally:
        process.terminate()
        process.wait(timeout=5)
