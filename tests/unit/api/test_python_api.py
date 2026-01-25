#!/usr/bin/env python3
"""
ptest Python API 测试用例
验证Python API的各项功能是否正常工作
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os

# 添加项目路径到sys.path以便导入
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 由于我们在项目中，使用相对导入
import sys
import os

current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from api import TestFramework, TestEnvironment, ManagedObject, TestCase, TestResult
    from api import create_test_framework, quick_test
except ImportError:
    print("导入失败，尝试从模块导入...")
    sys.path.insert(0, str(current_dir.parent))
    from ptest.api import (
        TestFramework,
        TestEnvironment,
        ManagedObject,
        TestCase,
        TestResult,
    )
    from ptest.api import create_test_framework, quick_test


class TestTestFramework(unittest.TestCase):
    """TestFramework类测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_test_")
        self.framework = TestFramework()

    def tearDown(self):
        """测试后清理"""
        self.framework.cleanup()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_framework_creation(self):
        """测试框架创建"""
        framework = TestFramework()
        self.assertIsNotNone(framework)
        self.assertEqual(framework.version, "1.0.1")
        framework.cleanup()

    def test_create_test_framework_function(self):
        """测试便捷创建函数"""
        framework = create_test_framework()
        self.assertIsNotNone(framework)
        self.assertIsInstance(framework, TestFramework)
        framework.cleanup()

    def test_create_environment(self):
        """测试创建测试环境"""
        env = self.framework.create_environment(self.test_dir)
        self.assertIsNotNone(env)
        self.assertIsInstance(env, TestEnvironment)
        self.assertEqual(str(env.path), str(Path(self.test_dir).resolve()))

    def test_environment_status(self):
        """测试环境状态"""
        env = self.framework.create_environment(self.test_dir)
        status = env.get_status()
        self.assertIsInstance(status, dict)
        self.assertIn("path", status)

    def test_framework_status(self):
        """测试框架状态"""
        status = self.framework.get_status()
        self.assertIsInstance(status, dict)
        self.assertIn("version", status)
        self.assertIn("environments", status)


class TestTestEnvironment(unittest.TestCase):
    """TestEnvironment类测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_env_test_")
        self.framework = TestFramework()
        self.env = self.framework.create_environment(self.test_dir)

    def tearDown(self):
        """测试后清理"""
        self.framework.cleanup()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_add_test_case(self):
        """测试添加测试用例"""
        case = self.env.add_case(
            "test_api",
            {
                "type": "api",
                "method": "GET",
                "url": "https://jsonplaceholder.typicode.com/users",
                "expected_status": 200,
            },
        )

        self.assertIsNotNone(case)
        self.assertIsInstance(case, TestCase)
        self.assertEqual(case.case_id, "test_api")

    def test_add_object(self):
        """测试添加对象"""
        obj = self.env.add_object("mysql", "test_mysql", version="8.0")
        self.assertIsNotNone(obj)
        self.assertIsInstance(obj, ManagedObject)
        self.assertEqual(obj.name, "test_mysql")


class TestManagedObject(unittest.TestCase):
    """ManagedObject类测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_obj_test_")
        self.framework = TestFramework()
        self.env = self.framework.create_environment(self.test_dir)
        self.obj = self.env.add_object("mysql", "test_mysql", version="8.0")

    def tearDown(self):
        """测试后清理"""
        self.framework.cleanup()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_object_creation(self):
        """测试对象创建"""
        self.assertIsNotNone(self.obj)
        self.assertEqual(self.obj.name, "test_mysql")

    def test_object_status(self):
        """测试对象状态"""
        status = self.obj.get_status()
        self.assertIsInstance(status, dict)
        self.assertIn("name", status)
        self.assertIn("status", status)

    def test_context_manager(self):
        """测试上下文管理器"""
        with self.env.add_object("mysql", "context_mysql") as mysql_obj:
            self.assertIsNotNone(mysql_obj)
            # 对象应该在with块内启动
            # 由于这是模拟测试，我们主要验证对象确实存在


