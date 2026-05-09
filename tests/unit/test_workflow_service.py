from __future__ import annotations

import json
import socket
import tarfile
import textwrap
from pathlib import Path

import ptest.cases.executor as case_executor_module
from ptest.app import WorkflowService
from ptest.contract.manager import APIContract, APIEndpoint, ContractManager
from ptest.models import (
    OBJECT_STATUS_ERROR,
    OBJECT_STATUS_INSTALL_FAILED_PRESERVED,
    OBJECT_STATUS_START_FAILED_PRESERVED,
    OBJECT_STATUS_INSTALLED,
)
from ptest.mock import MockConfig, MockServer
from ptest.objects.db_enhanced import DatabaseServerObject
from ptest.objects.db_server import DatabaseServerComponent


def _normalized_path(path: str) -> str:
    return path.replace("\\", "/")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _create_fake_mysql_archive(package_path: Path) -> Path:
    package_path.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = package_path.parent / "fake_mysql_pkg"
    bin_dir = stage_dir / "mysql-8.4" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_mysqld_script = bin_dir / "mysqld.py"
    fake_mysqld_script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os
            import signal
            import socket
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
                host = sys.argv[2]
                port = int(sys.argv[3])
                pid_file = sys.argv[4]
                log_file = sys.argv[5]
                running = True

                def handle_term(signum, frame):
                    global running
                    running = False

                signal.signal(signal.SIGTERM, handle_term)
                signal.signal(signal.SIGINT, handle_term)

                Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
                Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")
                Path(log_file).parent.mkdir(parents=True, exist_ok=True)
                Path(log_file).write_text("running\\n", encoding="utf-8")

                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((host, port))
                server.listen(5)
                server.settimeout(0.5)

                while running:
                    try:
                        conn, _ = server.accept()
                    except socket.timeout:
                        continue
                    conn.close()

                server.close()
                Path(log_file).write_text("stopped\\n", encoding="utf-8")
                raise SystemExit(0)

            datadir = _arg_value("--datadir")
            log_file = _arg_value("--log-error")
            pid_file = _arg_value("--pid-file")
            host = _arg_value("--bind-address", "127.0.0.1")
            port = int(_arg_value("--port", "13306"))

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
                        host,
                        str(port),
                        pid_file,
                        log_file,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    start_new_session=True,
                )
                time.sleep(1)
                if pid_file and not Path(pid_file).exists():
                    Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
                    Path(pid_file).write_text(str(process.pid), encoding="utf-8")
                raise SystemExit(0)

            raise SystemExit(1)
            """
        ),
        encoding="utf-8",
    )
    fake_mysqld_script.chmod(0o755)
    fake_mysqld = bin_dir / "mysqld"
    fake_mysqld.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            exec "$(command -v python3)" "$(dirname "$0")/mysqld.py" "$@"
            """
        ),
        encoding="utf-8",
    )
    fake_mysqld.chmod(0o755)
    fake_mysqld_cmd = bin_dir / "mysqld.cmd"
    fake_mysqld_cmd.write_text(
        '@echo off\r\npython "%~dp0mysqld.py" %*\r\n',
        encoding="utf-8",
    )
    with tarfile.open(package_path, "w:xz") as archive:
        archive.add(stage_dir / "mysql-8.4", arcname="mysql-8.4")
    return package_path


def _create_fake_mysql_deb_bundle(package_path: Path) -> Path:
    package_path.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = package_path.parent / "fake_mysql_deb_bundle"
    stage_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "mysql-community-server-core_8.4.8-1ubuntu24.04_amd64.deb",
        "mysql-community-client-core_8.4.8-1ubuntu24.04_amd64.deb",
        "mysql-common_8.4.8-1ubuntu24.04_amd64.deb",
    ):
        (stage_dir / name).write_bytes(b"fake-deb")
    with tarfile.open(package_path, "w") as archive:
        for child in sorted(stage_dir.iterdir()):
            archive.add(child, arcname=child.name)
    return package_path


class _FakeMySQLCursor:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state
        self.description = [("value",)]
        self.rowcount = 1
        self._rows: list[tuple[object, ...]] = [(1,)]

    def __enter__(self) -> "_FakeMySQLCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str) -> None:
        self.query = query
        normalized = " ".join(query.strip().upper().split())
        if normalized.startswith("CREATE DATABASE"):
            databases = self.state.setdefault("databases", set())
            if isinstance(databases, set):
                database_name = query.strip().rstrip(";").split()[-1].strip("`")
                databases.add(database_name)
            self.rowcount = 1
            self.description = []
            self._rows = []
            return
        if normalized.startswith("USE "):
            self.state["active_database"] = (
                query.strip().rstrip(";").split()[-1].strip("`")
            )
            self.rowcount = 0
            self.description = []
            self._rows = []
            return
        if normalized.startswith("CREATE TABLE"):
            if not self.state.get("active_database"):
                raise RuntimeError("No database selected")
            self.rowcount = 0
            self.description = []
            self._rows = []
            return
        if normalized.startswith("INSERT INTO"):
            if not self.state.get("active_database"):
                raise RuntimeError("No database selected")
            self.state["rows"] = [{"id": 1, "name": "alpha"}]
            self.rowcount = 1
            self.description = []
            self._rows = []
            return
        if normalized.startswith("UPDATE"):
            if not self.state.get("active_database"):
                raise RuntimeError("No database selected")
            rows = self.state.setdefault("rows", [])
            if isinstance(rows, list) and rows:
                first_row = rows[0]
                if isinstance(first_row, dict):
                    first_row["name"] = "beta"
            self.rowcount = 1
            self.description = []
            self._rows = []
            return
        if normalized.startswith("DELETE"):
            if not self.state.get("active_database"):
                raise RuntimeError("No database selected")
            rows = self.state.get("rows", [])
            self.rowcount = len(rows) if isinstance(rows, list) else 0
            self.state["rows"] = []
            self.description = []
            self._rows = []
            return
        if normalized.startswith("SELECT 1 AS VALUE"):
            self.description = [("value",)]
            self.rowcount = 1
            self._rows = [(1,)]
            return
        if normalized.startswith("SELECT COUNT(*) AS COUNT"):
            rows = self.state.get("rows", [])
            count = len(rows) if isinstance(rows, list) else 0
            self.description = [("count",)]
            self.rowcount = 1
            self._rows = [(count,)]
            return
        if normalized.startswith("SELECT ID, NAME FROM CRUD_ITEMS"):
            rows = self.state.get("rows", [])
            self.description = [("id",), ("name",)]
            self.rowcount = len(rows) if isinstance(rows, list) else 0
            if isinstance(rows, list):
                self._rows = [
                    (item.get("id"), item.get("name"))
                    for item in rows
                    if isinstance(item, dict)
                ]
            else:
                self._rows = []
            return

        self.description = []
        self.rowcount = 0
        self._rows = []

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows

    def close(self) -> None:
        return None


class _FakeMySQLConnection:
    def __init__(
        self,
        capture: dict[str, object],
        kwargs: dict[str, object],
        state: dict[str, object],
    ) -> None:
        capture["connect_kwargs"] = kwargs
        self.state = state

    def cursor(self) -> _FakeMySQLCursor:
        return _FakeMySQLCursor(self.state)

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakePyMySQLModule:
    def __init__(self, capture: dict[str, object]) -> None:
        self.capture = capture
        self.state: dict[str, object] = {"rows": []}

    def connect(self, **kwargs: object) -> _FakeMySQLConnection:
        return _FakeMySQLConnection(self.capture, kwargs, self.state)


