from __future__ import annotations

import sqlite3
from pathlib import Path

from ptest.api import PTestAPI


def _prepare_orders_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE orders (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                owner TEXT NOT NULL
            )
            """
        )
        cursor.executemany(
            "INSERT INTO orders (id, state, owner) VALUES (?, ?, ?)",
            [
                ("ORD-100", "pending", "alice"),
                ("ORD-200", "ready", "bob"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_data_state_value_mismatch_exposes_recovery_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "orders.db"
    _prepare_orders_db(db_path)

    api = PTestAPI(work_path=tmp_path / "workspace_value_mismatch")
    api.init_environment()
    created = api.create_test_case(
        "database",
        "sqlite_state_mismatch",
        content={
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT id, state FROM orders WHERE id = 'ORD-100'",
            "expected_result": [{"id": "ORD-100", "state": "ready"}],
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
    assert assets["assets"]["details"]["failure_kind"] == "value_mismatch"
    assert assets["assets"]["details"]["actual_result"] == [
        {"id": "ORD-100", "state": "pending"}
    ]
    assert assets["assets"]["investigation"]["failure_kind"] == "value_mismatch"
    assert assets["assets"]["investigation"]["state_hints"]["mismatched_fields"] == [
        "state"
    ]

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["failure_kind"] == "value_mismatch"
    assert recovery["recovery"]["data_source"]["db_type"] == "sqlite"
    assert recovery["recovery"]["state_hints"]["mismatched_fields"] == ["state"]
    assert recovery["recovery"]["suggested_repairs"][0]["action"] == (
        "align_key_field_values"
    )
    assert recovery["recovery"]["next_actions"][1]["action"] == (
        "rerun_preserved_query_manually"
    )

    detail = api.get_problem_record(problem_id)
    assert detail["success"] is True
    assert detail["problem"]["investigation"]["data_source"]["db_type"] == "sqlite"
    assert detail["problem"]["investigation"]["failure_kind"] == "value_mismatch"


def test_data_state_missing_rows_exposes_minimal_repair_hints(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orders.db"
    _prepare_orders_db(db_path)

    api = PTestAPI(work_path=tmp_path / "workspace_missing_rows")
    api.init_environment()
    created = api.create_test_case(
        "database",
        "sqlite_missing_order",
        content={
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT id, state FROM orders WHERE id = 'ORD-404'",
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
    assert assets["assets"]["details"]["state_hints"]["missing_row_count"] == 1
    assert assets["assets"]["investigation"]["failure_kind"] == "missing_rows"

    recovery = api.recover_problem(problem_id)
    assert recovery["success"] is True
    assert recovery["recovery"]["failure_kind"] == "missing_rows"
    assert recovery["recovery"]["state_hints"]["missing_row_count"] == 1
    assert recovery["recovery"]["suggested_repairs"][0]["action"] == (
        "insert_minimal_required_rows"
    )
    assert recovery["recovery"]["next_actions"][2]["action"] == "restore_missing_rows"
