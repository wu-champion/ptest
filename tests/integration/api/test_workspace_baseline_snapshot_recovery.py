from __future__ import annotations

import shutil
import sqlite3

from ptest.api import PTestAPI
from pathlib import Path

from ptest.models import ManagedObjectRecord, OBJECT_STATUS_ERROR, OBJECT_STATUS_RUNNING


def test_workspace_baseline_snapshot_can_restore_object_records(tmp_path) -> None:
    api = PTestAPI(work_path=tmp_path / "workspace_baseline_restore")
    api.init_environment()
    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="demo_service",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
            installed=True,
            config={"runtime_backend": "managed"},
        )
    )

    created = api.create_workspace_baseline("pre-mutation baseline")
    assert created["success"] is True
    baseline_id = created["data"]["baseline_id"]

    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="demo_service",
            type_name="service",
            status=OBJECT_STATUS_ERROR,
            installed=False,
            config={"runtime_backend": "managed", "mutated": True},
        )
    )
    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="residual_service",
            type_name="service",
            status=OBJECT_STATUS_ERROR,
            installed=False,
        )
    )

    restored = api.restore_workspace_baseline(baseline_id)
    assert restored["success"] is True
    assert restored["data"]["baseline"]["baseline_id"] == baseline_id
    assert restored["data"]["verification"]["scope"] == (
        "workspace_minimum_baseline_restore"
    )

    objects = api.workflow.storage.load_objects()
    assert set(objects.keys()) == {"demo_service"}
    restored_service = objects["demo_service"]
    assert restored_service.status == OBJECT_STATUS_RUNNING
    assert restored_service.installed is True

    baselines = api.list_workspace_baselines()
    assert baselines["success"] is True
    assert baselines["data"][0]["baseline_id"] == baseline_id


def test_workspace_baseline_snapshot_restores_object_reference_directories(
    tmp_path,
) -> None:
    workspace = tmp_path / "workspace_baseline_object_refs"
    api = PTestAPI(work_path=workspace)
    api.init_environment()

    instance_root = workspace / ".ptest" / "managed_objects" / "mysql_service"
    managed = {
        "instance_root": str(instance_root),
        "data_dir": str(instance_root / "data"),
        "log_dir": str(instance_root / "logs"),
        "dump_dir": str(instance_root / "dumps"),
    }
    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="mysql_service",
            type_name="mysql",
            status=OBJECT_STATUS_RUNNING,
            installed=True,
            config={
                "runtime_backend": "host",
                "managed_instance": managed,
            },
        )
    )

    data_dir = Path(managed["data_dir"])
    log_dir = Path(managed["log_dir"])
    dump_dir = Path(managed["dump_dir"])
    for directory in (data_dir, log_dir, dump_dir):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".baseline_marker").write_text("baseline", encoding="utf-8")

    created = api.create_workspace_baseline("object-reference baseline")
    assert created["success"] is True
    baseline_id = created["data"]["baseline_id"]
    assert created["data"]["object_reference_count"] >= 1

    for directory in (data_dir, log_dir, dump_dir):
        shutil.rmtree(directory)
        assert directory.exists() is False

    restored = api.restore_workspace_baseline(baseline_id)
    assert restored["success"] is True
    directory_restore = restored["data"]["verification"]["directory_restore"]
    assert directory_restore["scope"] == "workspace_object_reference_restore"
    restored_fields = {
        item["field"]
        for item in directory_restore["restored_paths"]
        if item["object_name"] == "mysql_service"
    }
    assert {"data_dir", "log_dir", "dump_dir"} <= restored_fields
    for directory in (data_dir, log_dir, dump_dir):
        assert directory.exists() is True


def test_workspace_baseline_snapshot_restores_small_config_content(tmp_path) -> None:
    workspace = tmp_path / "workspace_baseline_content_refs"
    api = PTestAPI(work_path=workspace)
    api.init_environment()

    instance_root = workspace / ".ptest" / "managed_objects" / "demo_service"
    config_dir = instance_root / "config"
    config_file = config_dir / "service.conf"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text("port=18080\nmode=baseline\n", encoding="utf-8")

    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="demo_service",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
            installed=True,
            config={
                "runtime_backend": "host",
                "managed_instance": {
                    "instance_root": str(instance_root),
                    "config_dir": str(config_dir),
                },
            },
        )
    )

    created = api.create_workspace_baseline("content-reference baseline")
    assert created["success"] is True
    baseline_id = created["data"]["baseline_id"]
    assert created["data"]["content_reference_count"] >= 1

    shutil.rmtree(config_dir)
    assert config_file.exists() is False

    restored = api.restore_workspace_baseline(baseline_id)
    assert restored["success"] is True
    content_restore = restored["data"]["verification"]["content_restore"]
    assert content_restore["scope"] == "workspace_content_reference_restore"
    restored_paths = {
        item["path"]
        for item in content_restore["restored_contents"]
        if item["object_name"] == "demo_service"
    }
    assert str(config_file.resolve()) in restored_paths
    assert config_file.read_text(encoding="utf-8") == "port=18080\nmode=baseline\n"


