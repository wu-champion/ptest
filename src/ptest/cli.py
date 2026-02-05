# ptest/cli.py
import argparse

from . import __version__
from .environment import EnvironmentManager
from .objects.manager import ObjectManager
from .tools.manager import ToolManager
from .cases.manager import CaseManager
from .reports.generator import ReportGenerator
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
    config_parser.add_argument("--file", help="Configuration file path")

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

    status_obj_parser = obj_subparsers.add_parser("status", help="Show object status")
    list_obj_parser = obj_subparsers.add_parser("list", help="List all objects")

    # tool commands - 中优先级
    tool_parser = subparsers.add_parser(
        "tool", help=get_colored_text("Manage tools", 93)
    )
    tool_subparsers = tool_parser.add_subparsers(
        dest="tool_action", help="Tool actions"
    )

    install_tool_parser = tool_subparsers.add_parser("install", help="Install a tool")
    install_tool_parser.add_argument("name", help="Tool name")

    start_tool_parser = tool_subparsers.add_parser("start", help="Start a tool")
    start_tool_parser.add_argument("name", help="Tool name")

    stop_tool_parser = tool_subparsers.add_parser("stop", help="Stop a tool")
    stop_tool_parser.add_argument("name", help="Tool name")

    uninstall_tool_parser = tool_subparsers.add_parser(
        "uninstall", help="Uninstall a tool"
    )
    uninstall_tool_parser.add_argument("name", help="Tool name")

    status_tool_parser = tool_subparsers.add_parser("status", help="Show tool status")
    list_tool_parser = tool_subparsers.add_parser("list", help="List all tools")

    # case commands - 中优先级
    case_parser = subparsers.add_parser(
        "case", help=get_colored_text("Manage test cases", 93)
    )
    case_subparsers = case_parser.add_subparsers(
        dest="case_action", help="Case actions"
    )

    add_case_parser = case_subparsers.add_parser("add", help="Add a test case")
    add_case_parser.add_argument("id", help="Test case ID")
    add_case_parser.add_argument("data", help="Test case data (JSON string)")

    remove_case_parser = case_subparsers.add_parser("remove", help="Remove a test case")
    remove_case_parser.add_argument("id", help="Test case ID")

    list_cases_parser = case_subparsers.add_parser("list", help="List all test cases")

    run_case_parser = case_subparsers.add_parser("run", help="Run test cases")
    run_case_parser.add_argument(
        "id", nargs="?", default="all", help='Test case ID or "all"'
    )

    # run command - 高优先级
    run_parser = subparsers.add_parser("run", help=get_colored_text("Run tests", 92))
    run_parser.add_argument(
        "type",
        choices=["all", "failed"],
        default="all",
        nargs="?",
        help="Type of tests to run",
    )

    # report command - 低优先级
    report_parser = subparsers.add_parser(
        "report", help=get_colored_text("Generate test reports", 96)
    )
    report_parser.add_argument(
        "--format", choices=["html", "json"], default="html", help="Report format"
    )

    # status command - 高优先级
    status_parser = subparsers.add_parser(
        "status", help=get_colored_text("Show overall status", 92)
    )

    return parser


def _handle_init_command(env_manager, args):
    """处理init命令"""
    result = env_manager.init_environment(args.path)
    print_colored(result, 92)


def _handle_config_command(env_manager, args):
    """处理config命令"""
    from .config import load_config

    config_file = (
        env_manager.test_path / "ptest_config.json"
        if env_manager.test_path
        else args.file
    )
    if config_file:
        env_manager.config = load_config(config_file)
        print_colored(f"✓ Configuration loaded from: {config_file}", 92)
    else:
        print_colored("✗ No configuration file specified", 91)


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
        "list": lambda: (
            entity_manager.list_tools()
            if entity_type == "tool"
            else entity_manager.list_objects()
        ),
        "status": lambda: (
            entity_manager.list_tools()
            if entity_type == "tool"
            else entity_manager.list_objects()
        ),
    }

    action_func = action_map.get(action)
    if action_func:
        result = action_func()
        print(result if isinstance(result, str) else str(result))
    else:
        print_colored(f"✗ Unknown {entity_type} action: {action}", 91)


