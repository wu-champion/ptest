#!/usr/bin/env python3
"""
测试运行器 - 集中运行所有测试
"""

import sys
import importlib
import traceback
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入测试配置
from tests import TEST_CONFIG  # noqa: E402


def run_test_module(module_name: str) -> bool:
    """运行单个测试模块"""
    print(f"\n{'=' * 60}")
    print(f"Running {module_name}")
    print(f"{'=' * 60}")

    try:
        module = importlib.import_module(f"tests.{module_name}")
        if hasattr(module, "main"):
            module.main()
            return True
        else:
            print(f"⚠️  Module {module_name} has no main() function")
            return False
    except Exception as e:
        print(f"❌ Failed to run {module_name}: {str(e)}")
        if "--verbose" in sys.argv:
            traceback.print_exc()
        return False


def discover_test_modules() -> list:
    """发现所有测试模块"""
    tests_dir = Path(__file__).parent
    test_modules = []

    for file_path in tests_dir.glob("test_*.py"):
        if file_path.name != "__init__.py":
            module_name = file_path.stem
            test_modules.append(module_name)

    return sorted(test_modules)


def run_all_tests(test_modules: list = None) -> dict:  # type: ignore
    """运行所有测试"""
    if test_modules is None:
        test_modules = discover_test_modules()

    print("🚀 ptest Framework Test Runner")
    print(f"Found {len(test_modules)} test modules")
    print(f"Test data directory: {TEST_CONFIG['test_data_dir']}")
    print(f"Test temp directory: {TEST_CONFIG['test_temp_dir']}")
    print(f"Test reports directory: {TEST_CONFIG['test_reports_dir']}")

    results = {"total": len(test_modules), "passed": 0, "failed": 0, "details": {}}

    for module_name in test_modules:
        success = run_test_module(module_name)
        results["details"][module_name] = success

        if success:
            results["passed"] += 1
            print(f"✅ {module_name} PASSED")
        else:
            results["failed"] += 1
            print(f"❌ {module_name} FAILED")

    return results


def run_specific_test(module_name: str) -> bool:
    """运行特定测试模块"""
    test_modules = discover_test_modules()

    if module_name not in test_modules:
        available = ", ".join(test_modules)
        print(f"❌ Test module '{module_name}' not found")
        print(f"Available modules: {available}")
        return False

    return run_test_module(module_name)


def print_summary(results: dict):
    """打印测试结果摘要"""
    print(f"\n{'=' * 60}")
    print("📊 TEST SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total tests: {results['total']}")
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")

    if results["failed"] == 0:
        print("\n🎉 ALL TESTS PASSED!")
        return True
    else:
        print(f"\n💥 {results['failed']} TESTS FAILED")

        # 显示失败的测试
        failed_tests = [
            name for name, result in results["details"].items() if not result
        ]
        if failed_tests:
            print(f"Failed modules: {', '.join(failed_tests)}")

        return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="ptest Framework Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/run_tests.py                    # Run all tests
  python tests/run_tests.py test_basic          # Run specific test
  python tests/run_tests.py --list             # List all test modules
  python tests/run_tests.py --verbose          # Run with verbose output
        """,
    )

    parser.add_argument(
        "module", nargs="?", help="Specific test module to run (without .py extension)"
    )
    parser.add_argument(
        "--list", "-l", action="store_true", help="List all available test modules"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--failfast", "-f", action="store_true", help="Stop on first test failure"
    )

    args = parser.parse_args()

    # 如果使用verbose，添加到参数列表
    if args.verbose:
        sys.argv.append("--verbose")

    if args.list:
        test_modules = discover_test_modules()
        print("Available test modules:")
        for module in test_modules:
            print(f"  - {module}")
        return

    if args.module:
        # 运行特定测试
        success = run_specific_test(args.module)
        if success:
            print(f"\n✅ {args.module} PASSED")
        else:
            print(f"\n❌ {args.module} FAILED")
            sys.exit(1)
    else:
        # 运行所有测试
        test_modules = discover_test_modules()
        if not test_modules:
            print("❌ No test modules found!")
            sys.exit(1)

        results = run_all_tests(test_modules)
        success = print_summary(results)

        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()
