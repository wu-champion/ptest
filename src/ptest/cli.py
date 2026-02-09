#!/usr/bin/env python3
# ptest/cli.py
import argparse
import json
import os
import shlex
from pathlib import Path
from typing import Any

from . import __version__
from .objects.manager import ObjectManager
from .tools.manager import ToolManager
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

    obj_subparsers.add_parser("list", help="List all test objects")

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

    case_subparsers.add_parser("list", help="List all test cases")

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
    from .environment import EnvironmentManager

    parser = setup_cli()
    args = parser.parse_args()

    # 初始化环境管理器
    env_manager = EnvironmentManager()

    command_handlers = {
        "init": lambda: _handle_init_command(env_manager, args),
        "config": lambda: handle_config_command(env_manager, args),
        "obj": lambda: (
            _handle_entity_command(
                ObjectManager(),
                args,
                args.obj_action,
                "obj",
            )
            if hasattr(args, "obj_action") and args.obj_action
            else (
                print_colored(
                    "请指定操作: install/start/stop/restart/uninstall/list/status", 93
                )
                or False
            )
        ),
        "tool": lambda: (
            _handle_entity_command(
                ToolManager(),
                args,
                args.tool_action,
                "tool",
            )
            if hasattr(args, "tool_action") and args.tool_action
            else (
                print_colored(
                    "请指定操作: install/start/stop/restart/uninstall/list/status", 93
                )
                or False
            )
        ),
        "case": lambda: _handle_case_command(env_manager, args),
        "run": lambda: _handle_run_command(env_manager, args),
        "data": lambda: _handle_data_command(env_manager, args),
        "contract": lambda: _handle_contract_command(env_manager, args),
        "suite": lambda: _handle_suite_command(env_manager, args),
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


def _handle_case_command(env_manager, args) -> bool:
    """处理case命令"""
    from .cases.manager import CaseManager

    case_manager = CaseManager(env_manager)

    if not hasattr(args, "case_action") or not args.case_action:
        print_colored("请指定 case 操作: add/list/show/delete/run", 91)
        return False

    if args.case_action == "add":
        # 添加用例
        if hasattr(args, "case_data") and args.case_data:
            try:
                case_data = json.loads(args.case_data)
                case_manager.add_case(case_data)
                print_colored(f"✓ 用例已添加: {case_data.get('id', 'unknown')}", 92)
                return True
            except json.JSONDecodeError as e:
                print_colored(f"✗ 无效的 JSON: {e}", 91)
                return False
        else:
            print_colored("✗ 请提供用例数据 (--data)", 91)
            return False

    elif args.case_action == "list":
        # 列出所有用例
        cases = case_manager.list_cases()
        if cases:
            print_colored(f"共有 {len(cases)} 个用例:", 96)
            for case in cases:
                print(
                    f"  • {case.get('id', 'unknown')}: {case.get('description', '无描述')}"
                )
        else:
            print_colored("没有找到用例", 93)
        return True

    elif args.case_action == "show":
        # 显示用例详情
        if hasattr(args, "id") and args.id:
            case = case_manager.get_case(args.id)
            if case:
                print_colored(f"用例: {args.id}", 96)
                print(json.dumps(case, indent=2, ensure_ascii=False))
                return True
            else:
                print_colored(f"✗ 用例不存在: {args.id}", 91)
                return False
        else:
            print_colored("✗ 请提供用例 ID", 91)
            return False

    elif args.case_action == "delete":
        # 删除用例
        if hasattr(args, "id") and args.id:
            if case_manager.delete_case(args.id):
                print_colored(f"✓ 用例已删除: {args.id}", 92)
                return True
            else:
                print_colored(f"✗ 删除失败: {args.id}", 91)
                return False
        else:
            print_colored("✗ 请提供用例 ID", 91)
            return False

    elif args.case_action == "run":
        # 运行用例
        if hasattr(args, "id") and args.id:
            case = case_manager.get_case(args.id)
            if case:
                result = case_manager.run_case(case)
                status = "通过" if result.success else "失败"
                color = 92 if result.success else 91
                print_colored(
                    f"用例 {args.id}: {status} ({result.duration:.2f}s)", color
                )
                if not result.success and result.error:
                    print_colored(f"错误: {result.error}", 91)
                return result.success
            else:
                print_colored(f"✗ 用例不存在: {args.id}", 91)
                return False
        else:
            print_colored("✗ 请提供用例 ID", 91)
            return False

    else:
        print_colored(f"✗ 未知的 case 操作: {args.case_action}", 91)
        return False


def _handle_run_command(env_manager, args) -> bool:
    """处理run命令 - 运行所有或过滤后的用例"""
    from .cases.manager import CaseManager

    case_manager = CaseManager(env_manager)

    # 获取所有用例
    cases = case_manager.list_cases()

    # 如果有过滤条件，进行过滤
    if hasattr(args, "filter") and args.filter:
        cases = [c for c in cases if args.filter in str(c)]
        print_colored(f"过滤后: {len(cases)} 个用例", 94)

    if not cases:
        print_colored("没有要运行的用例", 93)
        return True

    print_colored(f"开始运行 {len(cases)} 个用例...", 96)

    passed = 0
    failed = 0

    for case in cases:
        result = case_manager.run_case(case)
        if result.success:
            passed += 1
            status_icon = "✓"
            color = 92
        else:
            failed += 1
            status_icon = "✗"
            color = 91

        print_colored(
            f"{status_icon} {case.get('id', 'unknown')}: {result.duration:.2f}s", color
        )

    print_colored(f"\n完成: {passed} 通过, {failed} 失败", 96 if failed == 0 else 91)
    return failed == 0


def _handle_status_command(env_manager, args) -> bool:
    """处理status命令 - 显示整体状态"""
    from .objects.manager import ObjectManager
    from .tools.manager import ToolManager
    from .cases.manager import CaseManager

    print_colored("=== ptest 状态 ===", 96)

    # 环境状态
    if env_manager.test_path:
        print(f"测试环境路径: {env_manager.test_path}")
        print(f"测试环境已初始化: ✓")
    else:
        print_colored("测试环境未初始化", 93)

    # 对象状态
    obj_manager = ObjectManager()
    print(f"\n测试对象:")
    # 显示对象数量

    # 工具状态
    tool_manager = ToolManager()
    print(f"\n测试工具:")
    # 显示工具数量

    # 用例状态
    case_manager = CaseManager(env_manager)
    cases = case_manager.list_cases()
    print(f"\n测试用例: {len(cases)} 个")

    return True
