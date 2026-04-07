from __future__ import annotations

import tarfile
import textwrap
from pathlib import Path

import ptest.cases.executor as case_executor_module
from ptest.api import PTestAPI


def _normalized_path(path: str) -> str:
    return path.replace("\\", "/")


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
            raise SystemExit(0)
            """
        ),
        encoding="utf-8",
    )
    fake_mysqld.chmod(0o755)
    with tarfile.open(package_path, "w:xz") as archive:
        archive.add(stage_dir / "mysql-8.4", arcname="mysql-8.4")
    return package_path


class _FakeMySQLCursor:
    description = [("value",)]
    rowcount = 1

    def __enter__(self) -> "_FakeMySQLCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str) -> None:
        self.query = query

    def fetchall(self) -> list[tuple[int]]:
        return [(1,)]


class _FakeMySQLConnection:
    def __init__(self, capture: dict[str, object], kwargs: dict[str, object]) -> None:
        capture["connect_kwargs"] = kwargs

    def cursor(self) -> _FakeMySQLCursor:
        return _FakeMySQLCursor()

    def close(self) -> None:
        return None

    def commit(self) -> None:
        return None


class _FakePyMySQLModule:
    def __init__(self, capture: dict[str, object]) -> None:
        self.capture = capture

    def connect(self, **kwargs: object) -> _FakeMySQLConnection:
        return _FakeMySQLConnection(self.capture, kwargs)


def test_api_returns_structured_environment_responses(tmp_path: Path) -> None:
    api = PTestAPI(work_path=str(tmp_path))

    init_result = api.init_environment()
    assert init_result["success"] is True
    assert init_result["status"] == "ready"
    assert init_result["data"]["root_path"] == str(tmp_path.resolve())

    status_result = api.get_environment_status()
    assert status_result["success"] is True
    assert status_result["status"] == "ready"
    assert status_result["data"]["path"] == str(tmp_path.resolve())


def test_api_returns_structured_case_responses(tmp_path: Path) -> None:
    api = PTestAPI(work_path=str(tmp_path))
    api.init_environment()

    create_result = api.create_test_case(
        test_type="database",
        name="sqlite_case",
        content={
            "type": "database",
            "db_type": "sqlite",
            "database": str(tmp_path / "sample.db"),
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    assert create_result["success"] is True
    case_id = create_result["data"]["case_id"]

    list_result = api.list_test_cases()
    assert list_result["success"] is True
    assert isinstance(list_result["data"], list)
    assert any(item["id"] == case_id for item in list_result["data"])

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is True
    assert run_result["status"] == "passed"
    assert "message" in run_result

    records_result = api.list_execution_records(case_id=case_id)
    assert records_result["success"] is True
    execution_id = records_result["data"][0]["execution_id"]

    execution_result = api.get_execution_record(execution_id)
    assert execution_result["success"] is True
    assert execution_result["data"]["execution_id"] == execution_id

    artifacts_result = api.get_execution_artifacts(execution_id)
    assert artifacts_result["success"] is True
    assert artifacts_result["data"]["execution_id"] == execution_id
    assert _normalized_path(artifacts_result["data"]["files"]["execution"]).endswith(
        "result/execution.json"
    )


def test_api_supports_mysql_lifecycle_scenario_inputs(tmp_path: Path) -> None:
    api = PTestAPI(work_path=str(tmp_path))
    api.init_environment()

    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")

    create_result = api.create_object(
        "mysql",
        "mysql_service",
        mysql_package_path=str(package_path),
        workspace_path=str(tmp_path),
    )

    assert create_result["success"] is True
    assert create_result["object"]["type_name"] == "database_server"
    config = create_result["object"]["config"]
    assert config["mysql_package_path"] == str(package_path.resolve())
    assert config["workspace_path"] == str(tmp_path.resolve())
    assert config["server_port"] == api.workflow.DEFAULT_MANAGED_MYSQL_PORT
    assert config["scenario"]["scenario_name"] == "mysql_full_lifecycle"
    assert config["source_asset"]["product"] == "mysql"


def test_api_runs_mysql_case_bound_to_managed_object(
    tmp_path: Path,
    monkeypatch,
) -> None:
    api = PTestAPI(work_path=str(tmp_path))
    api.init_environment()

    package_path = _create_fake_mysql_archive(tmp_path / "assets" / "mysql-8.4.tar.xz")
    create_result = api.create_object(
        "mysql",
        "mysql_service",
        mysql_package_path=str(package_path),
        workspace_path=str(tmp_path),
        port=3307,
    )
    assert create_result["success"] is True

    record = api.workflow.storage.get_object("mysql_service")
    assert record is not None
    record.status = "running"
    api.workflow.storage.upsert_object(record)

    capture: dict[str, object] = {}
    monkeypatch.setattr(case_executor_module, "PYMYSQL_AVAILABLE", True)
    monkeypatch.setattr(case_executor_module, "pymysql", _FakePyMySQLModule(capture))

    case_result = api.create_test_case(
        test_type="database",
        name="mysql_bound_case",
        content={
            "type": "database",
            "object_name": "mysql_service",
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    assert case_result["success"] is True

    run_result = api.run_test_case(case_result["data"]["case_id"])
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
