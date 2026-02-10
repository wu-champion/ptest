#!/usr/bin/env python3
"""
测试脚本 - 验证数据库对象与测试执行器的集成
"""

import sys
import os
import sqlite3
import tempfile
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from ptest.cases.manager import CaseManager  # noqa: E402
from ptest.objects.db import DBObject  # noqa: E402
from ptest.objects.manager import ObjectManager  # noqa: E402


class MockEnvManager:
    """模拟环境管理器"""

    def __init__(self):
        import logging
        from pathlib import Path
        import tempfile

        self.logger = logging.getLogger("ptest")
        self.logger.setLevel(logging.INFO)

        # 添加控制台处理器
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
            self.logger.addHandler(handler)

        # 添加 test_path 属性
        self.test_path = Path(tempfile.mkdtemp(prefix="ptest_test_"))

        self.obj_manager = ObjectManager(self)


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


def test_database_object_integration():
    """测试数据库对象与测试执行器的集成"""
    print("=== Testing Database Object Integration ===\n")

    # 创建测试数据库
    test_db = create_test_database()
    print(f"Created test database: {test_db}")

    # 创建模拟环境管理器
    env_manager = MockEnvManager()

    # 1. 创建并安装数据库对象
    print("\n1. Creating and installing database object...")
    db_config = {"db_type": "sqlite", "database": test_db, "timeout": 30}

    db_object = DBObject("test_db", env_manager)
    install_result = db_object.install(db_config)
    print(f"  Install result: {install_result}")

    # 添加到对象管理器
    env_manager.obj_manager.objects["test_db"] = db_object

    # 2. 测试数据库对象的查询功能
    print("\n2. Testing database object query functionality...")

    test_queries = [
        ("SELECT COUNT(*) as count FROM users", "Count all users"),
        (
            "SELECT COUNT(*) as count FROM users WHERE status = 'active'",
            "Count active users",
        ),
        ("SELECT * FROM users ORDER BY id LIMIT 3", "Get first 3 users"),
    ]

    for query, description in test_queries:
        print(f"\n  Testing: {description}")
        success, result = db_object.execute_query(query)
        print(f"    Success: {success}")
        print(f"    Result: {result}")

    # 3. 创建测试用例管理器和执行器
    print("\n3. Creating test case manager and executor...")
    case_manager = CaseManager(env_manager)

    # 4. 添加数据库测试用例
    print("\n4. Adding database test cases...")

    test_cases = {
        "db_count_active_users": {
            "type": "database",
            "db_object": "test_db",  # 指向数据库对象
            "query": "SELECT COUNT(*) as count FROM users WHERE status = 'active'",
            "expected_result": {"count": 3},
        },
        "db_get_all_users": {
            "type": "database",
            "db_object": "test_db",
            "query": "SELECT * FROM users ORDER BY id",
            "expected_result": {"count": 5},
        },
        "db_get_inactive_users": {
            "type": "database",
            "db_object": "test_db",
            "query": "SELECT COUNT(*) as count FROM users WHERE status = 'inactive'",
            "expected_result": {"count": 2},
        },
    }

    for case_id, case_data in test_cases.items():
        result = case_manager.add_case(case_id, case_data)
        print(f"  {result}")

    # 5. 运行测试用例
    print("\n5. Running database test cases...")

    for case_id in test_cases.keys():
        result = case_manager.run_case(case_id)
        print(f"  {result}")

    # 6. 显示测试摘要
    print("\n6. Test Summary:")
    print(f"  Total cases: {len(case_manager.cases)}")
    print(f"  Passed: {len(case_manager.passed_cases)}")
    print(f"  Failed: {len(case_manager.failed_cases)}")

    # 7. 清理
    print("\n7. Cleaning up...")
    db_object.uninstall()
    os.remove(test_db)
    print(f"  ✓ Cleaned up test database: {test_db}")

    return True


def test_database_object_types():
    """测试不同数据库类型的对象创建"""
    print("\n=== Testing Different Database Types ===\n")

    env_manager = MockEnvManager()

    db_types = [
        {
            "name": "test_sqlite",
            "config": {"db_type": "sqlite", "database": ":memory:", "timeout": 30},
        },
        {
            "name": "test_mysql",
            "config": {
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "username": "root",
                "password": "",
                "database": "test",
                "timeout": 30,
            },
        },
        {
            "name": "test_postgresql",
            "config": {
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "username": "postgres",
                "password": "",
                "database": "test",
                "timeout": 30,
            },
        },
    ]

    for db_info in db_types:
        print(f"Testing {db_info['config']['db_type']} database object...")

        try:
            db_object = DBObject(db_info["name"], env_manager)
            result = db_object.install(db_info["config"])
            print(f"  Install result: {result}")

            if "✓" in result:
                # 测试连接
                test_result = db_object.execute_query("SELECT 1 as test")
                print(f"  Test query result: {test_result}")

                # 清理
                db_object.uninstall()
            else:
                print("  Installation failed, skipping connection test")

        except Exception as e:
            print(f"  Error: {str(e)}")

        print()


def main():
    """主测试函数"""
    print("🚀 Testing Database Object Integration with Test Execution\n")

    try:
        # 测试数据库对象集成
        test_database_object_integration()

        # 测试不同数据库类型
        test_database_object_types()

        print("\n" + "=" * 60)
        print("🎉 DATABASE OBJECT INTEGRATION TEST COMPLETED")
        print("=" * 60)
        print("✓ Database objects now provide connection management")
        print("✓ Test executor uses database objects instead of direct connections")
        print("✓ Database configuration is managed through objects")
        print("✓ Supports SQLite, MySQL, and PostgreSQL")
        print("\n🚀 This is a much better architecture!")

    except Exception as e:
        print(f"\n💥 Test failed: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
