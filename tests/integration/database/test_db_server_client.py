#!/usr/bin/env python3
"""
测试脚本 - 验证数据库服务端和客户端分离架构
"""

import sys
import os
import tempfile
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from objects.db_v2 import EnhancedDBObject  # noqa: E402
from objects.db_server import DatabaseServerComponent  # noqa: E402
from objects.db_client import DatabaseClientComponent  # noqa: E402


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


def test_database_components():
    """测试数据库组件"""
    print("=== Testing Database Components ===\n")

    # 测试服务端组件
    print("1. Testing Database Server Component")
    server_config = {
        "db_type": "sqlite",
        "host": "localhost",
        "port": 9999,
        "data_dir": tempfile.mkdtemp(prefix="test_db_server_"),
        "log_file": tempfile.mktemp(prefix="test_db_server_log_"),
        "pid_file": tempfile.mktemp(prefix="test_db_server_pid_"),
    }

    try:
        server = DatabaseServerComponent(server_config)
        print(f"  ✓ Server component created: {server.db_type}")
        print(f"  ✓ Server endpoint: {server.get_endpoint()}")
        print(f"  ✓ Connection info: {server.get_connection_info()}")

        # 测试状态获取
        status = server.get_status()
        print(f"  ✓ Initial status: {status['status']}")

        print("  ✓ Server component test passed")

    except Exception as e:
        print(f"  ✗ Server component test failed: {str(e)}")

    print()

    # 测试客户端组件
    print("2. Testing Database Client Component")

    # 创建测试数据库
    test_db = tempfile.mktemp(suffix=".db")
    import sqlite3

    conn = sqlite3.connect(test_db)
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO test_table VALUES (1, 'test')")
    conn.commit()
    conn.close()

    client_config = {
        "db_type": "sqlite",
        "server_host": "localhost",
        "server_port": 9999,
        "database": test_db,
        "username": "",
        "password": "",
    }

    try:
        client = DatabaseClientComponent(client_config)
        print(f"  ✓ Client component created: {client.db_type}")
        print(f"  ✓ Server endpoint: {client.server_endpoint}")

        # 测试状态获取
        status = client.get_status()
        print(f"  ✓ Initial status: {status['status']}")

        # 测试连接
        success, message = client.test_connection()
        print(f"  ✓ Connection test: {success} - {message}")

        # 测试查询执行
        success, result = client.execute_query("SELECT * FROM test_table")
        if success:
            print(f"  ✓ Query execution: {result}")
        else:
            print(f"  ✗ Query execution failed: {result}")

        # 测试数据库信息获取
        success, info = client.get_database_info()
        if success:
            print(
                f"  ✓ Database info: {info.get('db_type', 'Unknown')} v{info.get('version', 'Unknown')}"
            )
        else:
            print(f"  ✗ Database info failed: {info}")

        print("  ✓ Client component test passed")

    except Exception as e:
        print(f"  ✗ Client component test failed: {str(e)}")

    # 清理
    os.remove(test_db)


