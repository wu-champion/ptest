# ptest 测试套件 CLI 命令 / ptest Test Suite CLI Commands
#
# 提供测试套件管理的命令行接口
# Provides CLI for test suite management

from __future__ import annotations


from . import SuiteManager
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
    run_parser.add_argument("--parallel", action="store_true", help="启用并行执行")
    run_parser.add_argument(
        "--workers", type=int, default=4, help="并行执行的最大工作线程数"
    )
    run_parser.add_argument(
        "--stop-on-failure", action="store_true", help="失败时停止执行"
    )
    run_parser.add_argument(
        "--timeout", type=int, default=0, help="用例执行超时时间(秒)"
    )
    run_parser.add_argument(
        "--retry-failed", type=int, default=0, help="失败用例重试次数"
    )
    run_parser.add_argument(
        "--dry-run", action="store_true", help="预览执行顺序，不实际执行"
    )
    run_parser.add_argument(
        "--report-format",
        choices=["html", "json", "md"],
        default=None,
        help="生成报告格式",
    )
    run_parser.add_argument(
        "--report-output", type=str, default=None, help="报告输出路径"
    )

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

    # 检查 dry-run
    dry_run = getattr(args, "dry_run", False)

    # 检查 retry-failed
    retry_count = getattr(args, "retry_failed", 0)

    # 检查执行模式
    parallel = False
    if hasattr(args, "parallel") and args.parallel:
        parallel = True

    max_workers = getattr(args, "workers", suite.max_workers)

    # 检查 stop_on_failure
    stop_on_failure = getattr(args, "stop_on_failure", False) or suite.stop_on_failure

    # 检查 timeout
    timeout = getattr(args, "timeout", 0) or suite.timeout

    if dry_run:
        print_colored("[Dry Run] 预览执行顺序:", 96)
        # 显示执行顺序
        from ..execution import DependencyResolver

        sorted_cases = suite.get_sorted_cases()
        task_ids = [case.case_id for case in sorted_cases]

        dependencies = {}
        for case in suite.cases:
            if case.depends_on:
                dependencies[case.case_id] = case.depends_on

        resolver = DependencyResolver(dependencies)
        try:
            layers = resolver.get_execution_order(task_ids)
            for idx, layer in enumerate(layers):
                print(f"  第 {idx + 1} 层: {', '.join(layer)}")
        except ValueError as e:
            print_colored(f"✗ 依赖解析失败: {e}", 91)

        print_colored("\n[Dry Run] 不执行实际测试", 93)
        return True

    if stop_on_failure:
        print_colored("失败时停止执行", 92)
    if timeout > 0:
        print_colored(f"超时时间: {timeout}秒", 92)
    if retry_count > 0:
        print_colored(f"失败重试次数: {retry_count}", 92)

    # 创建 CaseManager
    try:
        from ..cases.manager import CaseManager

        case_manager = CaseManager(env_manager)
    except Exception as e:
        print_colored(f"✗ 创建 CaseManager 失败: {e}", 91)
        return False

    # 检查用例是否存在
    if not case_manager.cases:
        print_colored("✗ 没有可用的测试用例", 91)
        print_colored("请先添加测试用例: ptest case add <case_id> <json>", 93)
        return False

    # 执行套件 (支持重试)
    try:
        result = suite_manager.execute_suite(
            suite_name=suite.name,
            case_manager=case_manager,
            parallel=parallel,
            max_workers=max_workers,
            stop_on_failure=stop_on_failure,
            timeout=timeout,
            retry_count=retry_count,
        )

        # 显示执行结果
        print()
        if result.get("success"):
            print_colored("✓ 套件执行成功", 92)
        else:
            print_colored("✗ 套件执行失败", 91)

        total = result.get("total", 0)
        passed = result.get("passed", 0)
        failed = result.get("failed", 0)

        print(f"总计: {total}, 通过: {passed}, 失败: {failed}")

        # 显示错误信息
        if result.get("error"):
            print_colored(f"错误: {result.get('error')}", 91)

        if result.get("errors"):
            for error in result.get("errors"):
                print_colored(f"  • {error}", 91)

        # 生成报告
        report_format = getattr(args, "report_format", None)
        if report_format:
            from pathlib import Path
            from datetime import datetime
            import json

            report_output = getattr(args, "report_output", None)
            if report_output:
                output_path = Path(report_output)
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = (
                    Path.cwd()
                    / f"suite_report_{suite.name}_{timestamp}.{report_format}"
                )

            if report_format == "json":
                report_data = {
                    "suite_name": suite.name,
                    "generated_at": datetime.now().isoformat(),
                    "success": result.get("success", False),
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "results": result.get("results", []),
                    "teardown_results": result.get("teardown_results", []),
                }
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(report_data, f, indent=2, ensure_ascii=False)
                print_colored(f"✓ 报告已生成: {output_path}", 92)
            elif report_format == "html":
                # 生成简单HTML报告
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Suite Report - {suite.name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
    </style>
</head>
<body>
    <h1>测试套件报告 / Test Suite Report</h1>
    <div class="summary">
        <h2>摘要 / Summary</h2>
        <p><strong>套件名称:</strong> {suite.name}</p>
        <p><strong>执行时间:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <p><strong>状态:</strong> <span class="{"passed" if result.get("success") else "failed"}">
            {"✓ 成功 / SUCCESS" if result.get("success") else "✗ 失败 / FAILED"}
        </span></p>
        <p><strong>总计:</strong> {total} | <span class="passed">通过: {passed}</span> | <span class="failed">失败: {failed}</span></p>
    </div>
    <h2>测试结果 / Test Results</h2>
    <table>
        <tr><th>用例 ID / Case ID</th><th>状态 / Status</th><th>耗时 / Duration</th></tr>
"""

                for r in result.get("results", []):
                    status = "PASSED" if r.get("success") else "FAILED"
                    status_class = "passed" if r.get("success") else "failed"
                    duration = r.get("duration", "N/A")
                    case_id = r.get("task_id", r.get("case_id", "Unknown"))
                    html_content += f'        <tr><td>{case_id}</td><td class="{status_class}">{status}</td><td>{duration}s</td></tr>\n'

                html_content += """    </table>
</body>
</html>"""

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print_colored(f"✓ 报告已生成: {output_path}", 92)
            elif report_format == "md":
                # 生成 Markdown 报告
                md_content = f"""# 测试套件报告 / Test Suite Report

## 摘要 / Summary

- **套件名称**: {suite.name}
- **执行时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **状态**: {"✓ 成功 / SUCCESS" if result.get("success") else "✗ 失败 / FAILED"}
- **总计**: {total} | 通过: {passed} | 失败: {failed}

## 测试结果 / Test Results

| 用例 ID / Case ID | 状态 / Status | 耗时 / Duration |
|---|---|---|
"""
                for r in result.get("results", []):
                    status = "✓ PASSED" if r.get("success") else "✗ FAILED"
                    duration = r.get("duration", "N/A")
                    case_id = r.get("task_id", r.get("case_id", "Unknown"))
                    md_content += f"| {case_id} | {status} | {duration}s |\n"

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                print_colored(f"✓ 报告已生成: {output_path}", 92)

        return result.get("success", False)

        return result.get("success", False)

    except Exception as e:
        print_colored(f"✗ 执行套件时发生错误: {e}", 91)
        import traceback

        traceback.print_exc()
        return False
