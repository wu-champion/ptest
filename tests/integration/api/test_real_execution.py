#!/usr/bin/env python3
"""
测试脚本 - 验证真实的测试用例执行逻辑
"""

import sys
import os
import json
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent.parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))

# 直接导入模块
from ptest.environment import EnvironmentManager
from ptest.cases.manager import CaseManager


def test_real_execution():
    """测试真实执行逻辑"""
    print("=== Real Execution Test ===")

    # 创建临时测试环境
    test_dir = "/tmp/ptest_real_test"
    if os.path.exists(test_dir):
        import shutil

        shutil.rmtree(test_dir)

    # 初始化环境
    env_manager = EnvironmentManager()
    env_path = env_manager.init_environment(test_dir)
    print(f"✓ Environment initialized at: {env_path}")

    # 创建测试用例管理器
    case_manager = CaseManager(env_manager)
    print("✓ Case manager created")

    # 添加简单的测试用例
    print("Adding test cases...")

    # API测试用例
    api_case = {
        "type": "api",
        "method": "GET",
        "url": "https://jsonplaceholder.typicode.com/users",
        "expected_status": 200,
    }
    result = case_manager.add_case("api_get_users", api_case)
    print(f"  API case added: {result}")

    # 简单的Web测试用例
    web_case = {
        "type": "web",
        "url": "https://example.com",
        "expected_title": "Example Domain",
    }
    result = case_manager.add_case("website_homepage", web_case)
    print(f"  Web case added: {result}")

    print(f"\nTotal test cases added: {len(case_manager.cases)}")

    # 列出所有测试用例
    print("\n" + "=" * 50)
    print("Listing all test cases:")
    print(case_manager.list_cases())

    # 运行一个简单的API测试
    print("\n" + "=" * 50)
    print("Running API test case 'api_get_users':")
    try:
        result = case_manager.run_case("api_get_users")
        print(f"Result: {result}")
    except Exception as e:
        print(f"API test failed: {e}")

    # 运行Web测试
    print("\n" + "=" * 50)
    print("Running Web test case 'website_homepage':")
    try:
        result = case_manager.run_case("website_homepage")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Web test failed: {e}")

    # 显示测试结果
    print("\n" + "=" * 50)
    print("Test Summary:")
    print(f"  Total cases: {len(case_manager.cases)}")
    print(f"  Passed: {len(case_manager.passed_cases)}")
    print(f"  Failed: {len(case_manager.failed_cases)}")

    # 显示详细结果
    if case_manager.results:
        print("\nDetailed Results:")
        for case_id, result_obj in case_manager.results.items():
            print(
                f"  {case_id}: {result_obj.status.upper()} ({result_obj.duration:.2f}s)"
            )
            if result_obj.error_message:
                print(f"    Error: {result_obj.error_message}")

    print("\n=== Test Execution Complete ===")


if __name__ == "__main__":
    test_real_execution()
