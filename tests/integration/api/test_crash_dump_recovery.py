from __future__ import annotations

import socket
import threading
from pathlib import Path

from ptest.api import PTestAPI


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _OneShotCrashService:
    def __init__(self, host: str, port: int, dump_path: Path) -> None:
        self.host = host
        self.port = port
        self.dump_path = dump_path
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._serve_once, daemon=True)

    def start(self) -> None:
        self._thread.start()
        assert self._ready.wait(timeout=2), "crash service did not become ready"

    def _serve_once(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(1)
            self._ready.set()
            conn, _ = server.accept()
            conn.close()
        self.dump_path.write_text("fake core dump", encoding="utf-8")

    def trigger_crash(self) -> None:
        with socket.create_connection((self.host, self.port), timeout=1):
            pass
        self._thread.join(timeout=2)

    def is_stopped(self) -> bool:
        return not self._thread.is_alive()


def test_crash_dump_problem_preserves_dump_refs_and_recovery_plan(tmp_path) -> None:
    port = _find_free_port()
    dump_path = tmp_path / "demo_service.core"
    service = _OneShotCrashService("127.0.0.1", port, dump_path)
    service.start()
    logs_dir = tmp_path / "workspace_crash_dump" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "crash.log").write_text(
        "runtime started\nfatal signal received\n",
        encoding="utf-8",
    )

    api = PTestAPI(work_path=tmp_path / "workspace_crash_dump")
    api.init_environment()
    created = api.create_test_case(
        "service",
        "service_crash_dump_check",
        content={
            "service_name": "demo_crash_service",
            "check_type": "port",
            "host": "127.0.0.1",
            "port": port,
            "timeout": 1,
            "expected_runtime_state": "running",
            "dump_paths": [str(dump_path)],
        },
    )
    case_id = created["data"]["case_id"]

    service.trigger_crash()
    assert service.is_stopped() is True
    assert dump_path.exists() is True

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id, problem_type="crash_dump")
    assert problems["count"] == 1
    problem_id = problems["data"][0]["problem_id"]

    assets = api.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["crash_target"]["service_name"] == (
        "demo_crash_service"
    )
    assert assets["assets"]["details"]["dump_refs"][0]["path"] == str(dump_path)
    assert assets["assets"]["details"]["dump_refs"][0]["exists"] is True
    assert assets["assets"]["details"]["log_window"]["file_count"] >= 1
    assert any(
        snippet.get("path") == "logs/crash.log"
        for snippet in assets["assets"]["details"]["log_window"]["snippets"]
        if isinstance(snippet, dict)
    )
    assert assets["assets"]["recovery"]["mode"] == "crash_dump_investigation"
    assert assets["assets"]["investigation"]["boundary"]["scope"] == (
        "crash_asset_preservation"
    )
    assert assets["assets"]["investigation"]["boundary"]["assessment"] == (
        "dump_refs_preserved_for_followup_analysis"
    )
    assert assets["assets"]["investigation"]["log_window"]["file_count"] >= 1

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["mode"] == "crash_dump_investigation"
    assert recovery["recovery"]["dump_refs"][0]["exists"] is True
    assert recovery["recovery"]["recommended_checks"][0]["purpose"] == (
        "inspect_dump_refs"
    )
    assert recovery["recovery"]["next_actions"][0]["action"] == "inspect_dump_refs"
