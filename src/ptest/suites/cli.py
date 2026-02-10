# ptest 测试套件 CLI 命令 / ptest Test Suite CLI Commands
#
# 提供测试套件管理的命令行接口
# Provides CLI for test suite management

from __future__ import annotations


from . import SuiteManager, ExecutionMode
from ..utils import print_colored, get_colored_text
from ..core import get_logger

logger = get_logger("suites.cli")


def setup_suite_subparser(subparsers):
    """设置 suite 子命令"""
    suite_parser = subparsers.add_parser(
        "suite", help=get_colored_text("测试套件管理", 92)
    )
    suite_subparsers = suite_parser.add_subparsers(
        dest="suite_action", help="测试套件操作 / Suite actions"
    )

    # 创建套件命令
    create_parser = suite_subparsers.add_parser("create", help="创建测试套件")
    create_parser.add_argument("name", help="套件名称")
    create_parser.add_argument(
        "--from-file", "-f", help="从配置文件创建套件（JSON/YAML）", default=None
    )

    # 列出套件命令
    suite_subparsers.add_parser("list", help="列出所有套件")

    # 显示套件命令
    show_parser = suite_subparsers.add_parser("show", help="显示套件详情")
    show_parser.add_argument("name", help="套件名称")

    # 删除套件命令
    delete_parser = suite_subparsers.add_parser("delete", help="删除测试套件")
    delete_parser.add_argument("name", help="套件名称")

    # 验证命令
    validate_parser = suite_subparsers.add_parser("validate", help="验证套件配置")
    validate_parser.add_argument("name", help="套件名称")

    # 运行套件命令
    run_parser = suite_subparsers.add_parser("run", help="运行测试套件")
    run_parser.add_argument("name", help="套件名称")
    run_parser.add_argument("--verbose", action="store_true", help="显示详细输出")

    return suite_parser


def handle_suite_command(env_manager, args) -> bool:
    """处理 suite 命令"""
    if not hasattr(args, "suite_action") or not args.suite_action:
        print_colored("请指定套件操作: create/list/show/delete/validate/run", 91)
        return False

    suite_manager = SuiteManager(storage_dir=env_manager.test_path)

    handlers = {
        "create": lambda: _handle_create(env_manager, suite_manager, args),
        "list": lambda: _handle_list(env_manager, suite_manager, args),
        "show": lambda: _handle_show(env_manager, suite_manager, args),
        "delete": lambda: _handle_delete(env_manager, suite_manager, args),
        "validate": lambda: _handle_validate(env_manager, suite_manager, args),
        "run": lambda: _handle_run(env_manager, suite_manager, args),
    }

    handler = handlers.get(args.suite_action)
    if handler:
        return handler()

    print_colored("未知的套件操作", 91)
    return False


def _handle_create(env_manager, suite_manager, args) -> bool:
    """处理创建套件命令"""
    from pathlib import Path
    import json

    suite_name = args.name

    # 检查套件是否已存在
    if suite_manager.load_suite(suite_name):
        print_colored(f"✗ 套件已存在: {suite_name}", 91)
        return False

    suite_data = None

    # 如果从文件创建
    if hasattr(args, "from_file") and args.from_file:
        file_path = Path(args.from_file)
        if not file_path.exists():
            print_colored(f"✗ 文件不存在: {args.from_file}", 91)
            return False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix in [".yaml", ".yml"]:
                    try:
                        import yaml  # type: ignore[import-untyped]

                        suite_data = yaml.safe_load(f)
                    except ImportError:
                        print_colored("✗ 需要安装 PyYAML: pip install pyyaml", 91)
                        return False
                else:
                    suite_data = json.load(f)

            # 确保名称一致
            if suite_data:
                suite_data["name"] = suite_name

            print_colored(f"✓ 从文件加载配置: {args.from_file}", 92)

        except Exception as e:
            print_colored(f"✗ 读取文件失败: {e}", 91)
            return False
    else:
        # 创建空套件
        suite_data = {
            "name": suite_name,
            "description": None,
            "setup": [],
            "cases": [],
            "teardown": [],
            "execution_mode": "sequential",
            "max_workers": 4,
        }

    # 创建套件
    try:
        suite = suite_manager.create_suite(suite_data)
        print_colored(f"✓ 测试套件创建成功: {suite.name}", 92)

        # 显示套件信息
        print(f"  用例数: {len(suite.cases)}")
        print(f"  执行模式: {suite.execution_mode.value}")
        print(f"  最大并行数: {suite.max_workers}")

        return True

    except Exception as e:
        print_colored(f"✗ 创建套件失败: {e}", 91)
        return False


