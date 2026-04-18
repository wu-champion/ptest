from __future__ import annotations

import socket
import tarfile
import textwrap
import time
from pathlib import Path

import ptest.cases.executor as case_executor_module
from ptest.api import PTestAPI
from ptest.objects.db_server import DatabaseServerComponent


def _create_fake_mysql_archive(package_path: Path) -> Path:
    package_path.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = package_path.parent / "fake_mysql_pkg"
    bin_dir = stage_dir / "mysql-8.4" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_mysqld = bin_dir / "mysqld"
    fake_mysqld.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os
            import signal
            import subprocess
            import sys
            import time
            from pathlib import Path

            def _arg_value(prefix: str, default: str = "") -> str:
                for arg in sys.argv[1:]:
                    if arg.startswith(prefix):
                        return arg.split("=", 1)[1]
                return default

            if len(sys.argv) > 1 and sys.argv[1] == "--serve":
                pid_file = sys.argv[2]
                log_file = sys.argv[3]
                running = True

                def handle_term(signum, frame):
                    nonlocal_running[0] = False

                nonlocal_running = [True]
                signal.signal(signal.SIGTERM, handle_term)
                signal.signal(signal.SIGINT, handle_term)

                Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
                Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")
                Path(log_file).parent.mkdir(parents=True, exist_ok=True)
                Path(log_file).write_text("running\\n", encoding="utf-8")

                while nonlocal_running[0]:
                    time.sleep(0.2)

                Path(log_file).write_text("stopped\\n", encoding="utf-8")
                raise SystemExit(0)

            datadir = _arg_value("--datadir")
            log_file = _arg_value("--log-error")
            pid_file = _arg_value("--pid-file")

            if "--initialize-insecure" in sys.argv:
                Path(datadir, "mysql").mkdir(parents=True, exist_ok=True)
                if log_file:
                    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
                    Path(log_file).write_text("initialized\\n", encoding="utf-8")
                raise SystemExit(0)

            if "--daemonize" in sys.argv:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        __file__,
                        "--serve",
                        pid_file,
                        log_file,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    start_new_session=True,
                )
                time.sleep(0.5)
                if pid_file and not Path(pid_file).exists():
                    Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
                    Path(pid_file).write_text(str(process.pid), encoding="utf-8")
                raise SystemExit(0)

            raise SystemExit(1)
            """
        ),
        encoding="utf-8",
    )
    fake_mysqld.chmod(0o755)
    with tarfile.open(package_path, "w:xz") as archive:
        archive.add(stage_dir / "mysql-8.4", arcname="mysql-8.4")
    return package_path


class _FakeMySQLCursor:
    def __init__(self, query_results: dict[str, list[dict[str, object]]]) -> None:
        self.query_results = query_results
        self.description: list[tuple[str]] = []
        self.rowcount = 0
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> "_FakeMySQLCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str) -> None:
        normalized = query.strip()
        rows = self.query_results.get(normalized, [])
        if rows:
            columns = list(rows[0].keys())
            self.description = [(column,) for column in columns]
            self._rows = [tuple(row[column] for column in columns) for row in rows]
            self.rowcount = len(rows)
        else:
            self.description = []
            self._rows = []
            self.rowcount = 0

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)


class _FakeMySQLConnection:
    def __init__(
        self,
        query_results: dict[str, list[dict[str, object]]],
        capture: dict[str, object],
        kwargs: dict[str, object],
    ) -> None:
        self.query_results = query_results
        capture["connect_kwargs"] = kwargs

    def cursor(self) -> _FakeMySQLCursor:
        return _FakeMySQLCursor(self.query_results)

    def close(self) -> None:
        return None

    def commit(self) -> None:
        return None


class _FakePyMySQLModule:
    def __init__(
        self,
        query_results: dict[str, list[dict[str, object]]],
        capture: dict[str, object],
    ) -> None:
        self.query_results = query_results
        self.capture = capture

    def connect(self, **kwargs: object) -> _FakeMySQLConnection:
        return _FakeMySQLConnection(self.query_results, self.capture, kwargs)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _prepare_mysql_object(api: PTestAPI, work_path: Path) -> int:
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(work_path / "assets" / "mysql-8.4.tar.xz")
    create_result = api.create_object(
        "mysql",
        "mysql_service",
        mysql_package_path=str(package_path),
        workspace_path=str(work_path),
        port=mysql_port,
        mysql_config={"health_check_mode": "tcp"},
    )
    assert create_result["success"] is True

    start_result = api.start_object("mysql_service")
    assert start_result["success"] is True
    return mysql_port


def test_mysql_data_state_value_mismatch_exposes_recovery_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        DatabaseServerComponent,
        "_check_runtime_backend_capabilities",
        lambda self: (True, "sandbox runtime preflight bypassed for test"),
    )
    monkeypatch.setattr(
        DatabaseServerComponent,
        "_mysql_health_check",
        lambda self, pid: (True, f"MySQL server healthy (PID: {pid}, sandbox mode)"),
    )

    api = PTestAPI(work_path=tmp_path / "workspace_mysql_value_mismatch")
    api.init_environment()
    mysql_port = _prepare_mysql_object(api, tmp_path)

    query = "SELECT id, state FROM orders WHERE id = 'ORD-100'"
    capture: dict[str, object] = {}
    monkeypatch.setattr(case_executor_module, "PYMYSQL_AVAILABLE", True)
    monkeypatch.setattr(
        case_executor_module,
        "pymysql",
        _FakePyMySQLModule(
            {
                query: [{"id": "ORD-100", "state": "pending"}],
            },
            capture,
        ),
    )

    created = api.create_test_case(
        "database",
        "mysql_state_mismatch",
        content={
            "object_name": "mysql_service",
            "query": query,
            "expected_result": [{"id": "ORD-100", "state": "ready"}],
        },
    )
    case_id = created["data"]["case_id"]

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False
    assert capture["connect_kwargs"] == {
        "host": "127.0.0.1",
        "port": mysql_port,
        "user": "root",
        "password": "",
        "database": None,
        "charset": "utf8mb4",
    }

    problems = api.list_problem_records(case_id=case_id, problem_type="data_state")
    assert problems["count"] == 1
    problem_id = problems["data"][0]["problem_id"]

    assets = api.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["failure_kind"] == "value_mismatch"
    assert assets["assets"]["details"]["actual_result"] == [
        {"id": "ORD-100", "state": "pending"}
    ]
    assert assets["assets"]["investigation"]["data_source"]["db_type"] == "mysql"
    assert assets["assets"]["investigation"]["state_hints"]["mismatched_fields"] == [
        "state"
    ]
    assert assets["assets"]["investigation"]["origin_hints"]["classification"] == (
        "stale_field_values"
    )
    assert (
        assets["assets"]["investigation"]["origin_hints"]["query_context"]
        == "single_or_filtered_query"
    )
    assert assets["assets"]["investigation"]["boundary"]["scope"] == (
        "query_level_plan"
    )

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["failure_kind"] == "value_mismatch"
    assert recovery["recovery"]["data_source"]["db_type"] == "mysql"
    assert recovery["recovery"]["origin_hints"]["classification"] == (
        "stale_field_values"
    )
    assert recovery["recovery"]["boundary"]["scope"] == "query_level_plan"
    assert (
        recovery["recovery"]["boundary"]["confidence"]
        == "high_for_direct_result_mismatch"
    )
    assert recovery["recovery"]["suggested_repairs"][0]["action"] == (
        "align_key_field_values"
    )


def test_mysql_data_state_missing_rows_exposes_repair_hints(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        DatabaseServerComponent,
        "_check_runtime_backend_capabilities",
        lambda self: (True, "sandbox runtime preflight bypassed for test"),
    )
    monkeypatch.setattr(
        DatabaseServerComponent,
        "_mysql_health_check",
        lambda self, pid: (True, f"MySQL server healthy (PID: {pid}, sandbox mode)"),
    )

    api = PTestAPI(work_path=tmp_path / "workspace_mysql_missing_rows")
    api.init_environment()
    mysql_port = _prepare_mysql_object(api, tmp_path)

    query = "SELECT id, state FROM orders WHERE id = 'ORD-404'"
    monkeypatch.setattr(case_executor_module, "PYMYSQL_AVAILABLE", True)
    monkeypatch.setattr(
        case_executor_module,
        "pymysql",
        _FakePyMySQLModule(
            {
                query: [],
            },
            {},
        ),
    )

    created = api.create_test_case(
        "database",
        "mysql_missing_order",
        content={
            "object_name": "mysql_service",
            "query": query,
            "expected_result": [{"id": "ORD-404", "state": "ready"}],
        },
    )
    case_id = created["data"]["case_id"]

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id, problem_type="data_state")
    assert problems["count"] == 1
    problem_id = problems["data"][0]["problem_id"]

    assets = api.get_problem_assets(problem_id)
    assert assets["success"] is True
    assert assets["assets"]["details"]["failure_kind"] == "missing_rows"
    assert assets["assets"]["investigation"]["data_source"]["db_type"] == "mysql"
    assert assets["assets"]["investigation"]["origin_hints"]["classification"] == (
        "missing_seed_data"
    )
    assert assets["assets"]["investigation"]["boundary"]["scope"] == (
        "query_level_plan"
    )

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["failure_kind"] == "missing_rows"
    assert recovery["recovery"]["data_source"]["port"] == mysql_port
    assert recovery["recovery"]["origin_hints"]["classification"] == (
        "missing_seed_data"
    )
    assert recovery["recovery"]["boundary"]["scope"] == "query_level_plan"
    assert recovery["recovery"]["boundary"]["needs_historical_state"] is False
    assert recovery["recovery"]["suggested_repairs"][0]["action"] == (
        "insert_minimal_required_rows"
    )