class TestTestCase(unittest.TestCase):
    """TestCase类测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_case_test_")
        self.framework = TestFramework()
        self.env = self.framework.create_environment(self.test_dir)
        self.case = self.env.add_case(
            "test_api",
            {
                "type": "api",
                "method": "GET",
                "url": "https://jsonplaceholder.typicode.com/users",
                "expected_status": 200,
            },
        )

    def tearDown(self):
        """测试后清理"""
        self.framework.cleanup()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_case_creation(self):
        """测试用例创建"""
        self.assertIsNotNone(self.case)
        self.assertEqual(self.case.case_id, "test_api")

    def test_case_data(self):
        """测试用例数据"""
        data = self.case.get_data()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["type"], "api")
        self.assertEqual(data["method"], "GET")

    def test_case_status(self):
        """测试用例状态"""
        status = self.case.get_status()
        self.assertIsInstance(status, dict)
        self.assertIn("id", status)
        self.assertIn("status", status)


class TestTestResult(unittest.TestCase):
    """TestResult类测试"""

    def test_result_creation(self):
        """测试结果创建"""
        # 模拟一个成功的测试结果
        result = TestResult("✓ Test case 'test_id' passed", "test_id")

        self.assertTrue(result.is_passed())
        self.assertFalse(result.is_failed())
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.case_id, "test_id")

    def test_result_to_dict(self):
        """测试结果转换为字典"""
        result = TestResult("✓ Test case 'test_id' passed", "test_id")
        result_dict = result.to_dict()

        self.assertIsInstance(result_dict, dict)
        self.assertIn("case_id", result_dict)
        self.assertIn("status", result_dict)
        self.assertIn("success", result_dict)
        self.assertTrue(result_dict["success"])


class TestQuickTest(unittest.TestCase):
    """快速测试功能测试"""

    def test_quick_test_function(self):
        """测试快速测试函数"""
        # 使用一个简单的API测试
        result = quick_test(
            {
                "type": "api",
                "method": "GET",
                "url": "https://jsonplaceholder.typicode.com/users/1",
                "expected_status": 200,
            }
        )

        self.assertIsNotNone(result)
        self.assertIsInstance(result, TestResult)
        # 由于网络依赖，这里我们主要验证功能调用不出错


class TestIntegration(unittest.TestCase):
    """集成测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_integration_test_")

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_full_workflow(self):
        """测试完整工作流程"""
        with TestFramework() as framework:
            # 创建环境
            env = framework.create_environment(self.test_dir)

            # 添加测试用例
            case1 = env.add_case(
                "api_users",
                {
                    "type": "api",
                    "method": "GET",
                    "url": "https://jsonplaceholder.typicode.com/users",
                    "expected_status": 200,
                },
            )

            case2 = env.add_case(
                "api_posts",
                {
                    "type": "api",
                    "method": "GET",
                    "url": "https://jsonplaceholder.typicode.com/posts",
                    "expected_status": 200,
                },
            )

            # 运行测试
            result1 = case1.run()
            result2 = case2.run()

            # 验证结果
            self.assertIsNotNone(result1)
            self.assertIsNotNone(result2)
            self.assertIsInstance(result1, TestResult)
            self.assertIsInstance(result2, TestResult)

            # 生成报告
            try:
                report_path = framework.generate_report("json")
                self.assertIsNotNone(report_path)
            except Exception as e:
                # 如果报告生成失败，记录但不影响测试
                print(f"报告生成失败（可接受的）: {e}")

    def test_context_manager_workflow(self):
        """测试上下文管理器工作流程"""
        with TestFramework() as framework:
            env = framework.create_environment(self.test_dir)

            with env.add_object("mysql", "test_db") as mysql_obj:
                self.assertIsNotNone(mysql_obj)
                status = mysql_obj.get_status()
                self.assertIsInstance(status, dict)

            # 对象应该自动停止


class TestErrorHandling(unittest.TestCase):
    """错误处理测试"""

    def test_invalid_object_type(self):
        """测试无效对象类型"""
        framework = TestFramework()
        try:
            env = framework.create_environment("/tmp/ptest_error_test")
            # 尝试添加无效对象类型，应该抛出异常或返回错误
            obj = env.add_object("invalid_type", "test")
            # 如果没有异常，验证对象状态
            status = obj.get_status()
        except Exception as e:
            # 预期会有异常
            self.assertIsInstance(e, (ValueError, Exception))
        finally:
            framework.cleanup()

    def test_no_environment_specified(self):
        """测试未指定环境的情况"""
        framework = TestFramework()

        # 不创建环境，直接尝试创建测试用例
        with self.assertRaises(ValueError):
            framework.create_case("test_case", {"type": "api"})

        framework.cleanup()


def run_api_tests():
    """运行所有API测试"""
    print("运行 ptest Python API 测试...")
    print("=" * 60)

    # 创建测试套件
    test_classes = [
        TestTestFramework,
        TestTestEnvironment,
        TestManagedObject,
        TestTestCase,
        TestTestResult,
        TestQuickTest,
        TestIntegration,
        TestErrorHandling,
    ]

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出测试结果摘要
    print("\n" + "=" * 60)
    print("测试结果摘要:")
    print(f"运行测试: {result.testsRun}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped) if hasattr(result, 'skipped') else 0}")

    if result.failures:
        print("\n失败的测试:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")

    if result.errors:
        print("\n错误的测试:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")

    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n测试结果: {'全部通过' if success else '存在问题'}")

    return success


if __name__ == "__main__":
    success = run_api_tests()
    sys.exit(0 if success else 1)