def test_workspace_baseline_snapshot_reports_overwritten_content(tmp_path) -> None:
    workspace = tmp_path / "workspace_baseline_content_conflict"
    api = PTestAPI(work_path=workspace)
    api.init_environment()

    instance_root = workspace / ".ptest" / "managed_objects" / "demo_service"
    config_dir = instance_root / "config"
    config_file = config_dir / "service.conf"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text("port=18080\nmode=baseline\n", encoding="utf-8")

    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="demo_service",
            type_name="service",
            status=OBJECT_STATUS_RUNNING,
            installed=True,
            config={
                "runtime_backend": "host",
                "managed_instance": {
                    "instance_root": str(instance_root),
                    "config_dir": str(config_dir),
                },
            },
        )
    )

    created = api.create_workspace_baseline("content-conflict baseline")
    assert created["success"] is True
    baseline_id = created["data"]["baseline_id"]

    config_file.write_text("port=18081\nmode=mutated\n", encoding="utf-8")

    restored = api.restore_workspace_baseline(baseline_id)
    assert restored["success"] is True
    content_restore = restored["data"]["verification"]["content_restore"]
    overwritten = [
        item
        for item in content_restore["overwritten_contents"]
        if item["object_name"] == "demo_service"
    ]
    assert len(overwritten) == 1
    assert overwritten[0]["path"] == str(config_file.resolve())
    assert overwritten[0]["action"] == "overwritten_to_baseline"
    assert overwritten[0]["previous_sha256"] != overwritten[0]["sha256"]
    assert config_file.read_text(encoding="utf-8") == "port=18080\nmode=baseline\n"

    restored_again = api.restore_workspace_baseline(baseline_id)
    unchanged = restored_again["data"]["verification"]["content_restore"][
        "unchanged_contents"
    ]
    assert any(
        item["path"] == str(config_file.resolve())
        and item["action"] == "already_at_baseline"
        for item in unchanged
    )


def test_workspace_baseline_snapshot_restores_small_sqlite_data_file(tmp_path) -> None:
    workspace = tmp_path / "workspace_baseline_sqlite_content"
    api = PTestAPI(work_path=workspace)
    api.init_environment()

    instance_root = workspace / ".ptest" / "managed_objects" / "demo_sqlite"
    data_dir = instance_root / "data"
    db_file = data_dir / "app.sqlite3"
    data_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_file) as connection:
        connection.execute("CREATE TABLE settings (name TEXT PRIMARY KEY, value TEXT)")
        connection.execute(
            "INSERT INTO settings (name, value) VALUES (?, ?)",
            ("mode", "baseline"),
        )

    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="demo_sqlite",
            type_name="sqlite",
            status=OBJECT_STATUS_RUNNING,
            installed=True,
            config={
                "runtime_backend": "host",
                "managed_instance": {
                    "instance_root": str(instance_root),
                    "data_dir": str(data_dir),
                },
            },
        )
    )

    created = api.create_workspace_baseline("sqlite-content baseline")
    assert created["success"] is True
    baseline_id = created["data"]["baseline_id"]
    assert created["data"]["content_reference_count"] >= 1

    shutil.rmtree(data_dir)
    assert db_file.exists() is False

    restored = api.restore_workspace_baseline(baseline_id)
    assert restored["success"] is True
    content_restore = restored["data"]["verification"]["content_restore"]
    restored_paths = {
        item["path"]
        for item in content_restore["restored_contents"]
        if item["object_name"] == "demo_sqlite"
    }
    assert str(db_file.resolve()) in restored_paths

    with sqlite3.connect(db_file) as connection:
        value = connection.execute(
            "SELECT value FROM settings WHERE name = ?",
            ("mode",),
        ).fetchone()
    assert value == ("baseline",)
