from __future__ import annotations

import json
import socket
import tarfile
import textwrap
from pathlib import Path

import ptest.cases.executor as case_executor_module
from ptest.app import WorkflowService
from ptest.contract.manager import APIContract, APIEndpoint, ContractManager
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
        if normalized.startswith("CREATE TABLE"):
            self.rowcount = 0
            self.description = []
            self._rows = []
            return
        if normalized.startswith("INSERT INTO"):
            self.state["rows"] = [{"id": 1, "name": "alpha"}]
            self.rowcount = 1
            self.description = []
            self._rows = []
            return
        if normalized.startswith("UPDATE"):
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
    assert record.metadata["isolation"]["env_id"].startswith("env_")
    assert record.metadata["isolation"]["isolation_level"] == "basic"
    assert record.metadata["isolation"]["recovery_strategy"] == "created_new"
    assert record.metadata["isolation"]["validated"] is True
    assert record.metadata["isolation"]["health"] is True

    install_result = service.install_object("service", "demo_service")
    assert install_result["success"] is True

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
    assert _normalized_path(managed_instance["lib_dir"]).endswith("mysql_service/lib")
    assert _normalized_path(managed_instance["files_dir"]).endswith(
        "mysql_service/mysql-files"
    )
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

    stop_result = service.stop_object("mysql_service")
    assert stop_result["success"] is True
    assert stop_result["status"] == "stopped"
    checks = stop_result["checks"]
    assert checks["workspace_boundary"]["ok"] is True
    assert checks["process_cleanup"]["ok"] is True
    assert checks["port_release"]["ok"] is True
    assert checks["all_passed"] is True


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
    assert "does not permit binding" in start_result["message"]
    assert "Operation not permitted" in start_result["message"]


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

    record = service.storage.get_object("mysql_service")
    assert record is not None
    record.status = "running"
    record.metadata = {
        "runtime": {
            "status": "running",
            "details": {
                "db_type": "mysql",
                "endpoint": "127.0.0.1:3307",
            },
        }
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
        "database": "ptest_mysql",
        "charset": "utf8mb4",
    }

    records = service.list_execution_records("mysql_bound_case")
    assert len(records) == 1
    case_payload = records[0]["metadata"]["case"]["data"]
    assert case_payload["object_name"] == "mysql_service"
    assert case_payload["db_type"] == "mysql"
    assert case_payload["host"] == "127.0.0.1"
    assert case_payload["port"] == 3307
    assert case_payload["database"] == "ptest_mysql"


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
    assert len(output) == 7
    assert output[0]["name"] == "create_table"
    assert output[2]["result"] == [{"id": 1, "name": "alpha"}]
    assert output[4]["result"] == [{"id": 1, "name": "beta"}]
    assert output[6]["result"] == [{"count": 0}]


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
    assert install_result["object"]["config"]["mysql_package_path"].endswith(
        "missing-mysql.tar.xz"
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
    assert (artifact_dir / "case" / "case.json").exists()
    assert (artifact_dir / "result" / "result.json").exists()
    assert (artifact_dir / "result" / "execution.json").exists()
    assert (artifact_dir / "indexes" / "artifact_index.json").exists()
    assert (artifact_dir / "logs" / "log_index.json").exists()
    artifacts = executions[0]["metadata"]["artifacts"]
    assert _normalized_path(artifacts["directory"]).startswith(".ptest/artifacts/")
    assert _normalized_path(artifacts["files"]["environment"]).endswith(
        "context/environment.json"
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
