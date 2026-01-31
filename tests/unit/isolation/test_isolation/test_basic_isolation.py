"""
隔离模块基础测试

测试隔离管理器和基础功能
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 直接导入模块
from ptest.isolation.manager import IsolationManager
from ptest.isolation.enums import IsolationLevel, EnvironmentStatus
from ptest.isolation.basic_engine import BasicIsolationEngine


class TestIsolationManager(unittest.TestCase):
    """隔离管理器测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_isolation_test_")
        self.config = {
            "default_isolation_level": "basic",
            "max_environments": 10,
            "basic": {"enabled": True},
        }

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_manager_initialization(self):
        """测试管理器初始化"""
        manager = IsolationManager(self.config)

        self.assertEqual(manager.default_isolation_level, "basic")
        self.assertEqual(manager.max_environments, 10)
        self.assertIn("basic", manager.engines)

    def test_create_basic_environment(self):
        """测试创建基础环境"""
        manager = IsolationManager(self.config)

        env_path = Path(self.test_dir) / "test_env"
        env = manager.create_environment(env_path, isolation_level="basic")

        self.assertIsNotNone(env)
        self.assertEqual(env.status, EnvironmentStatus.CREATED)
        self.assertEqual(
            env.env_id,
            manager.list_environments()[list(manager.list_environments().keys())[0]][
                "env_id"
            ],
        )

        # 清理
        manager.cleanup_environment(env.env_id)

    def test_list_environments(self):
        """测试列出环境"""
        manager = IsolationManager(self.config)

        # 创建多个环境
        env_path1 = Path(self.test_dir) / "test_env1"
        env_path2 = Path(self.test_dir) / "test_env2"

        env1 = manager.create_environment(env_path1, isolation_level="basic")
        env2 = manager.create_environment(env_path2, isolation_level="basic")

        environments = manager.list_environments()
        self.assertEqual(len(environments), 2)
        self.assertIn(env1.env_id, environments)
        self.assertIn(env2.env_id, environments)

        # 清理
        manager.cleanup_all_environments()

    def test_cleanup_environment(self):
        """测试清理环境"""
        manager = IsolationManager(self.config)

        env_path = Path(self.test_dir) / "test_env"
        env = manager.create_environment(env_path, isolation_level="basic")

        env_id = env.env_id
        self.assertIn(env_id, manager.active_environments)

        # 清理环境
        success = manager.cleanup_environment(env_id)
        self.assertTrue(success)
        self.assertNotIn(env_id, manager.active_environments)

    def test_max_environments_limit(self):
        """测试最大环境数量限制"""
        config = self.config.copy()
        config["max_environments"] = 2
        manager = IsolationManager(config)

        # 创建环境直到达到限制
        env1 = manager.create_environment(
            Path(self.test_dir) / "test_env1", isolation_level="basic"
        )
        env2 = manager.create_environment(
            Path(self.test_dir) / "test_env2", isolation_level="basic"
        )

        # 尝试创建第三个环境应该失败
        with self.assertRaises(RuntimeError):
            manager.create_environment(
                Path(self.test_dir) / "test_env3", isolation_level="basic"
            )

        # 清理
        manager.cleanup_all_environments()

    def test_unsupported_isolation_level(self):
        """测试不支持的隔离级别"""
        manager = IsolationManager(self.config)

        env_path = Path(self.test_dir) / "test_env"

        with self.assertRaises(ValueError):
            manager.create_environment(env_path, isolation_level="unsupported_level")


