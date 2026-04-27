from __future__ import annotations

from ptest.api import PTestAPI
from ptest.models import ManagedObjectRecord, OBJECT_STATUS_START_FAILED_PRESERVED


def test_workspace_recovery_exposes_minimum_baseline_plan_for_runtime_problem(
    tmp_path,
) -> None:
    api = PTestAPI(work_path=tmp_path / "workspace_recovery_runtime")
    api.init_environment()
    baseline = api.create_workspace_baseline("runtime baseline")
    assert baseline["success"] is True
    api.workflow.storage.upsert_object(
        ManagedObjectRecord(
            name="demo_runtime_service",
            type_name="service",
            status=OBJECT_STATUS_START_FAILED_PRESERVED,
            installed=True,
            config={"runtime_backend": "managed"},
            metadata={"failure_state": {"phase": "start"}},
        )
    )
    created = api.create_test_case(
        "service",
        "workspace_recovery_start_failed_check",
        content={
            "service_name": "demo_runtime_service",
            "check_type": "port",
            "host": "127.0.0.1",
            "port": 45678,
            "timeout": 1,
        },
    )
    case_id = created["data"]["case_id"]

    run_result = api.run_test_case(case_id)
    assert run_result["success"] is False

    problems = api.list_problem_records(case_id=case_id, problem_type="service_runtime")
    assert problems["count"] == 1
    problem_id = problems["data"][0]["problem_id"]

    detail = api.get_problem_record(problem_id)
    assert detail["success"] is True
    investigation = detail["problem"]["investigation"]
    assert investigation["workspace_recovery"]["scope"] == "workspace_minimum_recovery"
    assert investigation["workspace_recovery"]["affected_objects"][0]["object_name"] == (
        "demo_runtime_service"
    )
    assert (
        investigation["workspace_recovery"]["affected_objects"][0][
            "recommended_action"
        ]
        == "reinstall"
    )

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    workspace_recovery = recovery["recovery"]["workspace_recovery"]
    assert workspace_recovery["scope"] == "workspace_minimum_recovery"
    assert workspace_recovery["affected_objects"][0]["object_name"] == (
        "demo_runtime_service"
    )
    assert workspace_recovery["affected_objects"][0]["recommended_action"] == (
        "reinstall"
    )
    assert workspace_recovery["recovery_boundary"]["scope"] == (
        "workspace_minimum_recovery"
    )
    assert workspace_recovery["baseline_restore"]["available"] is True
    assert (
        workspace_recovery["baseline_restore"]["latest_baseline"]["baseline_id"]
        == baseline["data"]["baseline_id"]
    )
    assert workspace_recovery["post_recovery_checks"][0]["action"] == (
        "verify_recovered_object_state"
    )