def test_workflow_service_persists_environment_and_objects(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    record = service.init_environment()

    assert record.root_path == str(tmp_path.resolve())
    assert (tmp_path / ".ptest" / "environment.json").exists()
    assert (tmp_path / "dumps").exists()
    assert record.metadata["isolation"]["env_id"].startswith("env_")
    assert record.metadata["isolation"]["isolation_level"] == "basic"
    assert record.metadata["isolation"]["recovery_strategy"] == "created_new"
    assert record.metadata["isolation"]["validated"] is True
    assert record.metadata["isolation"]["health"] is True
    assert record.metadata["dumps_dir"] == str((tmp_path / "dumps").resolve())
    runtime_backend = record.metadata["runtime_backend"]
    assert runtime_backend["name"] == "host"
    assert runtime_backend["capabilities"]["process_spawn"] is True
    assert runtime_backend["capabilities"]["tcp_bind"] is True
    assert runtime_backend["capabilities"]["filesystem_write"] is True
    assert runtime_backend["capabilities"]["environment_variables"] is True
    assert "core_limit_probe" in runtime_backend["capabilities"]
    assert record.metadata["crash_capture"]["dump_dir"] == str(
        (tmp_path / "dumps").resolve()
    )
    assert record.metadata["crash_capture"]["enable_attempt"]["status"] == "pending"

    install_result = service.install_object("service", "demo_service")
    assert install_result["success"] is True
    assert install_result["object"]["metadata"]["crash_capture"]["dump_dir"] == str(
        (tmp_path / "dumps").resolve()
    )

    start_result = service.start_object("demo_service")
    assert start_result["success"] is True

    reloaded = WorkflowService(tmp_path)
    status = reloaded.get_object_status("demo_service")
    assert status["success"] is True
    assert status["object"]["status"] == "installed"
    assert (
        status["object"]["metadata"]["recovery"]["mode"]
        == "downgraded_nonrecoverable_runtime"
    )

    tool_install = service.install_tool("demo_tool", {"version": "1.0"})
    assert tool_install["success"] is True

    tool_start = service.start_tool("demo_tool")
    assert tool_start["success"] is True

    reloaded_tool = WorkflowService(tmp_path)
    tool_status = reloaded_tool.get_tool_status("demo_tool")
    assert tool_status["success"] is True
    assert tool_status["tool"]["status"] == "running"


def test_workflow_service_reuses_persisted_isolation_level(tmp_path: Path) -> None:
    service = WorkflowService(
        tmp_path,
        config={"default_isolation_level": "basic"},
    )
    initial = service.init_environment()

    reloaded = WorkflowService(
        tmp_path,
        config={"default_isolation_level": "unsupported"},
    )
    recovered = reloaded.init_environment()

    assert (
        initial.metadata["isolation"]["env_id"]
        == recovered.metadata["isolation"]["env_id"]
    )
    assert recovered.metadata["isolation"]["isolation_level"] == "basic"
    assert recovered.metadata["isolation"]["attached"] is True
    assert recovered.metadata["isolation"]["recovery_strategy"] in {
        "attached_active",
        "reattached_recreated",
    }
    assert recovered.metadata["isolation"]["validated"] is True


def test_workflow_service_recovers_database_runtime_state(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    install_result = service.install_object(
        "database",
        "demo_db",
        {
            "db_type": "sqlite",
            "driver": "sqlite",
            "database": str(tmp_path / "runtime.db"),
        },
    )
    assert install_result["success"] is True

    start_result = service.start_object("demo_db")
    assert start_result["success"] is True

    reloaded = WorkflowService(tmp_path)
    status = reloaded.get_object_status("demo_db")
    assert status["success"] is True
    assert status["object"]["status"] == "running"
    assert status["object"]["metadata"]["recovery"]["mode"] == "rebuild_connector"
    assert status["object"]["metadata"]["recovery"]["recovered"] is True


def test_workflow_service_installs_mysql_as_database_server(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": 3307,
        },
    )
    assert install_result["success"] is True
    assert install_result["object"]["type_name"] == "database_server"

    status = service.get_object_status("mysql_service")
    assert status["success"] is True
    assert status["object"]["type_name"] == "database_server"


def test_workflow_service_builds_mysql_scenario_defaults(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
        },
    )

    assert install_result["success"] is True
    config = install_result["object"]["config"]
    assert install_result["object"]["type_name"] == "database_server"
    assert config["db_type"] == "mysql"
    assert config["workspace_path"] == str(tmp_path.resolve())
    assert config["server_host"] == "127.0.0.1"
    assert config["server_port"] == WorkflowService.DEFAULT_MANAGED_MYSQL_PORT
    assert config["runtime_backend"] == "host"
    assert config["runtime_backend_requirements"] == [
        "process_spawn",
        "tcp_bind",
        "filesystem_write",
        "environment_variables",
    ]
    assert config["mysql_package_path"] == str(package_path.resolve())
    assert config["source_asset"]["product"] == "mysql"
    assert config["source_asset"]["version"] == "8.4"
    assert config["source_asset"]["source_type"] == "archive"
    assert config["scenario"]["scenario_name"] == "mysql_full_lifecycle"
    assert config["scenario"]["workspace_path"] == str(tmp_path.resolve())
    assert config["scenario"]["instance_name"] == "mysql_service"
    assert config["scenario"]["port"] == WorkflowService.DEFAULT_MANAGED_MYSQL_PORT
    assert config["scenario"]["runtime_backend"] == "host"
    assert config["scenario"]["boundary_checks"]["check_workspace_boundary"] is True
    managed_instance = config["managed_instance"]
    assert managed_instance["instance_root"].startswith(str(tmp_path.resolve()))
    assert _normalized_path(managed_instance["data_dir"]).endswith("mysql_service/data")
    assert _normalized_path(managed_instance["dump_dir"]).endswith(
        "mysql_service/dumps"
    )
    assert _normalized_path(managed_instance["lib_dir"]).endswith("mysql_service/lib")
    assert _normalized_path(managed_instance["files_dir"]).endswith(
        "mysql_service/mysql-files"
    )
    assert install_result["object"]["metadata"]["crash_capture"]["dump_dir"] == str(
        Path(managed_instance["dump_dir"]).resolve()
    )
    object_backend = install_result["object"]["metadata"]["runtime_backend"]
    assert object_backend["name"] == "host"
    assert object_backend["capability_status"] == "satisfied"
    assert object_backend["missing_capabilities"] == []
    assert object_backend["required_capabilities"] == [
        "process_spawn",
        "tcp_bind",
        "filesystem_write",
        "environment_variables",
    ]
    assert _normalized_path(config["config_file"]).endswith(
        "mysql_service/config/my.cnf"
    )
    assert _normalized_path(config["log_file"]).endswith("mysql_service/logs/mysql.log")
    assert _normalized_path(config["pid_file"]).endswith("mysql_service/run/mysql.pid")
    assert _normalized_path(config["socket_file"]).endswith(
        "mysql_service/run/mysql.sock"
    )
    assert Path(config["config_file"]).exists()
    assert (
        Path(config["config_file"]).read_text(encoding="utf-8").startswith("[mysqld]")
    )
    assert Path(config["staged_package_path"]).exists()
    assert Path(config["staged_package_path"]).parent == Path(
        managed_instance["install_dir"]
    )

    status = service.get_object_status("mysql_service")
    assert status["success"] is True
    runtime_details = status["object"]["metadata"]["runtime"]["details"]
    assert runtime_details["config_file"] == config["config_file"]
    assert runtime_details["install_root"].startswith(managed_instance["install_dir"])
    config_text = Path(config["config_file"]).read_text(encoding="utf-8")
    assert "health_check_mode" not in config_text
    assert "mysqlx=0" in config_text
    assert f"socket={config['socket_file']}" in config_text


def test_workflow_service_installs_mysql_from_deb_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_extract_deb_package(
        self: DatabaseServerObject, package_path: Path, rootfs_dir: Path
    ) -> None:
        if "server-core" in package_path.name:
            binary = rootfs_dir / "usr" / "sbin" / "mysqld"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)
        elif "client-core" in package_path.name:
            client = rootfs_dir / "usr" / "bin" / "mysql"
            client.parent.mkdir(parents=True, exist_ok=True)
            client.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            client.chmod(0o755)
        else:
            common = rootfs_dir / "etc" / "mysql" / "mysql.cnf"
            common.parent.mkdir(parents=True, exist_ok=True)
            common.write_text("[mysql]\n", encoding="utf-8")

    monkeypatch.setattr(
        DatabaseServerObject,
        "_extract_deb_package",
        fake_extract_deb_package,
    )
    monkeypatch.setattr(
        DatabaseServerObject,
        "_read_deb_dependency_requirements",
        lambda self, package_path: {
            "package": package_path.name,
            "raw": "libaio1t64, libnuma1",
            "external_packages": ["libaio1t64", "libnuma1"],
        },
    )

    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_deb_bundle(
        tmp_path / "assets" / "mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar"
    )

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
        },
    )

    assert install_result["success"] is True
    config = install_result["object"]["config"]
    assert config["staged_package_path"].endswith(".deb-bundle.tar")
    assert _normalized_path(config["mysql_binary"]).endswith("usr/sbin/mysqld")
    assert Path(config["mysql_binary"]).exists()
    assert config["source_asset"]["source_type"] == "archive"
    assert config["dependency_requirements"] == {
        "package": "mysql-community-server-core_8.4.8-1ubuntu24.04_amd64.deb",
        "raw": "libaio1t64, libnuma1",
        "external_packages": ["libaio1t64", "libnuma1"],
    }


