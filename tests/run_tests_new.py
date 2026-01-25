#!/usr/bin/env python3
"""
ptest 测试运行器
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """运行命令并打印结果"""
    print(f"\n{'=' * 50}")
    print(f"🚀 {description}")
    print("=" * 50)
    print(f"命令: {' '.join(cmd)}")
    print("=" * 50)

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=Path(__file__).parent
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print("错误输出:")
            print(result.stderr)

        return result.returncode == 0
    except Exception as e:
        print(f"执行失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="ptest 测试运行器")
    parser.add_argument(
        "--type",
        choices=["unit", "integration", "e2e", "performance", "verification", "all"],
        default="all",
        help="测试类型",
    )
    parser.add_argument("--coverage", action="store_true", help="生成覆盖率报告")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--marker", "-m", help="按标记运行测试")

    args = parser.parse_args()

    # 确定在项目根目录
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    if args.type == "all":
        # 按优先级运行测试
        test_sequence = [
            ("verification", "验证测试"),
            ("unit", "单元测试"),
            ("integration", "集成测试"),
            ("performance", "性能测试"),
            ("e2e", "端到端测试"),
        ]

        success = True
        failed_tests = []

        for test_type, description in test_sequence:
            cmd = ["python", "-m", "pytest", f"tests/{test_type}/"]
            if args.verbose:
                cmd.append("-v")
            if args.marker:
                cmd.extend(["-m", args.marker])
            if args.coverage and test_type == "unit":
                cmd.extend(["--cov=ptest", "--cov-report=term-missing"])

            test_success = run_command(cmd, f"运行{description}")
            if not test_success:
                failed_tests.append(test_type)
                success = False

        if success:
            print("\n✅ 所有测试通过!")
        else:
            print(f"\n❌ 以下测试失败: {', '.join(failed_tests)}")
            sys.exit(1)

    else:
        # 运行特定类型测试
        descriptions = {
            "unit": "单元测试",
            "integration": "集成测试",
            "e2e": "端到端测试",
            "performance": "性能测试",
            "verification": "验证测试",
        }

        description = descriptions.get(args.type, f"{args.type}测试")
        cmd = ["python", "-m", "pytest", f"tests/{args.type}/"]
        if args.verbose:
            cmd.append("-v")
        if args.marker:
            cmd.extend(["-m", args.marker])
        if args.coverage and args.type == "unit":
            cmd.extend(["--cov=ptest", "--cov-report=term-missing"])

        success = run_command(cmd, f"运行{description}")

        if not success:
            sys.exit(1)

    # 生成HTML覆盖率报告
    if args.coverage and args.type in ["unit", "all"]:
        print("\n📊 生成HTML覆盖率报告...")
        cmd = [
            "python",
            "-m",
            "pytest",
            "--cov=ptest",
            "--cov-report=html",
            "tests/unit/",
        ]
        run_command(cmd, "生成HTML覆盖率报告")
        print("📊 HTML覆盖率报告已生成到 htmlcov/index.html")


if __name__ == "__main__":
    main()