class TestBasicIsolationEngine(unittest.TestCase):
    """基础隔离引擎测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_basic_isolation_test_")
        self.config = {}
        self.engine = BasicIsolationEngine(self.config)

    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_engine_initialization(self):
        """测试引擎初始化"""
        self.assertEqual(self.engine.engine_name, "BasicIsolationEngine")
        self.assertIn("filesystem_isolation", self.engine.supported_features)
        self.assertTrue(self.engine.validate_config())

    def test_create_environment(self):
        """测试创建环境"""
        env_path = Path(self.test_dir) / "test_env"
        env = self.engine.create_isolation(env_path, "test_env_123", {})

        self.assertIsNotNone(env)
        self.assertEqual(env.env_id, "test_env_123")
        self.assertEqual(env.path, env_path)
        self.assertTrue(env_path.exists())

        # 检查目录结构
        expected_dirs = ["bin", "lib", "logs", "temp", "data"]
        for dir_name in expected_dirs:
            self.assertTrue((env_path / dir_name).exists())

        # 清理
        self.engine.cleanup_isolation(env)

    def test_activate_deactivate_environment(self):
        """测试激活和停用环境"""
        env_path = Path(self.test_dir) / "test_env"
        env = self.engine.create_isolation(env_path, "test_env_123", {})

        # 激活环境
        success = env.activate()
        self.assertTrue(success)
        self.assertEqual(env.status, EnvironmentStatus.ACTIVE)
        self.assertIsNotNone(env.activated_at)

        # 停用环境
        success = env.deactivate()
        self.assertTrue(success)
        self.assertEqual(env.status, EnvironmentStatus.INACTIVE)
        self.assertIsNotNone(env.deactivated_at)

        # 清理
        self.engine.cleanup_isolation(env)

    def test_execute_command(self):
        """测试执行命令"""
        env_path = Path(self.test_dir) / "test_env"
        env = self.engine.create_isolation(env_path, "test_env_123", {})

        # 执行简单命令
        result = env.execute_command(["echo", "hello"])
        self.assertTrue(result.success)
        self.assertEqual(result.stdout.strip(), "hello")
        self.assertEqual(result.returncode, 0)

        # 清理
        self.engine.cleanup_isolation(env)

    def test_port_allocation(self):
        """测试端口分配"""
        env_path = Path(self.test_dir) / "test_env"
        env = self.engine.create_isolation(env_path, "test_env_123", {})

        # 分配端口
        port1 = env.allocate_port()
        port2 = env.allocate_port()

        self.assertIsNotNone(port1)
        self.assertIsNotNone(port2)
        self.assertNotEqual(port1, port2)
        self.assertIn(port1, env.allocated_ports)
        self.assertIn(port2, env.allocated_ports)

        # 释放端口
        success = env.release_port(port1)
        self.assertTrue(success)
        self.assertNotIn(port1, env.allocated_ports)

        # 清理
        self.engine.cleanup_isolation(env)

    def test_validate_isolation(self):
        """测试隔离验证"""
        env_path = Path(self.test_dir) / "test_env"
        env = self.engine.create_isolation(env_path, "test_env_123", {})

        # 验证隔离
        is_valid = env.validate_isolation()
        self.assertTrue(is_valid)

        # 删除一个必需目录
        (env_path / "logs").rmdir()
        is_valid = env.validate_isolation()
        self.assertFalse(is_valid)

        # 清理
        self.engine.cleanup_isolation(env)


class TestEnvironmentFeatures(unittest.TestCase):
    """环境功能测试"""

    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp(prefix="ptest_env_features_test_")
        self.config = {"basic": {"enabled": True}}
        self.manager = IsolationManager(self.config)

    def tearDown(self):
        """测试后清理"""
        self.manager.cleanup_all_environments()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_environment_status_tracking(self):
        """测试环境状态跟踪"""
        env_path = Path(self.test_dir) / "test_env"
        env = self.manager.create_environment(env_path, isolation_level="basic")

        # 初始状态
        self.assertEqual(env.status, EnvironmentStatus.CREATED)

        # 激活后状态
        env.activate()
        self.assertEqual(env.status, EnvironmentStatus.ACTIVE)

        # 状态信息
        status = env.get_status()
        self.assertEqual(status["env_id"], env.env_id)
        self.assertEqual(status["status"], EnvironmentStatus.ACTIVE.value)
        self.assertIn("created_at", status)
        self.assertIn("activated_at", status)

    def test_manager_status(self):
        """测试管理器状态"""
        env_path = Path(self.test_dir) / "test_env"
        self.manager.create_environment(env_path, isolation_level="basic")

        status = self.manager.get_manager_status()

        self.assertEqual(status["total_environments"], 1)
        self.assertIn("available_engines", status)
        self.assertIn("basic", status["available_engines"])
        self.assertIn("environments_by_engine", status)


if __name__ == "__main__":
    unittest.main()
