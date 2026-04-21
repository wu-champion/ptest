from __future__ import annotations

import socket
import tarfile
import textwrap
import time
from pathlib import Path

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


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_workspace_core_capture_capability_is_exposed_for_managed_mysql(
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

    workspace = tmp_path / "workspace_crash_capture"
    api = PTestAPI(work_path=workspace)
    init_result = api.init_environment()
    assert init_result["success"] is True
    crash_capture = init_result["data"]["metadata"]["crash_capture"]
    assert crash_capture["dump_dir"] == str((workspace / "dumps").resolve())
    assert crash_capture["core_supported"] is True
    assert crash_capture["enable_attempt"]["status"] == "pending"

    mysql_port = _find_free_port()
    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    create_result = api.create_object(
        "mysql",
        "mysql_service",
        mysql_package_path=str(package_path),
        workspace_path=str(workspace),
        port=mysql_port,
        mysql_config={"health_check_mode": "tcp"},
    )
    assert create_result["success"] is True
    dump_dir = (
        workspace / ".ptest" / "managed_objects" / "mysql_service" / "dumps"
    ).resolve()
    assert create_result["data"]["metadata"]["crash_capture"]["dump_dir"] == str(
        dump_dir
    )

    start_result = api.start_object("mysql_service")
    assert start_result["success"] is True

    status_result = api.get_object_status("mysql_service")
    assert status_result["success"] is True
    object_capture = status_result["data"]["metadata"]["crash_capture"]
    assert object_capture["dump_dir"] == str(dump_dir)
    assert object_capture["enable_attempt"]["attempted"] is True
    assert object_capture["enable_attempt"]["status"] in {"success", "failed"}
    assert dump_dir.exists()