def test_workflow_service_installs_mysql_dependency_assets(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    dependency_file = tmp_path / "assets" / "libaio.so.1t64"
    dependency_file.write_text("fake-libaio", encoding="utf-8")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "dependency_assets": [
                {
                    "name": "libaio.so.1t64",
                    "path": str(dependency_file),
                }
            ],
        },
    )

    assert install_result["success"] is True
    config = install_result["object"]["config"]
    lib_dir = Path(config["managed_instance"]["lib_dir"])
    assert (lib_dir / "libaio.so.1t64").exists()
    assert config["runtime_library_paths"] == [str(lib_dir.resolve())]


def test_workflow_service_installs_mysql_dependency_deb_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    dependency_deb = tmp_path / "assets" / "libaio1t64_0.3.113_amd64.deb"
    dependency_deb.write_text("fake-deb", encoding="utf-8")

    def fake_extract_dependency_deb(
        self: DatabaseServerObject,
        package_path: Path,
        target_dir: Path,
    ) -> None:
        lib_path = target_dir / "usr" / "lib" / "x86_64-linux-gnu" / "libaio.so.1t64"
        lib_path.parent.mkdir(parents=True, exist_ok=True)
        lib_path.write_text("fake-libaio", encoding="utf-8")

    monkeypatch.setattr(
        DatabaseServerObject,
        "_extract_dependency_deb_package",
        fake_extract_dependency_deb,
    )

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "dependency_assets": [
                {
                    "name": "libaio1t64",
                    "path": str(dependency_deb),
                }
            ],
        },
    )

    assert install_result["success"] is True
    config = install_result["object"]["config"]
    lib_dir = Path(config["managed_instance"]["lib_dir"])
    extracted_lib = (
        lib_dir
        / "libaio1t64_0.3.113_amd64"
        / "usr"
        / "lib"
        / "x86_64-linux-gnu"
        / "libaio.so.1t64"
    )
    assert extracted_lib.exists()
    assert config["runtime_library_paths"] == [
        str(
            (
                lib_dir
                / "libaio1t64_0.3.113_amd64"
                / "usr"
                / "lib"
                / "x86_64-linux-gnu"
            ).resolve()
        )
    ]


def test_workflow_service_starts_mysql_managed_instance(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()

    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
            "mysql_config": {"health_check_mode": "tcp"},
        },
    )
    assert install_result["success"] is True

    start_result = service.start_object("mysql_service")
    assert start_result["success"] is True
    assert start_result["status"] == "running"
    assert "started" in start_result["message"]

    status = service.get_object_status("mysql_service")
    assert status["success"] is True
    assert status["object"]["status"] == "running"
    details = status["object"]["metadata"]["runtime"]["details"]
    assert details["pid"]
    assert details["endpoint"].endswith(f":{mysql_port}")
    normalized_binary = _normalized_path(details["mysql_binary"])
    assert normalized_binary.endswith("bin/mysqld") or normalized_binary.endswith(
        "bin/mysqld.cmd"
    )
    assert (
        status["object"]["metadata"]["crash_capture"]["enable_attempt"]["attempted"]
        is True
    )
    start_preflight = status["object"]["metadata"]["runtime_backend"]["last_preflight"]
    assert start_preflight["status"] == "success"

    stop_result = service.stop_object("mysql_service")
    assert stop_result["success"] is True
    assert stop_result["status"] == "stopped"
    checks = stop_result["checks"]
    assert checks["workspace_boundary"]["ok"] is True
    assert checks["process_cleanup"]["ok"] is True
    assert checks["port_release"]["ok"] is True
    assert checks["all_passed"] is True
    stopped_status = service.get_object_status("mysql_service")
    assert stopped_status["success"] is True
    assert (
        stopped_status["object"]["metadata"]["runtime_backend"]["last_preflight"]
        == start_preflight
    )


def test_workflow_service_records_crash_capture_enable_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    install_result = service.install_object("service", "demo_service")
    assert install_result["success"] is True

    def fake_attempt(
        self: WorkflowService,
        capability: dict[str, object],
    ) -> dict[str, object]:
        updated = capability.copy()
        updated["core_enabled"] = True
        updated["enable_attempt"] = {
            "attempted": True,
            "status": "success",
            "strategy": "process_rlimit_core",
            "failure_reason": "",
            "attempted_at": "2026-04-21T00:00:00",
        }
        return updated

    monkeypatch.setattr(
        WorkflowService,
        "_attempt_object_crash_capture_enable",
        fake_attempt,
    )

    start_result = service.start_object("demo_service")
    assert start_result["success"] is True

    status = service.get_object_status("demo_service")
    crash_capture = status["object"]["metadata"]["crash_capture"]
    assert crash_capture["core_enabled"] is True
    assert crash_capture["enable_attempt"]["attempted"] is True
    assert crash_capture["enable_attempt"]["status"] == "success"


def test_workflow_service_reports_missing_mysql_runtime_dependencies(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": _find_free_port(),
        },
    )
    assert install_result["success"] is True

    monkeypatch.setattr(
        DatabaseServerComponent,
        "_check_binary_dependencies",
        lambda self, binary, env=None: ["libaio.so.1t64", "libnuma.so.1"],
    )

    start_result = service.start_object("mysql_service")
    assert start_result["success"] is False
    assert start_result["status"] == "error"
    assert "missing required shared libraries" in start_result["message"]
    assert "libaio.so.1t64" in start_result["message"]
    assert "libnuma.so.1" in start_result["message"]
    status = service.get_object_status("mysql_service")
    assert status["success"] is True
    assert status["object"]["status"] == OBJECT_STATUS_START_FAILED_PRESERVED
    assert status["object"]["failure_state"]["phase"] == "start"
    assert status["object"]["available_actions"] == {
        "clear": True,
        "reset": True,
    }
    assert "clear" in status["object"]["suggested_actions"]
    assert "reset" in status["object"]["suggested_actions"]
    assert status["object"]["linked_problems"][0]["problem_type"] == (
        "dependency_configuration"
    )
    backend = status["object"]["metadata"]["runtime_backend"]
    assert "last_preflight" not in backend


def test_workflow_service_reports_mysql_runtime_backend_preflight_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": _find_free_port(),
        },
    )
    assert install_result["success"] is True

    class _DeniedSocket:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def __enter__(self) -> "_DeniedSocket":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def setsockopt(self, *_args: object) -> None:
            return None

        def bind(self, _address: tuple[str, int]) -> None:
            raise PermissionError("Operation not permitted")

    monkeypatch.setattr("ptest.objects.db_server.socket.socket", _DeniedSocket)

    start_result = service.start_object("mysql_service")
    assert start_result["success"] is False
    assert start_result["status"] == "error"
    # preflight bind probe 捕获 PermissionError 后阻断 start
    assert start_result["error_code"] == "object_start_preflight_failed"
    preflight = start_result["runtime_preflight"]
    assert preflight["status"] == "failed"
    port_check = next(c for c in preflight["checks"] if c["code"] == "port_bind")
    assert port_check["status"] == "failed"
    assert "does not permit binding" in port_check["message"]
    assert "Operation not permitted" in port_check["message"]
    # 对象保持 installed 状态（未进入 start_failed_preserved）
    status = service.get_object_status("mysql_service")
    assert status["success"] is True
    assert status["object"]["status"] == "installed"
    assert status["object"]["linked_problems"][0]["problem_type"] == (
        "dependency_configuration"
    )


def test_workflow_service_uninstalls_mysql_managed_instance(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()

    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
            "mysql_config": {"health_check_mode": "tcp"},
        },
    )
    assert install_result["success"] is True
    instance_root = Path(
        install_result["object"]["config"]["managed_instance"]["instance_root"]
    )
    assert instance_root.exists()

    start_result = service.start_object("mysql_service")
    assert start_result["success"] is True

    uninstall_result = service.uninstall_object("mysql_service")
    assert uninstall_result["success"] is True
    assert uninstall_result["status"] == "removed"
    assert not instance_root.exists()
    checks = uninstall_result["checks"]
    assert checks["workspace_boundary"]["ok"] is True
    assert checks["process_cleanup"]["ok"] is True
    assert checks["port_release"]["ok"] is True
    assert checks["object_cleanup"]["ok"] is True
    assert checks["object_cleanup"]["managed_paths_removed"] is True
    assert checks["all_passed"] is True
    assert (
        service.get_object_status("mysql_service")["error_code"] == "object_not_found"
    )


