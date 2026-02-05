"""
ptest Python API 测试用例
验证Python API的各项功能是否正常工作
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from ptest.api import PTestAPI, create_ptest_api


class TestPTestAPI(unittest.TestCase):
    """PTestAPI 主类测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_api_test_")
        self.api = PTestAPI(work_path=self.test_dir)

    def tearDown(self):
        """测试后清理"""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_api_initialization(self):
        """测试API初始化"""
        api = PTestAPI()
        self.assertIsNotNone(api)
        self.assertTrue(api.is_initialized)
        self.assertIsNotNone(api.env_manager)
        self.assertIsNotNone(api.isolation_manager)

    def test_api_with_config(self):
        """测试带配置的API初始化"""
        config = {"default_isolation_level": "basic"}
        api = PTestAPI(config=config, work_path=self.test_dir)
        self.assertIsNotNone(api)
        self.assertEqual(api.config["default_isolation_level"], "basic")

    def test_api_work_path(self):
        """测试工作路径设置"""
        api = PTestAPI(work_path=self.test_dir)
        self.assertEqual(str(api.work_path), str(Path(self.test_dir)))


class TestEnvironmentManagement(unittest.TestCase):
    """环境管理功能测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_env_test_")
        self.api = PTestAPI(work_path=self.test_dir)

    def tearDown(self):
        """测试后清理"""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_init_environment(self):
        """测试初始化环境"""
        env_path = self.api.init_environment(path=self.test_dir)
        self.assertIsNotNone(env_path)
        self.assertTrue(Path(env_path).exists())

    def test_get_environment_status(self):
        """测试获取环境状态"""
        self.api.init_environment(path=self.test_dir)
        status = self.api.get_environment_status()
        self.assertIsInstance(status, dict)
        self.assertIn("path", status)


class TestTestCaseManagement(unittest.TestCase):
    """测试用例管理功能测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_case_test_")
        self.api = PTestAPI(work_path=self.test_dir)
        self.api.init_environment()

    def tearDown(self):
        """测试后清理"""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_create_test_case(self):
        """测试创建测试用例"""
        case_id = self.api.create_test_case(
            test_type="api",
            name="test_api_endpoint",
            description="Test API endpoint functionality",
            content={"method": "GET", "url": "http://example.com"},
            tags=["api", "smoke"],
        )
        self.assertIsNotNone(case_id)
        self.assertIsInstance(case_id, str)
        self.assertTrue(len(case_id) > 0)

    def test_list_test_cases(self):
        """测试列出测试用例"""
        result = self.api.list_test_cases()
        self.assertIsInstance(result, str)


class TestReportGeneration(unittest.TestCase):
    """报告生成功能测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_report_test_")
        self.api = PTestAPI(work_path=self.test_dir)
        self.api.init_environment()

    def tearDown(self):
        """测试后清理"""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_generate_report(self):
        """测试生成报告"""
        try:
            report_path = self.api.generate_report(format_type="html")
            self.assertIsInstance(report_path, str)
        except Exception as e:
            self.assertIsInstance(e, Exception)


class TestSystemInfo(unittest.TestCase):
    """系统信息功能测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_info_test_")
        self.api = PTestAPI(work_path=self.test_dir)

    def tearDown(self):
        """测试后清理"""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_get_system_info(self):
        """测试获取系统信息"""
        info = self.api.get_system_info()
        self.assertIsInstance(info, dict)
        self.assertIn("version", info)
        self.assertIn("api_version", info)
        self.assertEqual(info["version"], "1.0.1")
        self.assertIn("isolation_engines", info)


class TestContextManager(unittest.TestCase):
    """上下文管理器测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_ctx_test_")

    def tearDown(self):
        """测试后清理"""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_context_manager(self):
        """测试上下文管理器"""
        with PTestAPI(work_path=self.test_dir) as api:
            self.assertIsNotNone(api)
            self.assertTrue(api.is_initialized)


class TestHelperFunction(unittest.TestCase):
    """便捷函数测试"""

    def test_create_ptest_api(self):
        """测试便捷创建函数"""
        api = create_ptest_api()
        self.assertIsNotNone(api)
        self.assertIsInstance(api, PTestAPI)


def run_api_tests():
    """运行所有API测试"""
    print("运行 ptest Python API 测试...")
    print("=" * 60)

    test_classes = [
        TestPTestAPI,
        TestEnvironmentManagement,
        TestTestCaseManagement,
        TestReportGeneration,
        TestSystemInfo,
        TestContextManager,
        TestHelperFunction,
    ]

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print("测试结果摘要:")
    print(f"运行测试: {result.testsRun}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped) if hasattr(result, 'skipped') else 0}")

    if result.failures:
        print("\n失败的测试:")
        for test, traceback in result.failures:
            print(f"- {test}")

    if result.errors:
        print("\n错误的测试:")
        for test, traceback in result.errors:
            print(f"- {test}")

    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n测试结果: {'全部通过' if success else '存在问题'}")

    return success


if __name__ == "__main__":
    success = run_api_tests()
    sys.exit(0 if success else 1)