def _handle_list(env_manager, suite_manager, args) -> bool:
    """列出所有套件"""
    suites = suite_manager.list_suites()

    if not suites:
        print_colored("没有找到测试套件", 93)
        return True

    print_colored("测试套件列表:", 96)
    for name in suites:
        suite = suite_manager.load_suite(name)
        if suite:
            print(f"  • {name}")
            if suite.description:
                print(f"    {suite.description}")
            print(f"    用例数: {len(suite.cases)}")
            print(f"    执行模式: {suite.execution_mode.value}")
            print(f"    最大并行数: {suite.max_workers}")
        print()

    return True


def _handle_show(env_manager, suite_manager, args) -> bool:
    """显示套件详情"""
    suite = suite_manager.load_suite(args.name)

    if not suite:
        print_colored(f"套件不存在: {args.name}", 91)
        return False

    print_colored(f"套件: {suite.name}", 96)
    if suite.description:
        print_colored(f"描述: {suite.description}", 96)
    print()

    print_colored("Setup Hooks:", 94)
    for hook_name in suite.setup:
        print(f"  • {hook_name}")
    print()

    print_colored("用例列表:", 96)
    for case in suite.get_sorted_cases():
        status = "跳过" if case.skip else "执行"
        print(f"  [{case.order}] {status} {case.case_id}")
        if case.depends_on:
            print(f"      依赖: {', '.join(case.depends_on)}")
        if case.skip_reason:
            print(f"      原因: {case.skip_reason}")
    print()

    print_colored("Teardown Hooks:", 94)
    for hook_name in suite.teardown:
        print(f"  • {hook_name}")
    print()

    return True


def _handle_delete(env_manager, suite_manager, args) -> bool:
    """删除套件"""
    if suite_manager.delete_suite(args.name):
        print_colored(f"套件删除成功: {args.name}", 92)
        return True
    else:
        print_colored(f"套件删除失败: {args.name}", 91)
        return False


def _handle_validate(env_manager, suite_manager, args) -> bool:
    """验证套件配置"""
    suite = suite_manager.load_suite(args.name)

    if not suite:
        print_colored(f"套件不存在: {args.name}", 91)
        return False

    is_valid, errors = suite.validate()

    if is_valid:
        print_colored("✓ 套件配置有效", 92)
        return True
    else:
        print_colored("✗ 套件配置无效:", 91)
        for error in errors:
            print_colored(f"  • {error}", 91)
        return False


def _handle_run(env_manager, suite_manager, args) -> bool:
    """运行套件"""
    suite = suite_manager.load_suite(args.name)

    if not suite:
        print_colored(f"套件不存在: {args.name}", 91)
        return False

    print_colored(f"运行套件: {suite.name}", 94)
    print_colored(f"执行模式: {suite.execution_mode.value}", 94)
    print(f"最大并行数: {suite.max_workers}")
    print()

    is_valid, errors = suite.validate()
    if not is_valid:
        print_colored("✗ 套件配置验证失败:", 91)
        for error in errors:
            print_colored(f"  • {error}", 91)
        return False

    if suite.execution_mode == ExecutionMode.PARALLEL and suite.max_workers > 1:
        print_colored("注意: 并行执行功能需要进一步实现", 93)
        print_colored("当前只支持串行执行", 93)
    print()

    # TODO: 实现并行执行逻辑
    # for case in suite.get_sorted_cases():
    #     if not case.skip:
    #         case_manager.run_case(case.case_id)

    print_colored("串行执行功能待实现", 93)
    return True
