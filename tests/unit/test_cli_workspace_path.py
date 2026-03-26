from __future__ import annotations

import sys
from pathlib import Path

from ptest import cli
from ptest.app import WorkflowService


def test_cli_supports_global_workspace_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    args = cli.setup_cli().parse_args(["--path", str(workspace), "case", "list"])
    assert Path(args.path) == workspace


def test_cli_supports_workspace_path_after_subcommand(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    WorkflowService(workspace).init_environment()

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ptest", "case", "list", "--path", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "[]" in captured.out


def test_cli_reports_uninitialized_workspace_clearly(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "missing_workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ptest", "status", "--path", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Workspace is not initialized" in captured.out
    assert str(workspace.resolve()) in captured.out


def test_cli_data_template_uses_workspace_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    WorkflowService(workspace).init_environment()

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "data",
            "template",
            "save",
            "demo",
            '{"name":"{{name}}"}',
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Template 'demo' saved" in captured.out
    assert (workspace / ".ptest" / "data_templates" / "demo.json").exists()


def test_cli_execution_artifacts_use_workspace_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    service = WorkflowService(workspace)
    service.init_environment()
    service.add_case(
        "sqlite_smoke",
        {
            "type": "database",
            "db_type": "sqlite",
            "database": str(workspace / "sample.db"),
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    service.run_case("sqlite_smoke")
    execution_id = service.list_execution_records("sqlite_smoke")[0]["execution_id"]

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "execution",
            "artifacts",
            execution_id,
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert execution_id in captured.out
    assert "artifact_index.json" in captured.out