def test_workflow_service_binds_database_case_to_mysql_object(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": 3307,
        },
    )
    assert install_result["success"] is True
    monkeypatch.setattr(service, "OBJECT_ARTIFACT_MAX_SCAN_FILES", 2)
    data_dir = Path(install_result["object"]["config"]["managed_instance"]["data_dir"])
    for index in range(3):
        (data_dir / f"sample_{index}.txt").write_text(
            f"sample {index}",
            encoding="utf-8",
        )

    record = service.storage.get_object("mysql_service")
    assert record is not None
    record.status = "running"
    record.metadata = {
        **record.metadata,
        "runtime": {
            "status": "running",
            "details": {
                "db_type": "mysql",
                "endpoint": "127.0.0.1:3307",
            },
        },
    }
    service.storage.upsert_object(record)

    capture: dict[str, object] = {}
    monkeypatch.setattr(case_executor_module, "PYMYSQL_AVAILABLE", True)
    monkeypatch.setattr(case_executor_module, "pymysql", _FakePyMySQLModule(capture))

    add_result = service.add_case(
        "mysql_bound_case",
        {
            "type": "database",
            "object_name": "mysql_service",
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    assert add_result["success"] is True

    run_result = service.run_case("mysql_bound_case")
    assert run_result["success"] is True
    assert run_result["status"] == "passed"
    assert capture["connect_kwargs"] == {
        "host": "127.0.0.1",
        "port": 3307,
        "user": "root",
        "password": "",
        "database": None,
        "charset": "utf8mb4",
    }

    records = service.list_execution_records("mysql_bound_case")
    assert len(records) == 1
    case_payload = records[0]["metadata"]["case"]["data"]
    assert case_payload["object_name"] == "mysql_service"
    assert case_payload["db_type"] == "mysql"
    assert case_payload["host"] == "127.0.0.1"
    assert case_payload["port"] == 3307
    assert "database" not in case_payload
    object_artifacts = records[0]["metadata"]["object_artifacts"]
    assert object_artifacts["selection"]["mode"] == "explicit_refs"
    assert object_artifacts["selection"]["object_refs"] == ["mysql_service"]
    before_object = object_artifacts["before"]["objects"][0]
    after_object = object_artifacts["after"]["objects"][0]
    assert before_object["object_name"] == "mysql_service"
    assert "status" in after_object
    assert after_object["installed"] is True
    assert "runtime_backend" in after_object
    assert "runtime" in after_object
    assert after_object["artifact_sources"]["data_dir"]["exists"] is True
    assert after_object["artifact_sources"]["data_dir"]["kind"] == "directory"
    assert after_object["artifact_sources"]["data_dir"]["scan_truncated"] is True
    assert len(after_object["artifact_sources"]["data_dir"]["latest_files"]) == 2
    assert "mysql_service" in [
        item["object_name"] for item in object_artifacts["changes"]["objects"]
    ]
    artifact_dir = tmp_path / ".ptest" / "artifacts" / records[0]["execution_id"]
    object_artifacts_path = artifact_dir / "context" / "object_artifacts.json"
    assert object_artifacts_path.exists()
    artifact_index = json.loads(
        (artifact_dir / "indexes" / "artifact_index.json").read_text(encoding="utf-8")
    )
    assert "\\" not in artifact_index["files"]["object_artifacts"]
    assert _normalized_path(artifact_index["files"]["object_artifacts"]).endswith(
        "context/object_artifacts.json"
    )
    assert (
        artifact_index["categories"]["context"]["object_artifacts"]
        == (artifact_index["files"]["object_artifacts"])
    )
    artifacts = service.get_execution_artifacts(records[0]["execution_id"])
    assert artifacts["success"] is True
    object_artifacts_summary = artifacts["artifacts"]["object_artifacts_summary"]
    assert object_artifacts_summary["available"] is True
    assert object_artifacts_summary["artifact_ref"].endswith(
        "context/object_artifacts.json"
    )
    assert object_artifacts_summary["selection"]["mode"] == "explicit_refs"
    assert object_artifacts_summary["object_count"] == 1
    assert object_artifacts_summary["changed_object_count"] >= 0
    assert object_artifacts_summary["objects"][0]["object_name"] == "mysql_service"
    object_artifacts_path.write_text("{", encoding="utf-8")
    corrupted_artifacts = service.get_execution_artifacts(records[0]["execution_id"])
    assert corrupted_artifacts["success"] is True
    corrupted_summary = corrupted_artifacts["artifacts"]["object_artifacts_summary"]
    assert corrupted_summary["available"] is False
    assert corrupted_summary["artifact_ref"].endswith("context/object_artifacts.json")
    assert "error" in corrupted_summary

    status_result = service.get_object_status("mysql_service")
    assert status_result["success"] is True
    diagnostics = status_result["object"]["diagnostics"]
    assert diagnostics["runtime_backend"]["name"] == "host"
    assert diagnostics["managed_instance"]["available"] is True
    assert any(
        view["view"] == "object_status" for view in diagnostics["suggested_views"]
    )


def test_workflow_service_object_artifact_summary_counts_inferred_changes_after_preview_limit(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    object_artifacts = {
        "before": {
            "objects": [
                {
                    "object_name": f"object_{index:02d}",
                    "object_found": True,
                    "status": "running",
                }
                for index in range(11)
            ]
        },
        "after": {
            "objects": [
                {
                    "object_name": f"object_{index:02d}",
                    "object_found": True,
                    "status": "stopped",
                }
                for index in range(11)
            ]
        },
        "changes": {"objects": []},
    }

    summary = service._summarize_object_artifacts(object_artifacts)

    assert summary["object_count"] == 11
    assert summary["changed_object_count"] == 11
    assert len(summary["objects"]) == 10


def test_workflow_service_reports_missing_bound_database_object(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    add_result = service.add_case(
        "mysql_missing_object_case",
        {
            "type": "database",
            "object_name": "missing_mysql",
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    assert add_result["success"] is True

    run_result = service.run_case("mysql_missing_object_case")
    assert run_result["success"] is False
    assert run_result["status"] == "error"
    assert "missing_mysql" in run_result["error"]


def test_workflow_service_runs_all_cases_with_bound_mysql_object(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": 3308,
        },
    )
    assert install_result["success"] is True

    record = service.storage.get_object("mysql_service")
    assert record is not None
    record.status = "running"
    service.storage.upsert_object(record)

    monkeypatch.setattr(case_executor_module, "PYMYSQL_AVAILABLE", True)
    monkeypatch.setattr(
        case_executor_module,
        "pymysql",
        _FakePyMySQLModule({}),
    )

    add_result = service.add_case(
        "mysql_bound_case_batch",
        {
            "type": "database",
            "object_name": "mysql_service",
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    assert add_result["success"] is True

    run_result = service.run_all_cases()
    assert run_result["success"] is True
    assert run_result["passed"] == 1
    assert run_result["failed"] == 0


def test_workflow_service_runs_mysql_crud_case_with_bound_object(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": 3309,
        },
    )
    assert install_result["success"] is True

    record = service.storage.get_object("mysql_service")
    assert record is not None
    record.status = "running"
    service.storage.upsert_object(record)

    monkeypatch.setattr(case_executor_module, "PYMYSQL_AVAILABLE", True)
    monkeypatch.setattr(
        case_executor_module,
        "pymysql",
        _FakePyMySQLModule({}),
    )

    add_result = service.add_case(
        "mysql_crud_case",
        {
            "type": "database",
            "object_name": "mysql_service",
            "operations": [
                {
                    "name": "create_database",
                    "query": "CREATE DATABASE IF NOT EXISTS ptest_mysql_demo",
                },
                {
                    "name": "use_database",
                    "query": "USE ptest_mysql_demo",
                },
                {
                    "name": "create_table",
                    "query": "CREATE TABLE crud_items (id INT, name VARCHAR(32))",
                },
                {
                    "name": "insert",
                    "query": "INSERT INTO crud_items VALUES (1, 'alpha')",
                    "expected_result": {"count": 1},
                },
                {
                    "name": "select_after_insert",
                    "query": "SELECT id, name FROM crud_items",
                    "expected_result": [{"id": 1, "name": "alpha"}],
                },
                {
                    "name": "update",
                    "query": "UPDATE crud_items SET name = 'beta' WHERE id = 1",
                    "expected_result": {"count": 1},
                },
                {
                    "name": "select_after_update",
                    "query": "SELECT id, name FROM crud_items",
                    "expected_result": [{"id": 1, "name": "beta"}],
                },
                {
                    "name": "delete",
                    "query": "DELETE FROM crud_items WHERE id = 1",
                    "expected_result": {"count": 1},
                },
                {
                    "name": "select_after_delete",
                    "query": "SELECT COUNT(*) AS count FROM crud_items",
                    "expected_result": {"count": 0},
                },
            ],
        },
    )
    assert add_result["success"] is True

    run_result = service.run_case("mysql_crud_case")
    assert run_result["success"] is True
    assert run_result["status"] == "passed"
    output = run_result["output"]
    assert isinstance(output, list)
    assert len(output) == 9
    assert output[0]["name"] == "create_database"
    assert output[1]["name"] == "use_database"
    results_by_name = {item["name"]: item["result"] for item in output}
    assert results_by_name["select_after_insert"] == [{"id": 1, "name": "alpha"}]
    assert results_by_name["select_after_update"] == [{"id": 1, "name": "beta"}]
    assert results_by_name["select_after_delete"] == [{"count": 0}]


def test_workflow_service_requires_bound_database_object_to_be_running(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
        },
    )
    assert install_result["success"] is True

    add_result = service.add_case(
        "mysql_not_running_case",
        {
            "type": "database",
            "object_name": "mysql_service",
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    assert add_result["success"] is True

    run_result = service.run_case("mysql_not_running_case")
    assert run_result["success"] is False
    assert run_result["status"] == "error"
    assert "not running" in run_result["error"]


def test_workflow_service_rejects_invalid_mysql_package_path(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(tmp_path / "missing-mysql.tar.xz"),
            "workspace_path": str(tmp_path),
        },
    )

    assert install_result["success"] is False
    assert install_result["status"] == "error"
    assert "does not exist" in install_result["message"]
    assert install_result["object"]["type_name"] == "database_server"
    assert install_result["object"]["status"] == OBJECT_STATUS_ERROR
    assert install_result["object"]["config"]["mysql_package_path"].endswith(
        "missing-mysql.tar.xz"
    )


def test_workflow_service_preserves_mysql_install_failure_after_artifacts_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    def fail_extract_package(
        self: DatabaseServerObject,
        *,
        staged_package: Path,
        install_dir: Path,
    ) -> tuple[Path, dict[str, object]]:
        raise RuntimeError(
            f"simulated extraction failure for {staged_package.name} in {install_dir}"
        )

    monkeypatch.setattr(
        DatabaseServerObject,
        "_extract_mysql_package",
        fail_extract_package,
    )

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
        },
    )

    assert install_result["success"] is False
    assert install_result["status"] == "error"
    assert install_result["object"]["status"] == OBJECT_STATUS_INSTALL_FAILED_PRESERVED
    config = install_result["object"]["config"]
    assert Path(config["managed_instance"]["instance_root"]).exists()
    assert Path(config["staged_package_path"]).exists()

    status = service.get_object_status("mysql_service")
    assert status["success"] is True
    assert status["object"]["status"] == OBJECT_STATUS_INSTALL_FAILED_PRESERVED
    assert status["object"]["failure_state"]["phase"] == "install"
    assert status["object"]["available_actions"] == {
        "clear": True,
        "reset": True,
    }
    assert "clear" in status["object"]["suggested_actions"]
    assert "reset" in status["object"]["suggested_actions"]
    assert status["object"]["linked_problems"][0]["problem_type"] == (
        "dependency_object"
    )


def test_workflow_service_clears_preserved_mysql_install_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    def fail_extract_package(
        self: DatabaseServerObject,
        *,
        staged_package: Path,
        install_dir: Path,
    ) -> tuple[Path, dict[str, object]]:
        raise RuntimeError(
            f"simulated extraction failure for {staged_package.name} in {install_dir}"
        )

    monkeypatch.setattr(
        DatabaseServerObject,
        "_extract_mysql_package",
        fail_extract_package,
    )

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
        },
    )
    assert install_result["success"] is False
    instance_root = Path(
        install_result["object"]["config"]["managed_instance"]["instance_root"]
    )
    assert instance_root.exists()

    clear_result = service.clear_object("mysql_service")
    assert clear_result["success"] is True
    assert clear_result["status"] == "removed"
    assert not instance_root.exists()
    assert service.storage.get_object("mysql_service") is None
    assert (
        service.get_object_status("mysql_service")["error_code"] == "object_not_found"
    )


def test_workflow_service_clears_preserved_mysql_start_failure_to_installed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": _find_free_port(),
        },
    )
    assert install_result["success"] is True

    monkeypatch.setattr(
        DatabaseServerComponent,
        "_check_binary_dependencies",
        lambda self, binary, env=None: ["libaio.so.1t64"],
    )

    start_result = service.start_object("mysql_service")
    assert start_result["success"] is False

    clear_result = service.clear_object("mysql_service")
    assert clear_result["success"] is True
    assert clear_result["status"] == OBJECT_STATUS_INSTALLED

    status = service.get_object_status("mysql_service")
    assert status["success"] is True
    assert status["object"]["status"] == OBJECT_STATUS_INSTALLED
    assert "failure_state" not in status["object"]
    assert status["object"]["available_actions"] == {
        "clear": False,
        "reset": True,
    }
    assert "clear" not in status["object"]["suggested_actions"]
    assert "reset" in status["object"]["suggested_actions"]


