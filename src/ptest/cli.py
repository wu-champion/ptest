#!/usr/bin/env python3
# ptest/cli.py
import argparse
import json
import os
from pathlib import Path

from . import __version__
from .environment import EnvironmentManager
from .objects.manager import ObjectManager
from .tools.manager import ToolManager
from .cases.manager import CaseManager
from .reports.generator import ReportGenerator
from .data.cli import setup_data_subparser, handle_data_command
from .contract.cli import setup_contract_subparser, handle_contract_command
from .suites.cli import setup_suite_subparser, handle_suite_command
from .utils import print_colored, get_colored_text


def setup_cli():
    """设置命令行界面"""
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

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init command - 高优先级
    init_parser = subparsers.add_parser(
        "init", help=get_colored_text("Initialize test environment", 92)
    )
    init_parser.add_argument("--path", required=True, help="Path for test environment")

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
        "obj", help=get_colored_text("Manage test objects", 92)
    )
    obj_subparsers = obj_parser.add_subparsers(dest="obj_action", help="Object actions")

    install_obj_parser = obj_subparsers.add_parser(
        "install", help="Install a test object"
    )
    install_obj_parser.add_argument(
        "type", choices=["mysql", "web", "service", "db"], help="Object type"
    )
    install_obj_parser.add_argument("name", help="Object name")
    install_obj_parser.add_argument(
        "--version", help="Version for specific object types like MySQL"
    )

    start_obj_parser = obj_subparsers.add_parser("start", help="Start a test object")
    start_obj_parser.add_argument("name", help="Object name")

    stop_obj_parser = obj_subparsers.add_parser("stop", help="Stop a test object")
    stop_obj_parser.add_argument("name", help="Object name")

    restart_obj_parser = obj_subparsers.add_parser(
        "restart", help="Restart a test object"
    )
    restart_obj_parser.add_argument("name", help="Object name")

    uninstall_obj_parser = obj_subparsers.add_parser(
        "uninstall", help="Uninstall a test object"
    )
    uninstall_obj_parser.add_argument("name", help="Object name")

    list_obj_parser = obj_subparsers.add_parser("list", help="List all test objects")

    status_obj_parser = obj_subparsers.add_parser(
        "status", help="Get test object status"
    )
    status_obj_parser.add_argument("name", help="Object name")

    case_parser = subparsers.add_parser(
        "case", help=get_colored_text("Test case management", 92)
    )
    case_subparsers = case_parser.add_subparsers(
        dest="case_action", help="Case actions"
    )

    add_case_parser = case_subparsers.add_parser("add", help="Add a test case")
    add_case_parser.add_argument("id", help="Test case ID")

    edit_case_parser = case_subparsers.add_parser("edit", help="Edit a test case")
    edit_case_parser.add_argument("id", help="Test case ID")

    delete_case_parser = case_subparsers.add_parser("delete", help="Delete a test case")
    delete_case_parser.add_argument("id", help="Test case ID")

    list_case_parser = case_subparsers.add_parser("list", help="List all test cases")

    show_case_parser = case_subparsers.add_parser("show", help="Show test case details")
    show_case_parser.add_argument("id", help="尝试添加：Test case ID")
    show_case_parser.add_argument(
        "--format",
        choices=["json", "yaml"],
        default="json",
        help="Output format (json/yaml)",
    )

    run_parser = subparsers.add_parser(
        "run", help=get_colored_text("Run test cases", 92)
    )
    run_parser.add_argument("--filter", help="Filter cases by tag")
    run_parser.add_argument(
        "--parallel", action="store_true", help="Enable parallel execution"
    )
    run_parser.add_argument(
        "--format",
        choices=["html", "json", "yaml"],
        default="html",
        help="Report format",
    )

    # suite commands
    setup_suite_subparser(subparsers)

    # report command - 高优先级
    report_parser = subparsers.add_parser(
        "report", help=get_colored_text("Test report", 92)
    )
    report_subparsers = report_parser.add_subparsers(
        dest="report_action", help="Report actions"
    )

    report_generate_parser = report_subparsers.add_parser(
        "generate", help="Generate test report"
    )
    report_generate_parser.add_argument("--from-cases", help="Generate from cases")
    report_generate_parser.add_argument(
        "--format",
        choices=["html", "json", "yaml"],
        default="html",
        help="Report format",
    )

    # data commands
    setup_data_subparser(subparsers)

    # contract commands
    setup_contract_subparser(subparsers)

    return parser


def handle_config_command(env_manager, args) -> bool:
    """处理config命令"""
    from .config import load_config, save_config, validate_config, generate_config

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
            print_colored(f"  Run 'ptest config init' to create one", 93)
            return False

        editor = args.editor or os.environ.get("EDITOR", "vim")
        print_colored(f"Opening {config_file} with {editor}...", 94)
        try:
            subprocess.call([editor, str(config_file)])
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
            print_colored(f"  Run 'ptest config init' to create one", 93)
            return False

        config = load_config(config_file)
        print_colored("Current configuration:", 96)
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return True

    return False


def _handle_init_command(env_manager, args) -> bool:
    """处理init命令"""
    result = env_manager.init_environment(args.path)
    print_colored(result, 92)
    return True


def _handle_entity_command(entity_manager, args, action: str, entity_type: str):
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
        "install": lambda: (
            entity_manager.install(
                args.name,
                {"version": args.version}
                if hasattr(args, "version") and args.version
                else {},
            )
            if hasattr(args, "version")
            else entity_manager.install(args.name)
        ),
        "start": lambda: entity_manager.start(args.name),
        "stop": lambda: entity_manager.stop(args.name),
        "restart": lambda: entity_manager.restart(args.name),
        "uninstall": lambda: entity_manager.uninstall(args.name),
        "list": lambda: (entity_manager.list_()),
        "status": lambda: (entity_manager.status(args.name)),
    }

    handler = action_map.get(action)
    if handler:
        return handler()
    else:
        print_colored(f"✗ Unknown {entity_type} action: {action}", 91)
        return False


def _handle_data_command(env_manager, args) -> bool:
    """处理data命令"""
    return handle_data_command(args)


def _handle_contract_command(env_manager, args) -> bool:
    """处理contract命令"""
    return handle_contract_command(args)


def _handle_suite_command(env_manager, args) -> bool:
    """处理suite命令"""
    return handle_suite_command(args)


def main():
    """主入口"""
    parser = setup_cli()
    args = parser.parse_args()

    command_handlers = {
        "init": lambda: _handle_init_command(env_manager, args),
        "config": lambda: _handle_config_command(env_manager, args),
        "obj": lambda: _handle_entity_command(ObjectManager(), args, "obj"),
        "tool": lambda: _handle_entity_command(ToolManager(), args, "tool"),
        "case": lambda: _handle_case_command(env_manager, args),
        "run": lambda: _handle_run_command(env_manager, args),
        "data": lambda: _handle_data_command(env_manager, args),
        "setup_contract": lambda: _handle_contract_command(env_manager, args),
        "data": lambda: handle_data_command(args),
        "contract": lambda: handle_contract_command(env_manager, args),
        "suite": lambda: handle_suite_command(env_manager, args),
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
