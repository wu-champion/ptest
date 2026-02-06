#!/usr/bin/env python3
"""
简单的Python API功能验证
"""

import sys
import os
from pathlib import Path
import unittest
import tempfile
import shutil

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent.parent.parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))

# 直接导入所需的模块
print("测试Python API功能...")


class SimpleAPITest(unittest.TestCase):
    """简单API测试类"""

    def setUp(self):
        """测试前准备"""
        from ptest.environment import EnvironmentManager

        self.env_manager = EnvironmentManager()
        self.test_dir = tempfile.mkdtemp(prefix="ptest_api_test_")

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_environment_creation(self):
        """测试环境创建功能"""
        # 测试环境初始化
        result = self.env_manager.init_environment(self.test_dir)
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(self.test_dir))
        print(f"✓ 成功创建测试环境: {self.test_dir}")

        # 测试环境状态获取
        status = self.env_manager.get_env_status()
        self.assertIsNotNone(status)
        print(f"✓ 成功获取环境状态: {status}")

    def test_framework_components_import(self):
        """测试框架组件导入"""
        try:
            from ptest.isolation.manager import IsolationManager  # noqa: F401
            from ptest.objects.manager import ObjectManager  # noqa: F401
            from ptest.cases.manager import CaseManager  # noqa: F401
            from ptest.reports.generator import ReportGenerator  # noqa: F401
            from ptest.environment import EnvironmentManager  # noqa: F401

            print("✓ 成功导入主要API类")
        except ImportError as e:
            self.fail(f"导入失败: {e}")

    def test_basic_functionality(self):
        """测试基本功能"""
        self.test_environment_creation()
        self.test_framework_components_import()


if __name__ == "__main__":
    print("🧪 运行简单API测试...")
    unittest.main(verbosity=2)
