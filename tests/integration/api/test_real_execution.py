#!/usr/bin/env python3
"""
测试脚本 - 验证真实的测试用例执行逻辑
"""

import sys
import os
import json
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 直接导入模块
from environment import EnvironmentManager
from cases.manager import CaseManager
from examples.test_cases import all_test_cases


def test_real_execution():
    """测试真实的测试用例执行"""
    print("=== Testing Real Test Case Execution ===\n")

    # 初始化环境
    env_manager = EnvironmentManager()
    env_manager.init_environment("/tmp/ptest_test")

    # 创建测试用例管理器
    case_manager = CaseManager(env_manager)

    # 添加测试用例
    print("Adding test cases...")
    for case_id, case_data in all_test_cases.items():
        result = case_manager.add_case(case_id, case_data)
        print(f"  {result}")

    print(f"\nTotal test cases added: {len(all_test_cases)}")

    # 列出所有测试用例
    print("\n" + "=" * 50)
    print("Listing all test cases:")
    print(case_manager.list_cases())

    # 运行一个简单的API测试
    print("\n" + "=" * 50)
    print("Running API test case 'api_get_users':")
    result = case_manager.run_case("api_get_users")
    print(f"Result: {result}")

    # 运行Web测试
    print("\n" + "=" * 50)
    print("Running Web test case 'website_homepage':")
    result = case_manager.run_case("website_homepage")
    print(f"Result: {result}")

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