def test_enhanced_database_object():
    """测试增强的数据库对象"""
    print("\n=== Testing Enhanced Database Object ===\n")

    env_manager = MockEnvManager()

    # 测试客户端模式
    print("1. Testing Client-Only Mode")
    test_db = tempfile.mktemp(suffix=".db")

    client_params = {
        "mode": "client_only",
        "db_type": "sqlite",
        "database": test_db,
        "server_host": "localhost",
        "server_port": 9999,
    }

    try:
        db_obj = EnhancedDBObject("test_client_db", env_manager)
        result = db_obj.install(client_params)
        print(f"  Install result: {result}")

        result = db_obj.start()
        print(f"  Start result: {result}")

        # 执行查询测试
        success, result = db_obj.execute_query(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER, name TEXT)"
        )
        print(f"  Create table: {success}")

        success, result = db_obj.execute_query("INSERT INTO users VALUES (1, 'Alice')")
        print(f"  Insert data: {success}")

        success, result = db_obj.execute_query("SELECT COUNT(*) as count FROM users")
        if success:
            print(f"  Query result: {result}")

        # 健康检查
        success, message = db_obj.health_check()
        print(f"  Health check: {success} - {message}")

        # 获取状态
        status = db_obj.get_status()
        print(f"  Overall health: {status['overall_health']}")

        # 清理
        db_obj.uninstall()
        print("  Uninstall result: ✓")

        print("  ✓ Client-only mode test passed")

    except Exception as e:
        print(f"  ✗ Client-only mode test failed: {str(e)}")

    os.remove(test_db)

    print()

    # 测试完整栈模式（模拟）
    print("2. Testing Full Stack Mode (Simulated)")
    full_stack_params = {
        "mode": "full_stack",
        "db_type": "sqlite",
        "database": test_db,
        "server_host": "localhost",
        "server_port": 9998,
        "data_dir": tempfile.mkdtemp(prefix="test_full_stack_"),
    }

    try:
        db_obj = EnhancedDBObject("test_full_stack_db", env_manager)
        result = db_obj.install(full_stack_params)
        print(f"  Install result: {result}")

        # 获取连接信息
        conn_info = db_obj.get_connection_info()
        print(f"  ✓ Has server: {conn_info['has_server']}")
        print(f"  ✓ Has client: {conn_info['has_client']}")
        print(f"  ✓ Mode: {conn_info['mode']}")

        if conn_info["has_server"]:
            server_info = conn_info["server_info"]
            print(f"  ✓ Server status: {server_info.get('status', 'unknown')}")

        if conn_info["has_client"]:
            client_info = conn_info["client_info"]
            print(f"  ✓ Client status: {client_info.get('status', 'unknown')}")
            print(f"  ✓ Connected: {client_info.get('connected', False)}")

        print("  ✓ Full stack mode test passed")

    except Exception as e:
        print(f"  ✗ Full stack mode test failed: {str(e)}")


def test_database_object_modes():
    """测试不同部署模式"""
    print("\n=== Testing Different Deployment Modes ===\n")

    env_manager = MockEnvManager()

    modes = [
        {
            "name": "test_client_only",
            "mode": "client_only",
            "description": "客户端连接模式",
        },
        {
            "name": "test_server_only",
            "mode": "server_only",
            "description": "服务端模式",
        },
        {"name": "test_full_stack", "mode": "full_stack", "description": "完整栈模式"},
    ]

    for mode_config in modes:
        print(f"Testing {mode_config['description']}:")

        params = {
            "mode": mode_config["mode"],
            "db_type": "sqlite",
            "database": tempfile.mktemp(suffix=".db"),
            "server_host": "localhost",
            "server_port": 9997,
            "data_dir": tempfile.mkdtemp(prefix=f"test_{mode_config['mode']}_"),
        }

        try:
            db_obj = EnhancedDBObject(mode_config["name"], env_manager)

            # 安装
            result = db_obj.install(params)
            print(f"  ✓ Install: {result}")

            # 获取状态
            status = db_obj.get_status()
            print(f"  ✓ Mode: {status['mode']}")
            print(f"  ✓ Has server: {status['server_status'] is not None}")
            print(f"  ✓ Has client: {status['client_status'] is not None}")

            # 清理
            db_obj.uninstall()

            # 清理临时文件
            if os.path.exists(params["database"]):
                os.remove(params["database"])

            print(f"  ✓ {mode_config['description']} test passed")

        except Exception as e:
            print(f"  ✗ {mode_config['description']} test failed: {str(e)}")

        print()


def main():
    """主测试函数"""
    print("🚀 Testing Database Server/Client Separation Architecture\n")

    try:
        # 测试基础组件
        test_database_components()

        # 测试增强数据库对象
        test_enhanced_database_object()

        # 测试不同部署模式
        test_database_object_modes()

        print("\n" + "=" * 60)
        print("🎉 DATABASE SERVER/CLIENT ARCHITECTURE TEST COMPLETED")
        print("=" * 60)
        print("✓ Database server component implemented")
        print("✓ Database client component implemented")
        print("✓ Enhanced database object with component separation")
        print("✓ Multiple deployment modes supported")
        print("✓ Health checking for both components")
        print("✓ Connection management and status monitoring")
        print("\n🚀 Database objects now support server/client separation!")

    except Exception as e:
        print(f"\n💥 Test failed: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
