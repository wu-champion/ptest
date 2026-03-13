#!/usr/bin/env python3
"""简单 Python API 功能验证 - ptest 断言版本

迁移说明:
- 原文件使用 pytest/unittest 断言，现已迁移到 ptest 断言
- 迁移对照表:
  - assertIsNotNone(x) → assert_that(x).not_none()
  - assertTrue(x) → assert_that(x).is_true()
  - self.fail() → raise AssertionError()
"""

import sys
import os
from pathlib import Path
import unittest
import tempfile
import shutil

from ptest.assertions import assert_that

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
        # 关闭日志处理器，避免Windows文件锁定
        if hasattr(self, "env_manager") and self.env_manager:
            import logging

            logger = logging.getLogger("ptest.environment")
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_environment_creation(self):
        """测试环境创建功能"""
        # 测试环境初始化
        result = self.env_manager.init_environment(self.test_dir)
        assert_that(result).not_none()
        assert_that(os.path.exists(self.test_dir)).is_true()
        print(f"✓ 成功创建测试环境: {self.test_dir}")

        # 测试环境状态获取
        status = self.env_manager.get_env_status()
        assert_that(status).not_none()
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
            raise AssertionError(f"导入失败: {e}")

    def test_basic_functionality(self):
        """测试基本功能"""
        self.test_environment_creation()
        self.test_framework_components_import()


if __name__ == "__main__":
    print("🧪 运行简单API测试...")
    unittest.main(verbosity=2)
