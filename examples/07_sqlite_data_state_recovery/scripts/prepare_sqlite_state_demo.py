#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def _write_database(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()

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


def _case_payloads(db_path: Path) -> dict[str, dict[str, object]]:
    return {
        "01_order_state_mismatch.json": {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT id, state FROM orders WHERE id = 'ORD-100'",
            "expected_result": [{"id": "ORD-100", "state": "ready"}],
        },
        "02_missing_order.json": {
            "type": "database",
            "db_type": "sqlite",
            "database": str(db_path),
            "query": "SELECT id, state FROM orders WHERE id = 'ORD-404'",
            "expected_result": [{"id": "ORD-404", "state": "ready"}],
        },
    }


def _write_cases(cases_dir: Path, db_path: Path) -> None:
    cases_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in _case_payloads(db_path).items():
        (cases_dir / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the SQLite data_state recovery demo assets"
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="Workspace path used by the demo",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    db_path = workspace / "orders.db"
    cases_dir = workspace / "generated_cases"

    _write_database(db_path)
    _write_cases(cases_dir, db_path)

    summary = {
        "workspace": str(workspace),
        "database": str(db_path),
        "cases_dir": str(cases_dir),
        "cases": sorted(path.name for path in cases_dir.glob("*.json")),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
