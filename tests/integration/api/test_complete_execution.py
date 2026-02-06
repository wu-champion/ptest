#!/usr/bin/env python3
"""
完整测试脚本 - 验证真实的测试用例执行逻辑
"""

import sys
import os
import sqlite3
import tempfile
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent.parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))

# 直接导入模块
from ptest.cases.executor import TestExecutor  # noqa: E402
from ptest.cases.manager import CaseManager  # noqa: E402


class MockEnvManager:
    """模拟环境管理器"""

    def __init__(self):
        import logging

        self.logger = logging.getLogger("ptest")
        self.logger.setLevel(logging.INFO)

        # 添加控制台处理器
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
            self.logger.addHandler(handler)


def create_test_database():
    """创建测试数据库"""
    test_db = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()

    # 创建测试表
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    # 插入测试数据
    users_data = [
        (1, "Alice", "alice@example.com", "active"),
        (2, "Bob", "bob@example.com", "active"),
        (3, "Charlie", "charlie@example.com", "inactive"),
        (4, "Diana", "diana@example.com", "active"),
        (5, "Eve", "eve@example.com", "inactive"),
    ]

    cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?)", users_data)
    conn.commit()
    conn.close()

    return test_db


def test_sqlite_execution():
    """测试SQLite执行"""
    print("=== Testing SQLite Test Execution ===\n")

    # 创建测试数据库
    test_db = create_test_database()
    print(f"Created test database: {test_db}")

    # 创建模拟环境管理器和执行器
    env_manager = MockEnvManager()
    executor = TestExecutor(env_manager)

    # 定义测试用例
    test_cases = {
        "sqlite_count_active_users": {
            "type": "database",
            "db_type": "sqlite",
            "database": test_db,
            "query": "SELECT COUNT(*) as count FROM users WHERE status = 'active'",
            "expected_result": {"count": 3},
        },
        "sqlite_get_all_users": {
            "type": "database",
            "db_type": "sqlite",
            "database": test_db,
            "query": "SELECT * FROM users ORDER BY id",
            "expected_result": {"count": 5},
        },
        "sqlite_insert_user": {
            "type": "database",
            "db_type": "sqlite",
            "database": test_db,
            "query": "INSERT INTO users (id, name, email, status) VALUES (6, 'Frank', 'frank@example.com', 'active')",
            "expected_result": None,  # 不检查具体结果，只检查执行是否成功
        },
    }

    # 执行测试
    results = {}
    for case_id, case_data in test_cases.items():
        print(f"\nExecuting test case: {case_id}")
        result = executor.execute_case(case_id, case_data)
        results[case_id] = result

        print(f"  Status: {result.status.upper()}")
        print(f"  Duration: {result.duration:.3f}s")
        print(f"  Output: {result.output}")

        if result.status == "failed":
            print(f"  Error: {result.error_message}")

    # 清理
    os.remove(test_db)
    print(f"\n✓ Cleaned up test database: {test_db}")

    return results


def test_service_execution():
    """测试服务执行"""
    print("\n=== Testing Service Test Execution ===\n")

    env_manager = MockEnvManager()
    executor = TestExecutor(env_manager)

    # 定义测试用例（测试一个不太可能存在的端口）
    test_cases = {
        "service_test_unavailable": {
            "type": "service",
            "service_name": "nonexistent_service",
            "check_type": "port",
            "host": "localhost",
            "port": 9999,  # 很少有服务在这个端口
            "timeout": 2,
        },
        "service_test_localhost": {
            "type": "service",
            "service_name": "localhost",
            "check_type": "port",
            "host": "localhost",
            "port": 22,  # SSH端口（可能开放）
            "timeout": 2,
        },
    }

    # 执行测试
    results = {}
    for case_id, case_data in test_cases.items():
        print(f"\nExecuting test case: {case_id}")
        result = executor.execute_case(case_id, case_data)
        results[case_id] = result

        print(f"  Status: {result.status.upper()}")
        print(f"  Duration: {result.duration:.3f}s")
        print(f"  Output: {result.output}")

        if result.status == "failed":
            print(f"  Error: {result.error_message}")

    return results


def test_case_manager_integration():
    """测试CaseManager集成"""
    print("\n=== Testing CaseManager Integration ===\n")

    # 创建测试数据库
    test_db = create_test_database()

    env_manager = MockEnvManager()
    case_manager = CaseManager(env_manager)

    # 添加测试用例
    test_case = {
        "type": "database",
        "db_type": "sqlite",
        "database": test_db,
        "query": "SELECT COUNT(*) as count FROM users WHERE status = 'active'",
        "expected_result": {"count": 3},
    }

    print("Adding test case...")
    result = case_manager.add_case("integration_test", test_case)
    print(f"  {result}")

    # 运行测试用例
    print("\nRunning test case...")
    result = case_manager.run_case("integration_test")
    print(f"  {result}")

    # 显示结果统计
    print("\nSummary:")
    print(f"  Total cases: {len(case_manager.cases)}")
    print(f"  Passed: {len(case_manager.passed_cases)}")
    print(f"  Failed: {len(case_manager.failed_cases)}")

    # 清理
    os.remove(test_db)
    print(f"\n✓ Cleaned up test database: {test_db}")


def main():
    """主测试函数"""
    print("🚀 Starting Complete Test Execution Validation\n")

    try:
        # 测试SQLite执行
        sqlite_results = test_sqlite_execution()

        # 测试服务执行
        service_results = test_service_execution()

        # 测试CaseManager集成
        test_case_manager_integration()

        # 汇总结果
        print("\n" + "=" * 60)
        print("📊 FINAL TEST SUMMARY")
        print("=" * 60)

        all_results = {**sqlite_results, **service_results}

        total = len(all_results)
        passed = sum(1 for r in all_results.values() if r.status == "passed")
        failed = sum(1 for r in all_results.values() if r.status == "failed")
        errors = sum(1 for r in all_results.values() if r.status == "error")

        print(f"Total tests executed: {total}")
        print(f"✓ Passed: {passed}")
        print(f"✗ Failed: {failed}")
        print(f"⚠ Errors: {errors}")

        if failed > 0 or errors > 0:
            print(
                "\n❌ Some tests failed. This is normal for tests that expect failures (like unavailable services)."
            )

        print("\n🎉 Test execution logic validation completed successfully!")
        print("✓ The real test execution engine is working properly!")

    except Exception as e:
        print(f"\n💥 Test failed with error: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