def test_workflow_service_resets_running_mysql_object(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()

    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_service",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
            "mysql_config": {"health_check_mode": "tcp"},
        },
    )
    assert install_result["success"] is True
    instance_root = Path(
        install_result["object"]["config"]["managed_instance"]["instance_root"]
    )
    assert instance_root.exists()

    start_result = service.start_object("mysql_service")
    assert start_result["success"] is True

    reset_result = service.reset_object("mysql_service")
    assert reset_result["success"] is True
    assert reset_result["status"] == "removed"
    assert not instance_root.exists()
    assert service.storage.get_object("mysql_service") is None
    assert (
        service.get_object_status("mysql_service")["error_code"] == "object_not_found"
    )


def test_workflow_service_runs_case_and_generates_report(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    db_path = tmp_path / "sample.db"
    case_data = {
        "type": "database",
        "db_type": "sqlite",
        "database": str(db_path),
        "query": "SELECT 1 as value",
        "expected_result": [{"value": 1}],
    }

    add_result = service.add_case("sqlite_smoke", case_data)
    assert add_result["success"] is True

    run_result = service.run_case("sqlite_smoke")
    assert run_result["success"] is True
    assert run_result["status"] == "passed"

    report_path = Path(service.generate_report("json"))
    assert report_path.exists()
    assert report_path.parent == tmp_path / "reports"

    executions = service.list_execution_records("sqlite_smoke")
    assert len(executions) == 1
    assert executions[0]["status"] == "passed"
    artifact_dir = tmp_path / ".ptest" / "artifacts" / executions[0]["execution_id"]
    assert artifact_dir.exists()
    assert (artifact_dir / "context" / "environment.json").exists()
    assert (artifact_dir / "context" / "objects.json").exists()
    assert (artifact_dir / "context" / "object_artifacts.json").exists()
    assert (artifact_dir / "case" / "case.json").exists()
    assert (artifact_dir / "result" / "result.json").exists()
    assert (artifact_dir / "result" / "execution.json").exists()
    assert (artifact_dir / "indexes" / "artifact_index.json").exists()
    assert (artifact_dir / "logs" / "log_index.json").exists()
    artifacts = executions[0]["metadata"]["artifacts"]
    assert "\\" not in artifacts["directory"]
    assert "\\" not in artifacts["files"]["environment"]
    assert "\\" not in artifacts["files"]["object_artifacts"]
    assert "\\" not in artifacts["files"]["execution"]
    assert "\\" not in artifacts["indexes"]["artifact_index"]
    assert "\\" not in artifacts["indexes"]["log_index"]
    assert _normalized_path(artifacts["directory"]).startswith(".ptest/artifacts/")
    assert _normalized_path(artifacts["files"]["environment"]).endswith(
        "context/environment.json"
    )
    assert _normalized_path(artifacts["files"]["object_artifacts"]).endswith(
        "context/object_artifacts.json"
    )
    assert _normalized_path(artifacts["files"]["execution"]).endswith(
        "result/execution.json"
    )
    assert _normalized_path(artifacts["indexes"]["artifact_index"]).endswith(
        "indexes/artifact_index.json"
    )
    assert _normalized_path(artifacts["indexes"]["log_index"]).endswith(
        "logs/log_index.json"
    )
    artifact_index = json.loads(
        (artifact_dir / "indexes" / "artifact_index.json").read_text(encoding="utf-8")
    )
    log_index = json.loads(
        (artifact_dir / "logs" / "log_index.json").read_text(encoding="utf-8")
    )
    assert "\\" not in artifact_index["files"]["execution"]
    assert "\\" not in artifact_index["files"]["object_artifacts"]
    assert "\\" not in artifact_index["indexes"]["log_index"]
    assert (
        artifact_index["categories"]["context"]["object_artifacts"]
        == (artifact_index["files"]["object_artifacts"])
    )
    object_artifacts = json.loads(
        (artifact_dir / "context" / "object_artifacts.json").read_text(encoding="utf-8")
    )
    assert object_artifacts["selection"]["selection_reason"] == "all_objects_fallback"
    assert object_artifacts["before"]["objects"] == []
    assert object_artifacts["after"]["objects"] == []
    assert _normalized_path(artifact_index["files"]["execution"]).endswith(
        "result/execution.json"
    )
    assert _normalized_path(artifact_index["indexes"]["log_index"]).endswith(
        "logs/log_index.json"
    )
    assert log_index["workspace_logs_dir"] == "logs"

    suite_result = service.create_suite(
        {
            "name": "sqlite_suite",
            "cases": [
                {
                    "case_id": "sqlite_smoke",
                    "order": 1,
                }
            ],
        }
    )
    assert suite_result["success"] is True

    suite_run = service.run_suite("sqlite_suite")
    assert suite_run["success"] is True
    assert suite_run["total"] == 1

    suites = service.list_suites()
    assert "sqlite_suite" in suites

    destroy_result = service.destroy_environment()
    assert destroy_result["success"] is True
    assert destroy_result["isolation_cleanup"]["success"] is True
    artifact_root = tmp_path / ".ptest" / "artifacts"
    assert artifact_root.exists()
    assert list(artifact_root.iterdir()) == []

    env_status = service.get_environment_status()
    assert env_status["initialized"] is False
    assert env_status["status"] == "destroyed"


def test_workflow_service_can_reinitialize_after_destroy(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)

    first = service.init_environment()
    assert first.status == "ready"

    destroyed = service.destroy_environment()
    assert destroyed["success"] is True

    second = service.init_environment()
    assert second.status == "ready"
    assert second.root_path == str(tmp_path.resolve())
    assert second.metadata["isolation"]["env_id"]


def test_workflow_service_supports_data_contract_and_mock_workspace_assets(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    save_template = service.save_data_template(
        "user_template",
        {"username": "{{username}}", "email": "{{email}}"},
    )
    assert save_template["success"] is True

    template_list = service.list_data_templates()
    assert template_list["success"] is True
    assert "user_template" in template_list["data"]

    generated = service.generate_data_from_template("user_template", count=2)
    assert generated["success"] is True
    assert len(generated["data"]["results"]) == 2

    contract_manager = ContractManager(tmp_path / ".ptest" / "contracts")
    contract_manager._save_contract(  # noqa: SLF001
        APIContract(
            name="demo_contract",
            version="1.0.0",
            title="Demo",
            endpoints=[
                APIEndpoint(
                    path="/health",
                    method="GET",
                    summary="health",
                    responses={"200": {"description": "ok"}},
                )
            ],
        )
    )

    contract_list = service.list_contracts()
    assert contract_list["success"] is True
    assert "demo_contract" in contract_list["data"]

    generated_cases = service.generate_cases_from_contract(
        "demo_contract", persist=True
    )
    assert generated_cases["success"] is True
    assert generated_cases["data"]["persisted_case_ids"]

    mock_server = MockServer(MockConfig(name="demo_mock", port=18080))
    mock_server.save_config(tmp_path / ".ptest" / "mocks" / "demo_mock.json")

    mock_list = service.list_mock_servers()
    assert mock_list["success"] is True
    assert any(item["name"] == "demo_mock" for item in mock_list["data"])

    route_result = service.add_mock_route(
        "demo_mock",
        "/health",
        "GET",
        {"status": 200, "body": {"ok": True}},
    )
    assert route_result["success"] is True

    mock_status = service.get_mock_server_status("demo_mock")
    assert mock_status["success"] is True
    assert mock_status["data"]["name"] == "demo_mock"
    assert len(mock_status["data"]["routes"]) == 1


def test_workflow_service_returns_structured_contract_import_errors(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    result = service.import_contract(tmp_path / "missing-openapi.yaml")

    assert result["success"] is False
    assert result["status"] == "error"
    assert result["error_code"] in {
        "contract_import_failed",
        "contract_import_dependency_missing",
    }


def test_workflow_service_marks_detached_mock_runtime_as_stale(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    mock_server = MockServer(MockConfig(name="detached_mock", port=18081))
    mock_server.save_config(tmp_path / ".ptest" / "mocks" / "detached_mock.json")
    service._save_mock_state("detached_mock", {"status": "running"})  # noqa: SLF001

    reloaded = WorkflowService(tmp_path)
    status = reloaded.get_mock_server_status("detached_mock")

    assert status["success"] is True
    assert status["status"] == "stale"
    assert status["data"]["running"] is False
    assert status["data"]["runtime_state"]["status"] == "running"


def test_sqlite_database_case_generates_data_state_artifacts(
    tmp_path: Path,
) -> None:
    import sqlite3

    service = WorkflowService(tmp_path)
    service.init_environment()
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO demo (value) VALUES ('hello')")
    conn.commit()
    conn.close()
    service.add_case(
        "ds_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT * FROM demo",
            "expected_result": [{"id": 1, "value": "hello"}],
        },
    )
    result = service.run_case("ds_case")
    assert result["success"] is True
    executions = service.list_execution_records("ds_case")
    assert len(executions) == 1
    meta = executions[0]["metadata"]
    dsa = meta.get("data_state_artifacts")
    assert isinstance(dsa, dict)
    assert dsa["capture_status"] == "available"
    assert dsa["data_source"]["db_type"] == "sqlite"
    assert dsa["before"] is not None
    assert dsa["after"] is not None
    assert dsa["diff"]["capture_complete"] is True
    artifact_dir = tmp_path / ".ptest" / "artifacts" / executions[0]["execution_id"]
    assert (artifact_dir / "context" / "data_state.json").exists()


def test_data_state_artifacts_contains_schema_and_row_count(
    tmp_path: Path,
) -> None:
    import sqlite3

    service = WorkflowService(tmp_path)
    service.init_environment()
    db_path = tmp_path / "schema.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t1 (a INTEGER, b TEXT)")
    conn.execute("CREATE TABLE t2 (x REAL)")
    conn.execute("INSERT INTO t1 VALUES (1, 'a')")
    conn.execute("INSERT INTO t1 VALUES (2, 'b')")
    conn.execute("INSERT INTO t2 VALUES (3.14)")
    conn.commit()
    conn.close()
    service.add_case(
        "schema_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT COUNT(*) FROM t1",
            "expected_result": [{"count": 2}],
        },
    )
    service.run_case("schema_case")
    executions = service.list_execution_records("schema_case")
    dsa = executions[0]["metadata"]["data_state_artifacts"]
    after = dsa["after"]
    assert after["capture_status"] == "available"
    schema = after["schema"]
    assert schema["table_count"] == 2
    table_names = {t["name"] for t in schema["tables"]}
    assert "t1" in table_names
    assert "t2" in table_names
    t1_info = next(t for t in schema["tables"] if t["name"] == "t1")
    assert t1_info["row_count"] == 2
    col_names = {c["name"] for c in t1_info["columns"]}
    assert "a" in col_names
    assert "b" in col_names


def test_data_state_diff_captures_row_count_changes(
    tmp_path: Path,
) -> None:
    import sqlite3

    service = WorkflowService(tmp_path)
    service.init_environment()
    db_path = tmp_path / "diff.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items (name) VALUES ('initial')")
    conn.commit()
    conn.close()
    service.add_case(
        "diff_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "operations": [
                {
                    "query": "INSERT INTO items (name) VALUES ('added')",
                    "type": "execute",
                },
                {"query": "SELECT COUNT(*) as cnt FROM items", "type": "query"},
            ],
            "expected_result": [{"cnt": 2}],
        },
    )
    result = service.run_case("diff_case")
    assert result["success"] is True
    executions = service.list_execution_records("diff_case")
    dsa = executions[0]["metadata"]["data_state_artifacts"]
    diff = dsa["diff"]
    assert diff["capture_complete"] is True
    changes = diff["row_count_changes"]
    items_change = next(c for c in changes if c["table"] == "items")
    assert items_change["before"] == 1
    assert items_change["after"] == 2
    assert items_change["delta"] == 1
    assert diff["schema_changed"] is False


