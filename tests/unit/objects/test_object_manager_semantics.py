from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from ptest.objects.db_server import DatabaseServerComponent
from ptest.objects.manager import ObjectManager


class _MockEnvManager:
    def __init__(self) -> None:
        self.logger = logging.getLogger("ptest-test-object-manager")
        self.test_path = Path(".")


def test_mysql_alias_maps_to_database_server() -> None:
    manager = ObjectManager(_MockEnvManager())

    assert manager.normalize_type("mysql") == "database_server"
    assert manager.get_object_type("mysql") == "database_server"


def test_sqlite_alias_remains_database() -> None:
    manager = ObjectManager(_MockEnvManager())

    assert manager.normalize_type("sqlite") == "database"
    assert manager.get_object_type("sqlite") == "database"


def test_mysql_component_places_defaults_file_before_runtime_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binary = tmp_path / "bin" / "mysqld"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    config_file = tmp_path / "my.cnf"
    config_file.write_text("[mysqld]\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    log_file = tmp_path / "mysql.log"
    pid_file = tmp_path / "mysql.pid"

    commands: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        DatabaseServerComponent,
        "_check_binary_dependencies",
        lambda self, binary, env=None: [],
    )
    monkeypatch.setattr(
        DatabaseServerComponent,
        "health_check",
        lambda self: (True, "ok"),
    )
    monkeypatch.setattr("ptest.objects.db_server.time.sleep", lambda *_args: None)
    monkeypatch.setattr("ptest.objects.db_server.subprocess.run", fake_run)

    component = DatabaseServerComponent(
        {
            "db_type": "mysql",
            "host": "127.0.0.1",
            "port": 13316,
            "data_dir": str(data_dir),
            "config_file": str(config_file),
            "log_file": str(log_file),
            "pid_file": str(pid_file),
            "mysql_binary": str(binary),
            "mysql_config": {"health_check_mode": "tcp"},
        }
    )

    success, message = component.start()

    assert success is True
    assert "started" in message
    assert len(commands) == 2
    assert commands[0][1] == f"--defaults-file={config_file}"
    assert commands[0][2] == "--initialize-insecure"
    assert commands[1][1] == f"--defaults-file={config_file}"
    assert commands[1][2] == "--daemonize"
