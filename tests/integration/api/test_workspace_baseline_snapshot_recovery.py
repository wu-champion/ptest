from __future__ import annotations

from ptest.api import PTestAPI
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