def test_data_state_capture_degrades_when_database_missing(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "missing_db_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(tmp_path / "nonexistent.db"),
            "query": "SELECT 1",
            "expected_result": [{"1": 1}],
        },
    )
    service.run_case("missing_db_case")
    executions = service.list_execution_records("missing_db_case")
    dsa = executions[0]["metadata"]["data_state_artifacts"]
    assert dsa is not None
    assert dsa["before"] is not None
    assert dsa["before"].get("capture_status") == "unavailable"
    diff = dsa["diff"]
    assert diff["capture_complete"] is False


def test_data_state_capture_unsupported_for_mysql(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "mysql_case",
        {
            "type": "database",
            "db_type": "mysql",
            "host": "localhost",
            "port": 3306,
            "query": "SELECT 1",
            "expected_result": [{"1": 1}],
        },
    )
    service.run_case("mysql_case")
    executions = service.list_execution_records("mysql_case")
    dsa = executions[0]["metadata"]["data_state_artifacts"]
    assert dsa is not None
    assert dsa["capture_status"] == "unsupported"


def test_non_database_case_no_data_state_artifacts(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "api_case",
        {
            "type": "api",
            "request": {"method": "GET", "url": "https://example.test/api"},
            "expected_status": 200,
        },
    )
    import requests as req
    from unittest.mock import patch

    with patch.object(
        req,
        "request",
        return_value=type(
            "R",
            (),
            {"status_code": 200, "json": lambda s: {}, "text": "{}", "headers": {}},
        )(),
    ):
        service.run_case("api_case")
    executions = service.list_execution_records("api_case")
    dsa = executions[0]["metadata"].get("data_state_artifacts")
    assert dsa is None


