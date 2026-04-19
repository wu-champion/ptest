from __future__ import annotations

import socket
import threading

from ptest.api import PTestAPI
from ptest.models import ManagedObjectRecord, OBJECT_STATUS_START_FAILED_PRESERVED


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _OneShotTCPService:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._serve_once, daemon=True)

    def start(self) -> None:
        self._thread.start()
        assert self._ready.wait(timeout=2), "one-shot service did not become ready"

    def _serve_once(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(1)
            self._ready.set()
            conn, _ = server.accept()
            conn.close()

    def trigger_exit(self) -> None:
        with socket.create_connection((self.host, self.port), timeout=1):
            pass
        self._thread.join(timeout=2)

    def is_stopped(self) -> bool:
        return not self._thread.is_alive()


def test_service_runtime_port_unreachable_exposes_runtime_recovery_plan(
    tmp_path,
) -> None:
    port = _find_free_port()
    api = PTestAPI(work_path=tmp_path / "workspace_service_runtime")
    api.init_environment()
    created = api.create_test_case(
        "service",
        "port_unreachable_service_check",
        content={
            "service_name": "demo_runtime_service",
            "check_type": "port",
            "host": "127.0.0.1",
            "port": port,
            "timeout": 1,
        },
    )
    case_id = created["data"]["case_id"]

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id, problem_type="service_runtime")
    assert problems["count"] == 1
    problem_id = problems["data"][0]["problem_id"]

    assets = api.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["failure_kind"] == "port_unreachable"
    assert assets["assets"]["details"]["runtime_hints"]["failure_kind"] == (
        "port_unreachable"
    )
    assert assets["assets"]["recovery"]["mode"] == "runtime_level_plan"
    assert assets["assets"]["recovery"]["failure_kind"] == "port_unreachable"
    assert assets["assets"]["recovery"]["runtime_target"]["service_name"] == (
        "demo_runtime_service"
    )
    assert assets["assets"]["investigation"]["runtime_target"]["port"] == port
    assert assets["assets"]["investigation"]["failure_kind"] == "port_unreachable"
    assert assets["assets"]["investigation"]["boundary"]["scope"] == (
        "runtime_level_plan"
    )

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["mode"] == "runtime_level_plan"
    assert recovery["recovery"]["failure_kind"] == "port_unreachable"
    assert recovery["recovery"]["runtime_target"]["port"] == port
    assert recovery["recovery"]["recommended_checks"][0]["purpose"] == (
        "inspect_runtime_status"
    )
    assert recovery["recovery"]["suggested_repairs"][0]["action"] == (
        "verify_endpoint_reachability_and_port_binding"
    )
    assert recovery["recovery"]["boundary"]["scope"] == "runtime_level_plan"

    detail = api.get_problem_record(problem_id)
    assert detail["success"] is True
    assert detail["problem"]["investigation"]["runtime_target"]["service_name"] == (
        "demo_runtime_service"
    )
    assert detail["problem"]["investigation"]["failure_kind"] == "port_unreachable"


def test_service_runtime_start_failed_exposes_runtime_boundary(
    tmp_path,
) -> None:
    port = _find_free_port()
    api = PTestAPI(work_path=tmp_path / "workspace_start_failed")
    api.init_environment()
    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="demo_runtime_service",
            type_name="service",
            status=OBJECT_STATUS_START_FAILED_PRESERVED,
            installed=True,
            config={"runtime_backend": "managed"},
            metadata={"failure_state": {"phase": "start"}},
        )
    )
    created = api.create_test_case(
        "service",
        "service_start_failed_check",
        content={
            "service_name": "demo_runtime_service",
            "check_type": "port",
            "host": "127.0.0.1",
            "port": port,
            "timeout": 1,
        },
    )
    case_id = created["data"]["case_id"]

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id, problem_type="service_runtime")
    assert problems["count"] == 1
    problem_id = problems["data"][0]["problem_id"]

    assets = api.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["failure_kind"] == "startup_failed"
    assert assets["assets"]["recovery"]["failure_kind"] == "startup_failed"
    assert assets["assets"]["recovery"]["runtime_hints"]["object_status"] == (
        OBJECT_STATUS_START_FAILED_PRESERVED
    )
    assert assets["assets"]["investigation"]["boundary"]["confidence"] == (
        "high_for_preserved_start_failure"
    )

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["failure_kind"] == "startup_failed"
    assert recovery["recovery"]["boundary"]["assessment"] == (
        "startup_failure_detected"
    )
    assert recovery["recovery"]["suggested_repairs"][0]["action"] == (
        "inspect_start_failure_and_fix_prerequisites"
    )


def test_service_runtime_abnormal_exit_exposes_runtime_boundary(
    tmp_path,
) -> None:
    port = _find_free_port()
    service = _OneShotTCPService("127.0.0.1", port)
    service.start()

    api = PTestAPI(work_path=tmp_path / "workspace_abnormal_exit")
    api.init_environment()
    created = api.create_test_case(
        "service",
        "service_abnormal_exit_check",
        content={
            "service_name": "demo_runtime_service",
            "check_type": "port",
            "host": "127.0.0.1",
            "port": port,
            "timeout": 1,
            "expected_runtime_state": "running",
        },
    )
    case_id = created["data"]["case_id"]

    service.trigger_exit()
    assert service.is_stopped() is True

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id, problem_type="service_runtime")
    assert problems["count"] == 1
    problem_id = problems["data"][0]["problem_id"]

    assets = api.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["failure_kind"] == "abnormal_exit"
    assert assets["assets"]["details"]["runtime_hints"]["failure_kind"] == (
        "abnormal_exit"
    )
    assert assets["assets"]["details"]["runtime_hints"]["expected_runtime_state"] == (
        "running"
    )
    assert assets["assets"]["investigation"]["failure_kind"] == "abnormal_exit"
    assert assets["assets"]["investigation"]["boundary"]["scope"] == (
        "runtime_level_plan"
    )
    assert assets["assets"]["investigation"]["boundary"]["assessment"] == (
        "runtime_diverged_from_expected_service_state"
    )

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["failure_kind"] == "abnormal_exit"
    assert recovery["recovery"]["boundary"]["confidence"] == (
        "high_for_expected_running_service"
    )
    assert recovery["recovery"]["suggested_repairs"][0]["action"] == (
        "inspect_exit_logs_before_restart"
    )
