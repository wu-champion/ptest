#!/usr/bin/env python3
# ptest/cli.py
from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import __version__
from .app import WorkflowService
from .data.cli import setup_data_subparser, handle_data_command
from .contract.cli import setup_contract_subparser, handle_contract_command
from .suites.cli import setup_suite_subparser, handle_suite_command
from .mock.cli import setup_mock_subparser, handle_mock_command
from .utils import print_colored, get_colored_text

if TYPE_CHECKING:
    from .cases.manager import CaseManager
    from .environment import EnvironmentManager


def setup_cli() -> argparse.ArgumentParser:
    """设置命令行界面"""
    workspace_parent = argparse.ArgumentParser(add_help=False)
    workspace_parent.add_argument(
        "--path", help="Workspace path", default=argparse.SUPPRESS
    )

    parser = argparse.ArgumentParser(
        prog="ptest",
        description=get_colored_text("ptest - A comprehensive testing framework", 95),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{get_colored_text("Examples:", 93)}
  ptest init --path ./my_test_env
  ptest obj install mysql my_mysql_db --version 9.9.9
  ptest obj start my_mysql_db
  ptest case add my_test_case '{{"type": "api", "endpoint": "/api/test"}}'
  ptest run all
  ptest obj status
        """,
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--path", help="Workspace path")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init command - 高优先级
    init_parser = subparsers.add_parser(
        "init", help=get_colored_text("Initialize test environment", 92)
    )
    init_parser.add_argument("--path", required=True, help="Path for test environment")

    env_parser = subparsers.add_parser(
        "env",
        help=get_colored_text("Environment lifecycle management", 92),
        parents=[workspace_parent],
    )
    env_subparsers = env_parser.add_subparsers(dest="env_action", help="Env actions")
    env_subparsers.add_parser(
        "status", help="Show environment status", parents=[workspace_parent]
    )
    env_subparsers.add_parser(
        "destroy", help="Destroy current environment state", parents=[workspace_parent]
    )

    # config command - 高优先级
    config_parser = subparsers.add_parser(
        "config", help=get_colored_text("Configuration management", 92)
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_action", help="Config actions"
    )

    config_init_parser = config_subparsers.add_parser(
        "init", help="Initialize configuration file"
    )
    config_init_parser.add_argument(
        "--template",
        choices=["minimal", "full", "api", "database"],
        default="minimal",
        help="Configuration template",
    )
    config_init_parser.add_argument(
        "--format",
        choices=["json", "yaml"],
        default="yaml",
        help="Configuration file format",
    )

    config_subparsers.add_parser("validate", help="Validate current configuration")

    config_edit_parser = config_subparsers.add_parser(
        "edit", help="Edit configuration file"
    )
    config_edit_parser.add_argument(
        "--editor", help="Editor to use (defaults to $EDITOR or 'vim')"
    )

    config_subparsers.add_parser("show", help="Show current configuration")

    # obj commands - 高优先级
    obj_parser = subparsers.add_parser(
        "obj",
        help=get_colored_text("Manage test objects", 92),
        parents=[workspace_parent],
    )
    obj_subparsers = obj_parser.add_subparsers(dest="obj_action", help="Object actions")

    install_obj_parser = obj_subparsers.add_parser(
        "install", help="Install a test object", parents=[workspace_parent]
    )
    install_obj_parser.add_argument(
        "type", choices=["mysql", "web", "service", "db"], help="Object type"
    )
    install_obj_parser.add_argument("name", help="Object name")
    install_obj_parser.add_argument(
        "--version", help="Version for specific object types like MySQL"
    )
    install_obj_parser.add_argument("--driver", help="Database driver")
    install_obj_parser.add_argument("--database", help="Database name or sqlite path")
    install_obj_parser.add_argument("--host", help="Database host")
    install_obj_parser.add_argument("--port", type=int, help="Database port")
    install_obj_parser.add_argument("--username", help="Database username")
    install_obj_parser.add_argument("--password", help="Database password")

    start_obj_parser = obj_subparsers.add_parser(
        "start", help="Start a test object", parents=[workspace_parent]
    )
    start_obj_parser.add_argument("name", help="Object name")

    stop_obj_parser = obj_subparsers.add_parser(
        "stop", help="Stop a test object", parents=[workspace_parent]
    )
    stop_obj_parser.add_argument("name", help="Object name")

    restart_obj_parser = obj_subparsers.add_parser(
        "restart", help="Restart a test object", parents=[workspace_parent]
    )
    restart_obj_parser.add_argument("name", help="Object name")

    uninstall_obj_parser = obj_subparsers.add_parser(
        "uninstall", help="Uninstall a test object", parents=[workspace_parent]
    )
    uninstall_obj_parser.add_argument("name", help="Object name")

    obj_subparsers.add_parser(
        "list", help="List all test objects", parents=[workspace_parent]
    )

    status_obj_parser = obj_subparsers.add_parser(
        "status", help="Get test object status", parents=[workspace_parent]
    )
    status_obj_parser.add_argument("name", help="Object name")

    tool_parser = subparsers.add_parser(
        "tool",
        help=get_colored_text("Manage test tools", 92),
        parents=[workspace_parent],
    )
    tool_subparsers = tool_parser.add_subparsers(
        dest="tool_action", help="Tool actions"
    )

    install_tool_parser = tool_subparsers.add_parser(
        "install", help="Install a tool", parents=[workspace_parent]
    )
    install_tool_parser.add_argument("name", help="Tool name")
    install_tool_parser.add_argument("--version", help="Tool version")

    start_tool_parser = tool_subparsers.add_parser(
        "start", help="Start a tool", parents=[workspace_parent]
    )
    start_tool_parser.add_argument("name", help="Tool name")

    stop_tool_parser = tool_subparsers.add_parser(
        "stop", help="Stop a tool", parents=[workspace_parent]
    )
    stop_tool_parser.add_argument("name", help="Tool name")

    restart_tool_parser = tool_subparsers.add_parser(
        "restart", help="Restart a tool", parents=[workspace_parent]
    )
    restart_tool_parser.add_argument("name", help="Tool name")

    uninstall_tool_parser = tool_subparsers.add_parser(
        "uninstall", help="Uninstall a tool", parents=[workspace_parent]
    )
    uninstall_tool_parser.add_argument("name", help="Tool name")

    tool_subparsers.add_parser(
        "list", help="List all tools", parents=[workspace_parent]
    )

    status_tool_parser = tool_subparsers.add_parser(
        "status", help="Get tool status", parents=[workspace_parent]
    )
    status_tool_parser.add_argument("name", help="Tool name")

    case_parser = subparsers.add_parser(
        "case",
        help=get_colored_text("Test case management", 92),
        parents=[workspace_parent],
    )
    case_subparsers = case_parser.add_subparsers(
        dest="case_action", help="Case actions"
    )

    add_case_parser = case_subparsers.add_parser(
        "add", help="Add a test case", parents=[workspace_parent]
    )
    add_case_parser.add_argument("id", help="Test case ID")
    add_case_parser.add_argument(
        "--data",
        dest="case_data",
        help="Case data as JSON string",
    )
    add_case_parser.add_argument(
        "--file",
        dest="case_file",
        help="Path to a JSON file containing case data",
    )

    edit_case_parser = case_subparsers.add_parser(
        "edit", help="Edit a test case", parents=[workspace_parent]
    )
    edit_case_parser.add_argument("id", help="Test case ID")

    delete_case_parser = case_subparsers.add_parser(
        "delete", help="Delete a test case", parents=[workspace_parent]
    )
    delete_case_parser.add_argument("id", help="Test case ID")

    case_subparsers.add_parser(
        "list", help="List all test cases", parents=[workspace_parent]
    )

    show_case_parser = case_subparsers.add_parser(
        "show", help="Show test case details", parents=[workspace_parent]
    )
    show_case_parser.add_argument("id", help="尝试添加：Test case ID")
    show_case_parser.add_argument(
        "--format",
        choices=["json", "yaml"],
        default="json",
        help="Output format (json/yaml)",
    )

    run_case_parser = case_subparsers.add_parser(
        "run", help="Run a test case", parents=[workspace_parent]
    )
    run_case_parser.add_argument("id", help="Test case ID")

    run_parser = subparsers.add_parser(
        "run", help=get_colored_text("Run test cases", 92), parents=[workspace_parent]
    )
    run_parser.add_argument("--filter", help="Filter cases by tag")
    run_parser.add_argument(
        "--parallel", action="store_true", help="Enable parallel execution"
    )
    run_parser.add_argument(
        "--workers", type=int, default=4, help="Number of parallel workers"
    )
    run_parser.add_argument(
        "--timeout", type=int, default=0, help="Case execution timeout in seconds"
    )
    run_parser.add_argument(
        "--format",
        choices=["html", "json", "yaml"],
        default="html",
        help="Report format",
    )

    execution_parser = subparsers.add_parser(
        "execution",
        help=get_colored_text("Execution records and artifacts", 92),
        parents=[workspace_parent],
    )
    execution_subparsers = execution_parser.add_subparsers(
        dest="execution_action",
        help="Execution actions",
    )
    execution_list_parser = execution_subparsers.add_parser(
        "list",
        help="List execution records",
        parents=[workspace_parent],
    )
    execution_list_parser.add_argument("--case-id", help="Filter by case ID")
    execution_show_parser = execution_subparsers.add_parser(
        "show",
        help="Show a single execution record",
        parents=[workspace_parent],
    )
    execution_show_parser.add_argument("execution_id", help="Execution ID")
    execution_artifacts_parser = execution_subparsers.add_parser(
        "artifacts",
        help="Show execution artifact index",
        parents=[workspace_parent],
    )
    execution_artifacts_parser.add_argument("execution_id", help="Execution ID")
    execution_artifacts_parser.add_argument(
        "--include-contents",
        action="store_true",
        help="Include artifact file contents",
    )

    # suite commands
    setup_suite_subparser(subparsers, parents=[workspace_parent])

    # report command - 高优先级
    report_parser = subparsers.add_parser(
        "report", help=get_colored_text("Test report", 92), parents=[workspace_parent]
    )
    report_subparsers = report_parser.add_subparsers(
        dest="report_action", help="Report actions"
    )

    report_generate_parser = report_subparsers.add_parser(
        "generate", help="Generate test report", parents=[workspace_parent]
    )
    report_generate_parser.add_argument("--from-cases", help="Generate from cases")
    report_generate_parser.add_argument(
        "--format",
        choices=["html", "json", "markdown"],
        default="html",
        help="Report format",
    )
    report_generate_parser.add_argument("--output", help="Custom report output path")

    subparsers.add_parser(
        "status",
        help=get_colored_text("Workspace status", 92),
        parents=[workspace_parent],
    )

    # data commands
    setup_data_subparser(subparsers, parents=[workspace_parent])

    # contract commands
    setup_contract_subparser(subparsers, parents=[workspace_parent])

    # mock commands
    setup_mock_subparser(subparsers, parents=[workspace_parent])

    return parser


def handle_config_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理config命令"""
    from .config import load_config, save_config, generate_config

    if not hasattr(args, "config_action") or not args.config_action:
        config_file = (
            env_manager.test_path / "ptest_config.yaml"
            if env_manager.test_path
            else Path("ptest_config.yaml")
        )
        if config_file.exists():
            env_manager.config = load_config(config_file)
            print_colored(f"✓ Configuration loaded from: {config_file}", 92)
            return True
        else:
            print_colored("✗ No configuration file found", 91)
            return False

    if args.config_action == "init":
        config_file = (
            env_manager.test_path / f"ptest_config.{args.format}"
            if env_manager.test_path
            else Path(f"ptest_config.{args.format}")
        )
        config = generate_config(args.template)
        save_config(config, config_file)
        print_colored(f"✓ Configuration file created: {config_file}", 92)
        return True

    elif args.config_action == "edit":
        import subprocess

        config_file = (
            env_manager.test_path / "ptest_config.yaml"
            if env_manager.test_path
            else Path("ptest_config.yaml")
        )
        if not config_file.exists():
            config_file = config_file.with_suffix(".json")

        if not config_file.exists():
            print_colored("✗ Configuration file not found", 91)
            print_colored("  Run 'ptest config init' to create one", 93)
            return False

        editor = args.editor or os.environ.get("EDITOR", "vim")
        print_colored(f"Opening {config_file} with {editor}...", 94)
        try:
            # 使用shlex.split处理编辑器命令，防止命令注入
            # Use shlex.split to handle editor command and prevent command injection
            editor_parts = shlex.split(editor)
            subprocess.call([*editor_parts, str(config_file)])
            print_colored("✓ Configuration edit complete", 92)
            return True
        except Exception as e:
            print_colored(f"✗ Failed to open editor: {e}", 91)
            return False

    elif args.config_action == "show":
        config_file = (
            env_manager.test_path / "ptest_config.yaml"
            if env_manager.test_path
            else Path("ptest_config.yaml")
        )
        if not config_file.exists():
            config_file = config_file.with_suffix(".json")

        if not config_file.exists():
            print_colored("✗ Configuration file not found", 91)
            print_colored("  Run 'ptest config init' to create one", 93)
            return False

        config = load_config(config_file)
        print_colored("Current configuration:", 96)
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return True

    return False


def _handle_init_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理init命令"""
    root_path = _resolve_workspace_path(args)
    service = WorkflowService(root_path)
    record = service.init_environment(root_path)
    print_colored(f"✓ Test environment initialized at: {record.root_path}", 92)
    return True


def _resolve_workspace_path(args: argparse.Namespace) -> Path:
    path = getattr(args, "path", None)
    return Path(path).resolve() if path else Path.cwd().resolve()


def _get_workflow_service(args: argparse.Namespace) -> WorkflowService:
    return WorkflowService(_resolve_workspace_path(args))


def _ensure_workspace_initialized(service: WorkflowService, command_label: str) -> bool:
    record = service.storage.load_environment()
    if record is None:
        print_colored(f"✗ Workspace is not initialized: {service.root_path}", 91)
        print_colored(
            f"  Run 'ptest init --path {service.root_path}' before using '{command_label}'",
            93,
        )
        return False
    if record.status == "destroyed":
        print_colored(f"✗ Workspace has been destroyed: {service.root_path}", 91)
        print_colored(
            f"  Re-initialize it with 'ptest init --path {service.root_path}'",
            93,
        )
        return False
    return True


def _handle_object_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理对象命令"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "obj"):
        return False

    if not hasattr(args, "obj_action") or not args.obj_action:
        print_colored(
            "请指定操作: install/start/stop/restart/uninstall/list/status", 93
        )
        return False

    if args.obj_action == "install":
        params = {}
        if hasattr(args, "version") and args.version:
            params["version"] = args.version
        for key in ("driver", "database", "host", "port", "username", "password"):
            value = getattr(args, key, None)
            if value is not None:
                params[key] = value
        if args.type in {"db", "database", "sqlite", "mysql", "postgres", "postgresql"}:
            params.setdefault(
                "driver", "sqlite" if args.type == "sqlite" else args.type
            )
            if params["driver"] == "db":
                params["driver"] = "sqlite"
        result = service.install_object(args.type, args.name, params)
        print_colored(result["message"], 92 if result["success"] else 91)
        return result["success"]

    if args.obj_action == "list":
        print(json.dumps(service.list_objects(), indent=2, ensure_ascii=False))
        return True

    action_handlers = {
        "start": service.start_object,
        "stop": service.stop_object,
        "restart": service.restart_object,
        "uninstall": service.uninstall_object,
        "status": service.get_object_status,
    }
    handler = action_handlers.get(args.obj_action)
    if handler is None:
        print_colored(f"✗ Unknown obj action: {args.obj_action}", 91)
        return False

    result = handler(args.name)
    if "message" in result:
        print_colored(result["message"], 92 if result.get("success") else 91)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    if "object" in result:
        print(json.dumps(result["object"], indent=2, ensure_ascii=False))
    return bool(result.get("success", True))


def _handle_tool_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理工具命令"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "tool"):
        return False

    if not hasattr(args, "tool_action") or not args.tool_action:
        print_colored(
            "请指定操作: install/start/stop/restart/uninstall/list/status", 93
        )
        return False

    if args.tool_action == "install":
        params = {}
        if hasattr(args, "version") and args.version:
            params["version"] = args.version
        result = service.install_tool(args.name, params)
        print_colored(result["message"], 92 if result["success"] else 91)
        return result["success"]

    if args.tool_action == "list":
        print(json.dumps(service.list_tools(), indent=2, ensure_ascii=False))
        return True

    action_handlers = {
        "start": service.start_tool,
        "stop": service.stop_tool,
        "restart": service.restart_tool,
        "uninstall": service.uninstall_tool,
        "status": service.get_tool_status,
    }
    handler = action_handlers.get(args.tool_action)
    if handler is None:
        print_colored(f"✗ Unknown tool action: {args.tool_action}", 91)
        return False

    result = handler(args.name)
    if "message" in result:
        print_colored(result["message"], 92 if result.get("success") else 91)
    if "tool" in result:
        print(json.dumps(result["tool"], indent=2, ensure_ascii=False))
    return bool(result.get("success", True))


def _handle_suite_command_v2(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """通过统一工作流服务处理 suite 命令"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "suite"):
        return False

    if not hasattr(args, "suite_action") or not args.suite_action:
        print_colored("请指定套件操作: create/list/show/delete/validate/run", 91)
        return False

    if args.suite_action == "create":
        suite_data: dict[str, Any]
        if getattr(args, "from_file", None):
            file_path = Path(args.from_file)
            if not file_path.exists():
                print_colored(f"✗ 文件不存在: {args.from_file}", 91)
                return False
            try:
                with open(file_path, "r", encoding="utf-8") as handle:
                    if file_path.suffix in [".yaml", ".yml"]:
                        try:
                            import yaml  # type: ignore[import-untyped]
                        except ImportError:
                            print_colored("✗ 需要安装 PyYAML: pip install pyyaml", 91)
                            return False
                        suite_data = yaml.safe_load(handle)
                    else:
                        suite_data = json.load(handle)
            except Exception as exc:
                print_colored(f"✗ 读取文件失败: {exc}", 91)
                return False
            suite_data["name"] = args.name
        else:
            suite_data = {
                "name": args.name,
                "description": None,
                "setup": [],
                "cases": [],
                "teardown": [],
                "execution_mode": "sequential",
                "max_workers": 4,
            }
        try:
            result = service.create_suite(suite_data)
            print(json.dumps(result["suite"], indent=2, ensure_ascii=False))
            return True
        except Exception as exc:
            print_colored(f"✗ 创建套件失败: {exc}", 91)
            return False

    if args.suite_action == "list":
        print(json.dumps(service.list_suites(), indent=2, ensure_ascii=False))
        return True

    if args.suite_action == "show":
        suite = service.get_suite(args.name)
        if suite is None:
            print_colored(f"✗ 套件不存在: {args.name}", 91)
            return False
        print(json.dumps(suite, indent=2, ensure_ascii=False))
        return True

    if args.suite_action == "delete":
        result = service.delete_suite(args.name)
        print_colored(result["message"], 92 if result["success"] else 91)
        return result["success"]

    if args.suite_action == "validate":
        result = service.validate_suite(args.name)
        if result["success"]:
            print_colored("✓ 套件配置有效", 92)
            return True
        if "message" in result:
            print_colored(result["message"], 91)
            return False
        print_colored("✗ 套件配置无效", 91)
        print(json.dumps(result["errors"], indent=2, ensure_ascii=False))
        return False

    if args.suite_action == "run":
        result = service.run_suite(
            name=args.name,
            parallel=getattr(args, "parallel", False),
            workers=getattr(args, "workers", 4),
            stop_on_failure=getattr(args, "stop_on_failure", False),
            timeout=getattr(args, "timeout", 0),
            retry_count=getattr(args, "retry_failed", 0),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return bool(result.get("success", False))

    print_colored(f"✗ 未知的 suite 操作: {args.suite_action}", 91)
    return False


def _handle_env_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理环境命令"""
    service = _get_workflow_service(args)
    if not hasattr(args, "env_action") or not args.env_action:
        print_colored("请指定 env 操作: status/destroy", 93)
        return False

    if args.env_action == "status":
        print(
            json.dumps(service.get_environment_status(), indent=2, ensure_ascii=False)
        )
        return True

    if args.env_action == "destroy":
        result = service.destroy_environment()
        print_colored(result["message"], 92 if result["success"] else 91)
        if result.get("cleanup_messages"):
            print(json.dumps(result["cleanup_messages"], indent=2, ensure_ascii=False))
        return result["success"]

    print_colored(f"✗ Unknown env action: {args.env_action}", 91)
    return False


def _handle_execution_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理 execution 命令"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "execution"):
        return False

    if not hasattr(args, "execution_action") or not args.execution_action:
        print_colored("请指定 execution 操作: list/show/artifacts", 93)
        return False

    if args.execution_action == "list":
        records = service.list_execution_records(case_id=getattr(args, "case_id", None))
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return True

    if args.execution_action == "show":
        result = service.get_execution_record(args.execution_id)
        if not result["success"]:
            print_colored(result["message"], 91)
            return False
        print(json.dumps(result["execution"], indent=2, ensure_ascii=False))
        return True

    if args.execution_action == "artifacts":
        result = service.get_execution_artifacts(
            args.execution_id,
            include_contents=getattr(args, "include_contents", False),
        )
        if not result["success"]:
            print_colored(result["message"], 91)
            return False
        print(json.dumps(result["artifacts"], indent=2, ensure_ascii=False))
        return True

    print_colored(f"✗ Unknown execution action: {args.execution_action}", 91)
    return False


def _handle_entity_command(
    entity_manager: Any,
    args: argparse.Namespace,
    action: str,
    entity_type: str,
) -> bool:
    """
    通用的实体命令处理器

    统一处理install/start/stop/restart/uninstall/list/status命令

    Args:
        entity_manager: 实体管理器（ObjectManager或ToolManager）
        args: 命令行参数
        action: 操作类型（obj_action或tool_action）
        entity_type: 实体类型名称（用于错误消息）
    """
    # 定义通用的操作映射
    action_map = {
        "install": lambda: _print_result(
            entity_manager.install(
                args.name,
                {"version": args.version}
                if hasattr(args, "version") and args.version
                else {},
            )
            if hasattr(args, "version")
            else entity_manager.install(args.name)
        ),
        "start": lambda: _print_result(entity_manager.start(args.name)),
        "stop": lambda: _print_result(entity_manager.stop(args.name)),
        "restart": lambda: _print_result(entity_manager.restart(args.name)),
        "uninstall": lambda: _print_result(entity_manager.uninstall(args.name)),
        "list": lambda: _print_result(
            entity_manager.list_objects()
            if hasattr(entity_manager, "list_objects")
            else entity_manager.list_all()
        ),
        "status": lambda: _print_result(entity_manager.status(args.name)),
    }

    handler = action_map.get(action)
    if handler:
        result = handler()
        # 确保返回布尔值表示成功/失败
        if isinstance(result, str):
            return "error" not in result.lower() and "failed" not in result.lower()
        return bool(result)
    else:
        print_colored(f"✗ Unknown {entity_type} action: {action}", 91)
        return False


def _print_result(result: Any) -> Any:
    """打印结果并返回"""
    if isinstance(result, str):
        print(result)
    elif isinstance(result, (list, dict)):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def _handle_data_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理data命令"""
    service = _get_workflow_service(args)

    if not hasattr(args, "data_action") or not args.data_action:
        print_colored("✗ Please specify a data action (generate/template/types)", 91)
        return False

    if args.data_action == "types":
        from .data.generator import DATA_TYPE_CATEGORIES

        print(json.dumps(DATA_TYPE_CATEGORIES, indent=2, ensure_ascii=False))
        return True

    if args.data_action == "generate":
        result = service.generate_data(
            args.type,
            count=args.count,
            locale=args.locale,
            format_type=args.format,
            table=getattr(args, "table", None),
            dialect=getattr(args, "dialect", "generic"),
            batch_size=getattr(args, "batch_size", 100),
            seed=getattr(args, "seed", None),
        )
        if not result["success"]:
            print_colored(result["message"], 91)
            return False
        payload = result["data"]["result"]
        if getattr(args, "output", None):
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(payload, str):
                output_path.write_text(payload, encoding="utf-8")
            else:
                output_path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            print_colored(f"✓ Data saved to: {output_path}", 92)
        else:
            print(
                payload
                if isinstance(payload, str)
                else json.dumps(payload, indent=2, ensure_ascii=False)
            )
        print_colored(result["message"], 92)
        return True

    if args.data_action == "template":
        if not _ensure_workspace_initialized(service, "data template"):
            return False
        if not hasattr(args, "template_action") or not args.template_action:
            print_colored("✗ Please specify a template action (generate/save/list)", 91)
            return False
        if args.template_action == "save":
            try:
                definition = (
                    json.loads(Path(args.definition).read_text(encoding="utf-8"))
                    if Path(args.definition).exists()
                    else json.loads(args.definition)
                )
            except Exception as exc:
                print_colored(f"✗ Invalid template definition: {exc}", 91)
                return False
            result = service.save_data_template(args.name, definition)
            print_colored(result["message"], 92 if result["success"] else 91)
            return result["success"]
        if args.template_action == "list":
            result = service.list_data_templates()
            print(json.dumps(result["data"], indent=2, ensure_ascii=False))
            return True
        if args.template_action == "generate":
            result = service.generate_data_from_template(args.name, count=args.count)
            if not result["success"]:
                print_colored(result["message"], 91)
                return False
            payload = result["data"]["results"]
            if getattr(args, "output", None):
                Path(args.output).write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print_colored(f"✓ Data saved to: {args.output}", 92)
            else:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            print_colored(result["message"], 92)
            return True

    return handle_data_command(args)


def _handle_contract_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理contract命令"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "contract"):
        return False
    if not hasattr(args, "contract_action") or not args.contract_action:
        print_colored("✗ Please specify a contract action", 91)
        return False

    if args.contract_action == "import":
        result = service.import_contract(args.source, getattr(args, "name", None))
        if not result["success"]:
            print_colored(result["message"], 91)
            return False
        contract = result["contract"]
        print_colored(result["message"], 92)
        print(json.dumps(contract, indent=2, ensure_ascii=False))
        return True
    if args.contract_action == "list":
        result = service.list_contracts()
        print(json.dumps(result["data"], indent=2, ensure_ascii=False))
        return True
    if args.contract_action == "show":
        result = service.get_contract(args.name)
        if not result["success"]:
            print_colored(result["message"], 91)
            return False
        print(json.dumps(result["contract"], indent=2, ensure_ascii=False))
        return True
    if args.contract_action == "delete":
        result = service.delete_contract(args.name)
        print_colored(result["message"], 92 if result["success"] else 91)
        return result["success"]
    if args.contract_action == "generate-cases":
        result = service.generate_cases_from_contract(args.name, persist=True)
        if not result["success"]:
            print_colored(result["message"], 91)
            return False
        if getattr(args, "output", None):
            output_dir = Path(args.output)
            output_dir.mkdir(parents=True, exist_ok=True)
            for case in result["data"]["cases"]:
                (output_dir / f"{case['id']}.json").write_text(
                    json.dumps(case, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            print_colored(f"✓ Cases written to: {output_dir}", 92)
        print_colored(result["message"], 92)
        return True
    if args.contract_action == "validate":
        try:
            response_body = json.loads(Path(args.response).read_text(encoding="utf-8"))
        except Exception as exc:
            print_colored(f"✗ Failed to load response file: {exc}", 91)
            return False
        result = service.validate_contract_response(
            args.name,
            args.endpoint,
            args.method,
            args.status,
            response_body,
        )
        if result["success"]:
            print_colored(result["message"], 92)
            return True
        print_colored(result["message"], 91)
        print(json.dumps(result["data"]["errors"], indent=2, ensure_ascii=False))
        return False

    return handle_contract_command(args)


def _handle_mock_command_v2(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理 mock 命令"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "mock"):
        return False
    if not hasattr(args, "mock_action") or not args.mock_action:
        print_colored(
            "Please specify a mock action (start/stop/status/logs/list/add-route)", 91
        )
        return False

    if args.mock_action == "start":
        result = service.start_mock_server(
            args.name,
            port=args.port,
            blocking=getattr(args, "blocking", False),
        )
        print_colored(result["message"], 92 if result["success"] else 91)
        return result["success"]
    if args.mock_action == "stop":
        result = service.stop_mock_server(args.name)
        print_colored(result["message"], 92 if result["success"] else 91)
        return result["success"]
    if args.mock_action == "status":
        result = service.get_mock_server_status(args.name)
        if not result["success"]:
            print_colored(result["message"], 91)
            return False
        print(json.dumps(result["data"], indent=2, ensure_ascii=False))
        return True
    if args.mock_action == "logs":
        result = service.get_mock_logs(args.name, limit=args.limit)
        if not result["success"]:
            print_colored(result["message"], 91)
            return False
        print(json.dumps(result["data"], indent=2, ensure_ascii=False))
        return True
    if args.mock_action == "list":
        result = service.list_mock_servers()
        print(json.dumps(result["data"], indent=2, ensure_ascii=False))
        return True
    if args.mock_action == "add-route":
        try:
            response = json.loads(args.response)
            when = json.loads(args.when) if getattr(args, "when", None) else None
        except json.JSONDecodeError as exc:
            print_colored(f"✗ Invalid JSON: {exc}", 91)
            return False
        result = service.add_mock_route(
            args.name, args.path, args.method, response, when
        )
        print_colored(result["message"], 92 if result["success"] else 91)
        return result["success"]

    return handle_mock_command(args)


def _handle_suite_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理suite命令"""
    return handle_suite_command(env_manager, args)


def main() -> int:
    """主入口"""
    from .environment import EnvironmentManager

    parser = setup_cli()
    args = parser.parse_args()

    # 初始化环境管理器
    env_manager = EnvironmentManager()

    command_handlers = {
        "init": lambda: _handle_init_command(env_manager, args),
        "env": lambda: _handle_env_command(env_manager, args),
        "execution": lambda: _handle_execution_command(env_manager, args),
        "config": lambda: handle_config_command(env_manager, args),
        "obj": lambda: _handle_object_command(env_manager, args),
        "tool": lambda: _handle_tool_command(env_manager, args),
        "case": lambda: _handle_case_command(env_manager, args),
        "run": lambda: _handle_run_command(env_manager, args),
        "report": lambda: _handle_report_command(env_manager, args),
        "data": lambda: _handle_data_command(env_manager, args),
        "contract": lambda: _handle_contract_command(env_manager, args),
        "suite": lambda: _handle_suite_command_v2(env_manager, args),
        "mock": lambda: _handle_mock_command_v2(env_manager, args),
        "status": lambda: _handle_status_command(env_manager, args),
    }

    handler = command_handlers.get(args.command)
    if handler:
        result = handler()
        # 确保返回整数退出码 / Ensure integer exit code
        if isinstance(result, bool):
            return 0 if result else 1
        return result if isinstance(result, int) else 0
    else:
        print_colored(f"✗ Unknown command: {args.command}", 91)
        return 1


def _handle_case_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理case命令"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "case"):
        return False

    if not hasattr(args, "case_action") or not args.case_action:
        print_colored("请指定 case 操作: add/list/show/delete/run", 91)
        return False

    if args.case_action == "add":
        if getattr(args, "case_file", None):
            try:
                with open(args.case_file, "r", encoding="utf-8") as handle:
                    case_data = json.load(handle)
            except Exception as exc:
                print_colored(f"✗ 无法读取用例文件: {exc}", 91)
                return False
        elif getattr(args, "case_data", None):
            try:
                case_data = json.loads(args.case_data)
            except json.JSONDecodeError as e:
                print_colored(f"✗ 无效的 JSON: {e}", 91)
                return False
        else:
            print_colored("✗ 请通过 --data 或 --file 提供用例数据", 91)
            return False

        result = service.add_case(args.id, case_data)
        print_colored(result["message"], 92 if result["success"] else 91)
        return result["success"]

    elif args.case_action == "list":
        print(json.dumps(service.list_cases(), indent=2, ensure_ascii=False))
        return True

    elif args.case_action == "show":
        if hasattr(args, "id") and args.id:
            case = service.get_case(args.id)
            if case:
                print(json.dumps(case, indent=2, ensure_ascii=False))
                return True
            else:
                print_colored(f"✗ 用例不存在: {args.id}", 91)
                return False
        else:
            print_colored("✗ 请提供用例 ID", 91)
            return False

    elif args.case_action == "delete":
        if hasattr(args, "id") and args.id:
            result = service.delete_case(args.id)
            print_colored(result["message"], 92 if result["success"] else 91)
            return result["success"]
        else:
            print_colored("✗ 请提供用例 ID", 91)
            return False

    elif args.case_action == "run":
        if hasattr(args, "id") and args.id:
            result = service.run_case(args.id)
            color = 92 if result["success"] else 91
            print_colored(
                f"用例 {args.id}: {result['status']} ({result['duration']:.2f}s)", color
            )
            if result["error"]:
                print_colored(f"错误: {result['error']}", 91)
            return result["success"]
        else:
            print_colored("✗ 请提供用例 ID", 91)
            return False

    else:
        print_colored(f"✗ 未知的 case 操作: {args.case_action}", 91)
        return False


def _handle_run_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理run命令 - 运行所有或过滤后的用例"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "run"):
        return False
    result = service.run_all_cases(
        filter_text=getattr(args, "filter", None),
        parallel=getattr(args, "parallel", False),
        workers=getattr(args, "workers", 4),
        timeout=getattr(args, "timeout", 0),
    )

    if result["total"] == 0:
        print_colored("没有要运行的用例", 93)
        return True

    for item in result["results"]:
        color = 92 if item["success"] else 91
        icon = "✓" if item["success"] else "✗"
        print_colored(f"{icon} {item['case_id']}: {item['duration']:.2f}s", color)

    summary_color = 96 if result["failed"] == 0 else 91
    print_colored(
        f"\n完成: {result['passed']} 通过, {result['failed']} 失败",
        summary_color,
    )
    return result["success"]


def _handle_report_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理report命令"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "report"):
        return False
    if not hasattr(args, "report_action") or args.report_action != "generate":
        print_colored("✗ 目前仅支持 report generate", 91)
        return False

    try:
        report_path = service.generate_report(
            args.format, getattr(args, "output", None)
        )
        print_colored(f"✓ Report generated: {report_path}", 92)
        return True
    except Exception as exc:
        print_colored(f"✗ Report generation failed: {exc}", 91)
        return False


def _run_sequential(
    case_manager: CaseManager, case_ids: list[str], timeout: int
) -> bool:
    """串行执行用例"""
    from .execution import SequentialExecutor, ExecutionTask

    passed = 0
    failed = 0

    # 创建执行器
    executor = SequentialExecutor(stop_on_failure=False, timeout=timeout)

    # 创建任务
    tasks = []
    for case_id in case_ids:

        def run_case_task(case_id: str = case_id) -> Any:
            result = case_manager.run_case(case_id)
            return result

        task = ExecutionTask(task_id=case_id, func=run_case_task)
        tasks.append(task)

    # 执行
    results = executor.execute(tasks)

    for result in results:
        if result.success:
            passed += 1
            status_icon = "✓"
            color = 92
        else:
            failed += 1
            status_icon = "✗"
            color = 91

        print_colored(f"{status_icon} {result.task_id}: {result.duration:.2f}s", color)

    print_colored(f"\n完成: {passed} 通过, {failed} 失败", 96 if failed == 0 else 91)
    return failed == 0


def _run_parallel(
    case_manager: CaseManager,
    case_ids: list[str],
    max_workers: int,
    timeout: int,
) -> bool:
    """并行执行用例"""
    from .execution import ParallelExecutor, ExecutionTask

    passed = 0
    failed = 0

    # 创建执行器
    executor = ParallelExecutor(max_workers=max_workers)

    # 创建任务
    tasks = []
    for case_id in case_ids:

        def run_case_task(case_id: str = case_id) -> Any:
            result = case_manager.run_case(case_id)
            return result

        task = ExecutionTask(task_id=case_id, func=run_case_task, timeout=timeout)
        tasks.append(task)

    # 执行
    results = executor.execute(tasks)

    for result in results:
        if result.success:
            passed += 1
            status_icon = "✓"
            color = 92
        else:
            failed += 1
            status_icon = "✗"
            color = 91

        print_colored(f"{status_icon} {result.task_id}: {result.duration:.2f}s", color)

    executor.shutdown()

    print_colored(f"\n完成: {passed} 通过, {failed} 失败", 96 if failed == 0 else 91)
    return failed == 0


def _handle_status_command(
    env_manager: EnvironmentManager, args: argparse.Namespace
) -> bool:
    """处理status命令 - 显示整体状态"""
    service = _get_workflow_service(args)
    if not _ensure_workspace_initialized(service, "status"):
        return False
    print(json.dumps(service.get_workspace_status(), indent=2, ensure_ascii=False))
    return True