def test_suite_sqlite_data_state_snapshot_regression(tmp_path: Path) -> None:
    import sqlite3

    service = WorkflowService(tmp_path)
    service.init_environment()

    db_path = tmp_path / "suite_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items (name) VALUES ('initial')")
    conn.commit()
    conn.close()

    service.add_case(
        "suite_ds_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "operations": [
                {
                    "query": "INSERT INTO items (name) VALUES ('from_suite')",
                    "type": "execute",
                },
                {"query": "SELECT COUNT(*) as cnt FROM items", "type": "query"},
            ],
            "expected_result": [{"cnt": 2}],
        },
    )
    service.create_suite(
        {
            "name": "ds_suite",
            "cases": [{"case_id": "suite_ds_case", "order": 1}],
        }
    )

    suite_run = service.run_suite("ds_suite")
    assert suite_run["success"] is True

    executions = service.list_execution_records("suite_ds_case")
    assert len(executions) == 1
    dsa = executions[0]["metadata"].get("data_state_artifacts")
    assert isinstance(dsa, dict)
    assert dsa["capture_status"] == "available"
    assert dsa["before"] is not None
    assert dsa["after"] is not None
    assert dsa["diff"]["capture_complete"] is True
    changes = dsa["diff"]["row_count_changes"]
    items_change = next(c for c in changes if c["table"] == "items")
    assert items_change["before"] == 1
    assert items_change["after"] == 2
    assert items_change["delta"] == 1

    artifact_dir = tmp_path / ".ptest" / "artifacts" / executions[0]["execution_id"]
    assert (artifact_dir / "context" / "data_state.json").exists()


def test_data_state_capture_degrades_for_malformed_database_path(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.add_case(
        "malformed_db_case",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": 12345,
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    result = service.run_case("malformed_db_case")
    assert result["success"] is False
    executions = service.list_execution_records("malformed_db_case")
    assert len(executions) == 1
    dsa = executions[0]["metadata"].get("data_state_artifacts")
    assert isinstance(dsa, dict)
    assert dsa["capture_status"] == "unavailable"
    assert dsa["before"]["capture_status"] == "unavailable"
    assert "snapshot capture failed" in dsa["before"]["reason"]


# ── runtime preflight tests ────────────────────────────────────────────


def test_check_object_readiness_mysql_preflight_passed(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
            "mysql_config": {"health_check_mode": "tcp"},
        },
    )
    assert install_result["success"] is True

    result = service.check_object_readiness("mysql_svc")
    assert result["success"] is True
    assert result["status"] == "passed"
    preflight = result["runtime_preflight"]
    assert preflight["object_name"] == "mysql_svc"
    assert preflight["object_type"] == "database_server"
    assert preflight["scope"] == "start"
    assert preflight["can_start"] is True
    assert preflight["summary"]["required_failed"] == 0
    check_codes = [c["code"] for c in preflight["checks"]]
    assert "object_installation" in check_codes
    assert "runtime_backend_capabilities" in check_codes
    assert "workspace_boundary" in check_codes
    assert "managed_paths" in check_codes
    assert "pid_state" in check_codes
    assert "port_bind" in check_codes
    assert "dependency_assets" in check_codes


def test_check_object_readiness_port_bind_failed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    occupied_port = _find_free_port()
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": occupied_port,
        },
    )
    assert install_result["success"] is True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", occupied_port))
        blocker.listen(1)
        result = service.check_object_readiness("mysql_svc")

    assert result["success"] is False
    assert result["status"] == "failed"
    preflight = result["runtime_preflight"]
    assert preflight["can_start"] is False
    port_check = next(c for c in preflight["checks"] if c["code"] == "port_bind")
    assert port_check["status"] == "failed"
    assert port_check["required"] is True


def test_check_object_readiness_unsupported_type(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    service.install_object("service", "redis_svc")
    result = service.check_object_readiness("redis_svc")
    assert result["success"] is False
    assert result["status"] == "unavailable"
    assert result["error_code"] == "object_type_not_supported"


def test_check_object_readiness_object_not_found(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    result = service.check_object_readiness("nonexistent")
    assert result["success"] is False
    assert result["status"] == "not_found"


def test_start_blocked_by_preflight_failure(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    occupied_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": occupied_port,
        },
    )
    assert install_result["success"] is True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", occupied_port))
        blocker.listen(1)
        start_result = service.start_object("mysql_svc")

    assert start_result["success"] is False
    assert start_result["error_code"] == "object_start_preflight_failed"
    preflight = start_result["runtime_preflight"]
    assert preflight["status"] == "failed"
    assert preflight["can_start"] is False
    port_check = next(c for c in preflight["checks"] if c["code"] == "port_bind")
    assert port_check["status"] == "failed"
    assert service.get_object_status("mysql_svc")["object"]["status"] == "installed"


def test_start_preflight_records_problem(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    occupied_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": occupied_port,
        },
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", occupied_port))
        blocker.listen(1)
        service.start_object("mysql_svc")

    problems = list(service.storage.load_problem_records().values())
    matching = [p for p in problems if p.object_refs == ["mysql_svc"]]
    assert len(matching) >= 1
    problem = matching[0]
    assert problem.problem_type == "dependency_object"
    # 检查 problem assets 中的 details 和 recovery
    assets = service.storage.get_problem_assets(problem.problem_id)
    assert assets is not None
    details = assets.details
    assert details["phase"] == "preflight"
    assert details["action"] == "start"
    assert "runtime_preflight" in details
    assert details["runtime_preflight"]["status"] == "failed"
    recovery = assets.recovery
    assert recovery["action"] == "fix_runtime_preflight"
    assert recovery["object_name"] == "mysql_svc"
    assert isinstance(recovery["failed_checks"], list)
    assert "port_bind" in recovery["failed_checks"]


def test_object_status_includes_runtime_preflight_diagnostics(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
            "mysql_config": {"health_check_mode": "tcp"},
        },
    )
    status = service.get_object_status("mysql_svc")
    assert status["success"] is True
    diagnostics = status["object"]["diagnostics"]
    assert "runtime_preflight" in diagnostics
    preflight = diagnostics["runtime_preflight"]
    assert preflight["object_name"] == "mysql_svc"
    assert preflight["status"] in {"passed", "warning", "failed"}