def _handle_obj_command(obj_manager, args):
    """处理obj命令 - 使用通用处理器"""
    _handle_entity_command(obj_manager, args, args.obj_action, "object")


def _handle_tool_command(tool_manager, args):
    """处理tool命令 - 使用通用处理器"""
    _handle_entity_command(tool_manager, args, args.tool_action, "tool")


def _format_test_result(result) -> str:
    """格式化测试结果为可读字符串"""
    if hasattr(result, "status"):
        if result.status == "passed":
            return f"✓ Test case '{result.case_id}' {get_colored_text('PASSED', 92)} ({result.duration:.2f}s)"
        elif result.status == "failed":
            return f"✗ Test case '{result.case_id}' {get_colored_text('FAILED', 91)} ({result.duration:.2f}s): {result.error_message}"
        else:
            return f"✗ Test case '{result.case_id}' {get_colored_text('ERROR', 93)} ({result.duration:.2f}s): {result.error_message}"
    return str(result)


def _handle_case_command(case_manager, args):
    """处理case命令"""
    if args.case_action == "add":
        import json

        try:
            data = json.loads(args.data)
        except json.JSONDecodeError:
            print_colored("✗ Invalid JSON format for test case data", 91)
            return
        print(case_manager.add_case(args.id, data))
    elif args.case_action == "remove":
        print(case_manager.remove_case(args.id))
    elif args.case_action == "list":
        print(case_manager.list_cases())
    elif args.case_action == "run":
        if args.id == "all":
            print(case_manager.run_all_cases())
        else:
            result = case_manager.run_case(args.id)
            print(_format_test_result(result))


def _handle_run_command(case_manager, args):
    """处理run命令"""
    if args.type == "all":
        print(case_manager.run_all_cases())
    elif args.type == "failed":
        print(case_manager.run_failed_cases())


def _handle_report_command(env_manager, case_manager, args):
    """处理report命令"""
    report_gen = ReportGenerator(env_manager, case_manager)
    report_path = report_gen.generate_report(args.format)
    print_colored(f"✓ Report generated: {report_path}", 92)


def _handle_status_command(env_manager):
    """处理status命令"""
    status = env_manager.get_env_status()
    print_colored("=== ptest Framework Status ===", 95)
    if isinstance(status, str):
        print_colored(status, 91)
    else:
        print(f"Test Environment: {status['path']}")
        print(f"{get_colored_text('Objects:', 92)} {status['objects']} managed")
        print(f"{get_colored_text('Tools:', 93)} {status['tools']} managed")
        print(f"{get_colored_text('Test Cases:', 94)} {status['cases']} registered")
        print(f"{get_colored_text('Reports:', 96)} {status['reports']} generated")


def main():
    """主入口函数"""
    parser = setup_cli()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    env_manager = EnvironmentManager()
    obj_manager = ObjectManager(env_manager)
    tool_manager = ToolManager(env_manager)
    case_manager = CaseManager(env_manager)

    command_handlers = {
        "init": lambda: _handle_init_command(env_manager, args),
        "config": lambda: _handle_config_command(env_manager, args),
        "obj": lambda: _handle_obj_command(obj_manager, args),
        "tool": lambda: _handle_tool_command(tool_manager, args),
        "case": lambda: _handle_case_command(case_manager, args),
        "run": lambda: _handle_run_command(case_manager, args),
        "report": lambda: _handle_report_command(env_manager, case_manager, args),
        "status": lambda: _handle_status_command(env_manager),
    }

    try:
        handler = command_handlers.get(args.command)
        if handler:
            handler()
    except Exception as e:
        print_colored(f"✗ Error: {str(e)}", 91)
        if args.debug:
            import traceback

            traceback.print_exc()
