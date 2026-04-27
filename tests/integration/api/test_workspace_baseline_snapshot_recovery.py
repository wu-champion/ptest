from __future__ import annotations

import shutil

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


def test_workspace_baseline_snapshot_restores_object_reference_directories(tmp_path) -> None:
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
        item["field"] for item in directory_restore["restored_paths"] if item["object_name"] == "mysql_service"
    }
    assert {"data_dir", "log_dir", "dump_dir"} <= restored_fields
    for directory in (data_dir, log_dir, dump_dir):
        assert directory.exists() is True
