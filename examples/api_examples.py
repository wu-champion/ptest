#!/usr/bin/env python3
"""
ptest Python API 使用示例
演示如何使用Python API进行测试
"""

from ptest import TestFramework, create_test_framework, quick_test


def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")

    # 使用便捷函数创建框架
    framework = create_test_framework()

    # 创建测试环境
    env = framework.create_environment("./example_test_env")

    # 添加API测试用例
    api_case = env.add_case(
        "api_test",
        {
            "type": "api",
            "method": "GET",
            "url": "https://jsonplaceholder.typicode.com/users",
            "expected_status": 200,
        },
    )

    # 运行测试
    result = api_case.run()
    print(f"API测试结果: {result.status} (耗时: {result.duration:.2f}s)")

    # 生成报告
    report_path = framework.generate_report("html")
    print(f"HTML报告: {report_path}")

    # 清理
    framework.cleanup()


def example_context_manager():
    """上下文管理器示例"""
    print("\n=== 上下文管理器示例 ===")

    with TestFramework() as framework:
        env = framework.create_environment("./context_test_env")

        # 使用上下文管理器管理对象
        with env.add_object("mysql", "test_mysql", version="8.0") as mysql:
            print(f"MySQL对象状态: {mysql.get_status()}")

            # 添加数据库测试用例
            db_case = env.add_case(
                "db_test",
                {
                    "type": "database",
                    "db_object": "test_mysql",
                    "query": "SELECT 1 as test_value",
                    "expected_result": {"test_value": 1},
                },
            )

            result = db_case.run()
            print(f"数据库测试结果: {result.status}")

        # MySQL对象会自动停止

    # 框架会自动清理


def example_multiple_tests():
    """多测试用例示例"""
    print("\n=== 多测试用例示例 ===")

    with TestFramework() as framework:
        env = framework.create_environment("./multi_test_env")

        # 定义多个测试用例
        test_cases = [
            {
                "id": "get_users",
                "data": {
                    "type": "api",
                    "method": "GET",
                    "url": "https://jsonplaceholder.typicode.com/users",
                    "expected_status": 200,
                },
            },
            {
                "id": "get_posts",
                "data": {
                    "type": "api",
                    "method": "GET",
                    "url": "https://jsonplaceholder.typicode.com/posts",
                    "expected_status": 200,
                },
            },
            {
                "id": "web_homepage",
                "data": {
                    "type": "web",
                    "url": "https://example.com",
                    "expected_title": "Example Domain",
                },
            },
        ]

        # 批量添加测试用例
        for test_case in test_cases:
            env.add_case(test_case["id"], test_case["data"])

        # 运行所有测试
        results = env.run_all_cases()

        # 统计结果
        passed = sum(1 for r in results if r.is_passed())
        failed = sum(1 for r in results if r.is_failed())

        print(f"测试完成: {passed} 通过, {failed} 失败")

        for result in results:
            status_icon = "✓" if result.is_passed() else "✗"
            print(
                f"{status_icon} {result.case_id}: {result.status} ({result.duration:.2f}s)"
            )


def example_quick_test():
    """快速测试示例"""
    print("\n=== 快速测试示例 ===")

    # 快速执行单个测试用例
    result = quick_test(
        {
            "type": "api",
            "method": "GET",
            "url": "https://jsonplaceholder.typicode.com/users/1",
            "expected_status": 200,
        }
    )

    print(f"快速测试结果: {result.status}")
    print(f"测试详情: {result.to_dict()}")


def example_error_handling():
    """错误处理示例"""
    print("\n=== 错误处理示例 ===")

    try:
        with TestFramework() as framework:
            env = framework.create_environment("./error_test_env")

            # 添加一个可能失败的测试用例
            error_case = env.add_case(
                "error_test",
                {
                    "type": "api",
                    "method": "GET",
                    "url": "https://nonexistent.example.com/api",
                    "expected_status": 200,
                    "timeout": 5,
                },
            )

            result = error_case.run()

            if result.is_failed():
                print(f"测试失败: {result.get_error()}")
            else:
                print("测试意外通过")

    except Exception as e:
        print(f"捕获异常: {e}")


def example_object_management():
    """对象管理示例"""
    print("\n=== 对象管理示例 ===")

    with TestFramework() as framework:
        env = framework.create_environment("./object_test_env")

        # 创建并管理对象
        mysql_obj = env.add_object("mysql", "test_db", version="8.0")

        # 手动管理对象生命周期
        if mysql_obj.start():
            print("MySQL对象启动成功")

            status = mysql_obj.get_status()
            print(f"MySQL状态: {status}")

            # 添加测试用例
            case = env.add_case(
                "mysql_test",
                {
                    "type": "database",
                    "db_object": "test_db",
                    "query": "SELECT VERSION() as version",
                    "expected_result": {"version": "8.0"},  # 这里可能需要调整
                },
            )

            result = case.run()
            print(f"MySQL测试结果: {result.status}")

            # 停止对象
            if mysql_obj.stop():
                print("MySQL对象停止成功")
        else:
            print("MySQL对象启动失败")


if __name__ == "__main__":
    print("ptest Python API 使用示例")
    print("=" * 50)

    # 运行所有示例
    examples = [
        example_basic_usage,
        example_context_manager,
        example_multiple_tests,
        example_quick_test,
        example_error_handling,
        example_object_management,
    ]

    for example_func in examples:
        try:
            example_func()
        except Exception as e:
            print(f"示例执行失败 {example_func.__name__}: {e}")

        print("-" * 30)

    print("\n所有示例执行完成！")
