from __future__ import annotations

import sys
from pathlib import Path

from ptest import cli
from ptest.app import WorkflowService
from ptest.storage import LocalCliStateStorage


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
    assert "Workspace is not available" in captured.out
    assert "path does not exist" in captured.out
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


def test_cli_mysql_install_accepts_dependency_assets(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    dependency_a = tmp_path / "deps" / "libaio.so.1t64"
    dependency_b = tmp_path / "deps" / "libnuma.so.1"

    args = cli.setup_cli().parse_args(
        [
            "obj",
            "install",
            "mysql",
            "mysql_service",
            "--package-path",
            str(tmp_path / "mysql.tar.xz"),
            "--dependency-asset",
            str(dependency_a),
            "--dependency-asset",
            str(dependency_b),
            "--path",
            str(workspace),
        ]
    )

    assert args.package_path.endswith("mysql.tar.xz")
    assert args.dependency_assets == [str(dependency_a), str(dependency_b)]
    assert Path(args.path) == workspace


def test_cli_mysql_install_forwards_dependency_assets(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = tmp_path / "workspace"
    WorkflowService(workspace).init_environment()
    package_path = tmp_path / "assets" / "mysql.tar.xz"
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_text("fake-package", encoding="utf-8")
    dependency_path = tmp_path / "deps" / "libaio.so.1t64"
    dependency_path.parent.mkdir(parents=True, exist_ok=True)
    dependency_path.write_text("fake-lib", encoding="utf-8")

    captured_params: dict[str, object] = {}

    def fake_install_object(
        self: WorkflowService,
        obj_type: str,
        name: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        captured_params["obj_type"] = obj_type
        captured_params["name"] = name
        captured_params["params"] = params or {}
        return {
            "success": True,
            "message": "installed",
        }

    monkeypatch.setattr(WorkflowService, "install_object", fake_install_object)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ptest",
            "obj",
            "install",
            "mysql",
            "mysql_service",
            "--package-path",
            str(package_path),
            "--dependency-asset",
            str(dependency_path),
            "--path",
            str(workspace),
        ],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "installed" in captured.out
    assert captured_params["obj_type"] == "mysql"
    assert captured_params["name"] == "mysql_service"
    assert captured_params["params"] == {
        "mysql_package_path": str(package_path),
        "dependency_assets": [{"path": str(dependency_path)}],
        "workspace_path": str(workspace.resolve()),
        "driver": "mysql",
    }


def test_cli_uses_active_workspace_for_case_commands(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    WorkflowService(workspace).init_environment()
    LocalCliStateStorage().set_active_workspace(workspace)

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(sys, "argv", ["ptest", "case", "list"])

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Using active workspace" in captured.out
    assert str(workspace.resolve()) in captured.out
    assert "[]" in captured.out


def test_cli_explicit_path_overrides_active_workspace(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    active_workspace = tmp_path / "active"
    explicit_workspace = tmp_path / "explicit"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    WorkflowService(active_workspace).init_environment()
    WorkflowService(explicit_workspace).init_environment()
    LocalCliStateStorage().set_active_workspace(active_workspace)

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ptest", "case", "list", "--path", str(explicit_workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Using active workspace" not in captured.out
    assert "[]" in captured.out


def test_cli_init_sets_active_workspace(tmp_path: Path, monkeypatch, capsys) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        sys,
        "argv",
        ["ptest", "init", "--path", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Active workspace set to" in captured.out
    assert LocalCliStateStorage().get_active_workspace() == workspace.resolve()


def test_cli_workspace_use_rejects_destroyed_workspace(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    workspace = tmp_path / "workspace"
    service = WorkflowService(workspace)
    service.init_environment()
    service.destroy_environment()

    monkeypatch.setattr(
        sys,
        "argv",
        ["ptest", "workspace", "use", str(workspace)],
    )

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Workspace is not available" in captured.out
    assert "workspace has been destroyed" in captured.out


def test_cli_destroyed_current_workspace_does_not_fallback_to_active(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    active_workspace = tmp_path / "active"
    destroyed_workspace = tmp_path / "destroyed"
    WorkflowService(active_workspace).init_environment()
    destroyed_service = WorkflowService(destroyed_workspace)
    destroyed_service.init_environment()
    destroyed_service.destroy_environment()
    LocalCliStateStorage().set_active_workspace(active_workspace)

    monkeypatch.chdir(destroyed_workspace)
    monkeypatch.setattr(sys, "argv", ["ptest", "status"])

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Workspace is not available" in captured.out
    assert str(destroyed_workspace.resolve()) in captured.out
    assert "workspace has been destroyed" in captured.out
    assert "Using active workspace" not in captured.out


def test_cli_env_destroy_does_not_use_active_workspace(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    service = WorkflowService(workspace)
    service.init_environment()
    LocalCliStateStorage().set_active_workspace(workspace)

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(sys, "argv", ["ptest", "env", "destroy"])

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "No workspace resolved" in captured.out
    assert service.get_environment_status()["initialized"] is True


def test_cli_workspace_status_reports_active_workspace(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    workspace = tmp_path / "workspace"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    WorkflowService(workspace).init_environment()
    LocalCliStateStorage().set_active_workspace(workspace)

    monkeypatch.chdir(other_dir)
    monkeypatch.setattr(sys, "argv", ["ptest", "workspace", "status"])

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Active workspace" in captured.out
    assert str(workspace.resolve()) in captured.out
    assert "Default resolution" in captured.out
    assert "active workspace" in captured.out


def test_cli_exec_alias_matches_execution_command(
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
            "exec",
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