def test_object_status_preflight_from_metadata(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
            "mysql_config": {"health_check_mode": "tcp"},
        },
    )
    service.check_object_readiness("mysql_svc")
    status = service.get_object_status("mysql_svc")
    diagnostics = status["object"]["diagnostics"]
    assert diagnostics["runtime_preflight"]["checked_at"] is not None


def test_preflight_workspace_boundary_degrades_for_malformed_path(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后注入不可解析的 workspace_path
    record = service.storage.get_object("mysql_svc")
    record.config["workspace_path"] = "\x00invalid"
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    wb_check = next(c for c in preflight["checks"] if c["code"] == "workspace_boundary")
    assert wb_check["status"] == "failed"
    assert wb_check["required"] is True
    assert "could not be resolved" in wb_check["message"]


def test_preflight_dependency_requirements_schema_warning(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后注入非法 schema
    record = service.storage.get_object("mysql_svc")
    record.config["dependency_requirements"] = "not_a_dict"
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    da_check = next(c for c in preflight["checks"] if c["code"] == "dependency_assets")
    assert da_check["status"] == "warning"
    assert "schema_warnings" in da_check["details"]
    assert "str" in da_check["details"]["schema_warnings"][0]


def test_preflight_dependency_requirements_valid_dict(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后注入有效 dict
    record = service.storage.get_object("mysql_svc")
    record.config["dependency_requirements"] = {"libaio": ">=0.3"}
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    da_check = next(c for c in preflight["checks"] if c["code"] == "dependency_assets")
    assert da_check["status"] == "passed"
    assert da_check["details"]["dependency_requirements_keys"] == ["libaio"]


def test_preflight_workspace_boundary_empty_required_path(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后清空 config_file（启动必需路径）
    record = service.storage.get_object("mysql_svc")
    record.config["config_file"] = ""
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    wb_check = next(c for c in preflight["checks"] if c["code"] == "workspace_boundary")
    assert wb_check["status"] == "failed"
    assert wb_check["required"] is True
    assert "config_file:empty" in wb_check["message"]
    assert "config_file" in wb_check["details"]["empty_required"]


def test_preflight_workspace_boundary_empty_optional_path(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后清空 log_file（非启动必需路径）
    record = service.storage.get_object("mysql_svc")
    record.config["log_file"] = ""
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    wb_check = next(c for c in preflight["checks"] if c["code"] == "workspace_boundary")
    assert wb_check["status"] == "warning"
    assert wb_check["required"] is False
    assert "log_file" in wb_check["details"]["empty_optional"]


def test_preflight_workspace_boundary_empty_string_not_cwd(
    tmp_path: Path,
) -> None:
    """workspace_path="" 不应解析为 CWD，而应降级使用 root_path。"""
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后将 workspace_path 设为空字符串
    record = service.storage.get_object("mysql_svc")
    record.config["workspace_path"] = ""
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    wb_check = next(c for c in preflight["checks"] if c["code"] == "workspace_boundary")
    # 空 workspace_path 应降级为 root_path，不应解析为 CWD
    assert wb_check["details"]["workspace_path"] == str(tmp_path.resolve())


def test_preflight_workspace_boundary_managed_instance_empty_dir(
    tmp_path: Path,
) -> None:
    """managed_instance.data_dir="" 应产生 warning 而非静默跳过。"""
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后注入空 data_dir
    record = service.storage.get_object("mysql_svc")
    record.config["managed_instance"] = {
        "data_dir": "",
        "install_dir": str(tmp_path / "inst"),
    }
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    wb_check = next(c for c in preflight["checks"] if c["code"] == "workspace_boundary")
    # 空 data_dir 应进入 empty_optional
    assert wb_check["status"] == "warning"
    assert any(
        "managed_instance.data_dir" in p for p in wb_check["details"]["empty_optional"]
    )


def test_preflight_managed_paths_empty_dir_warning(
    tmp_path: Path,
) -> None:
    """managed_instance.data_dir="" 在 managed_paths 中应产生 warning。"""
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    record = service.storage.get_object("mysql_svc")
    record.config["managed_instance"] = {"data_dir": ""}
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    mp_check = next(c for c in preflight["checks"] if c["code"] == "managed_paths")
    assert mp_check["status"] == "warning"
    assert "data_dir:empty" in mp_check["details"]["missing_optional"]


def test_preflight_dependency_assets_non_list_schema_warning(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后注入非法类型
    record = service.storage.get_object("mysql_svc")
    record.config["dependency_assets"] = "not_a_list"
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    da_check = next(c for c in preflight["checks"] if c["code"] == "dependency_assets")
    assert da_check["status"] == "warning"
    assert "schema_warnings" in da_check["details"]
    assert "str" in da_check["details"]["schema_warnings"][0]


def test_preflight_dependency_assets_non_dict_item_schema_warning(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    # 安装后注入 list 中包含非 dict 元素
    record = service.storage.get_object("mysql_svc")
    record.config["dependency_assets"] = ["not_a_dict", 123]
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    da_check = next(c for c in preflight["checks"] if c["code"] == "dependency_assets")
    assert da_check["status"] == "warning"
    assert "schema_warnings" in da_check["details"]
    assert len(da_check["details"]["schema_warnings"]) == 2
    assert "str" in da_check["details"]["schema_warnings"][0]
    assert "int" in da_check["details"]["schema_warnings"][1]


def test_preflight_runtime_library_paths_non_list_schema_warning(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    record = service.storage.get_object("mysql_svc")
    record.config["runtime_library_paths"] = "not_a_list"
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    da_check = next(c for c in preflight["checks"] if c["code"] == "dependency_assets")
    assert da_check["status"] == "warning"
    assert "schema_warnings" in da_check["details"]
    assert any(
        "runtime_library_paths" in w for w in da_check["details"]["schema_warnings"]
    )


def test_preflight_runtime_library_paths_non_string_item_schema_warning(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    record = service.storage.get_object("mysql_svc")
    record.config["runtime_library_paths"] = [123, True]
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    da_check = next(c for c in preflight["checks"] if c["code"] == "dependency_assets")
    assert da_check["status"] == "warning"
    assert "schema_warnings" in da_check["details"]
    assert len(da_check["details"]["schema_warnings"]) == 2
    assert "int" in da_check["details"]["schema_warnings"][0]
    assert "bool" in da_check["details"]["schema_warnings"][1]


def test_preflight_dependency_assets_missing_path_warning(
    tmp_path: Path,
) -> None:
    """dependency_assets=[{"required": True}] 缺少 path 应产生 warning。"""
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    record = service.storage.get_object("mysql_svc")
    record.config["dependency_assets"] = [{"required": True}]
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    da_check = next(c for c in preflight["checks"] if c["code"] == "dependency_assets")
    assert da_check["status"] == "warning"
    assert "schema_warnings" in da_check["details"]
    assert any(
        "missing required 'path'" in w for w in da_check["details"]["schema_warnings"]
    )


def test_preflight_runtime_library_paths_empty_string_warning(
    tmp_path: Path,
) -> None:
    """runtime_library_paths=[""] 空字符串应产生 warning。"""
    service = WorkflowService(tmp_path)
    service.init_environment()
    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": mysql_port,
        },
    )
    assert install_result["success"] is True
    record = service.storage.get_object("mysql_svc")
    record.config["runtime_library_paths"] = [""]
    service.storage.upsert_object(record)

    result = service.check_object_readiness("mysql_svc")
    preflight = result["runtime_preflight"]
    da_check = next(c for c in preflight["checks"] if c["code"] == "dependency_assets")
    assert da_check["status"] == "warning"
    assert "schema_warnings" in da_check["details"]
    assert any("empty string" in w for w in da_check["details"]["schema_warnings"])


def test_start_preflight_blocking_includes_checks_field(
    tmp_path: Path,
) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    occupied_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    install_result = service.install_object(
        "mysql",
        "mysql_svc",
        {
            "mysql_package_path": str(package_path),
            "workspace_path": str(tmp_path),
            "port": occupied_port,
        },
    )
    assert install_result["success"] is True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", occupied_port))
        blocker.listen(1)
        start_result = service.start_object("mysql_svc")

    assert start_result["success"] is False
    assert "checks" in start_result
    assert start_result["checks"]["status"] == "failed"
    assert start_result["checks"] == start_result["runtime_preflight"]
