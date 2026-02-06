"""
测试统一引擎注册机制

验证 EngineRegistry 的功能：
- 引擎注册和发现
- 依赖管理
- 动态加载
- 优先级排序
"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ptest.isolation.engine_registry import (
    EngineRegistry,
)
from ptest.isolation.registry import list_available_engines as global_list
from ptest.isolation.base import IsolationEngine, IsolatedEnvironment, ProcessResult
from ptest.isolation.enums import EnvironmentStatus


class MockEngine(IsolationEngine):
    """完整的模拟引擎类，用于测试"""

    engine_name = "mock"
    isolation_level = "mock"

    def __init__(self, config=None):
        self.config = config or {}
        self.created = False
        self.destroyed = False
        self.created_environments = {}

    def create_isolation(self, path, env_id, isolation_config=None):
        self.created = True
        env = MockIsolatedEnvironment(env_id, path, self)
        self.created_environments[env_id] = env
        return env

    def cleanup_isolation(self, env):
        self.destroyed = True
        if env.env_id in self.created_environments:
            del self.created_environments[env.env_id]
        return True

    def activate(self):
        return True

    def deactivate(self):
        return True

    def execute_command(self, cmd, timeout=None, env_vars=None, cwd=None, **kwargs):
        return ProcessResult(returncode=0, stdout="", stderr="")

    def install_package(self, package, version=None, upgrade=False):
        return True

    def uninstall_package(self, package):
        return True

    def get_installed_packages(self):
        return {}

    def get_package_version(self, package):
        return None

    def allocate_port(self):
        return 8080

    def release_port(self, port):
        return True

    def get_supported_features(self):
        return ["mock_feature"]

    def validate_isolation(self):
        return True

    def get_isolation_status(self):
        return {"status": "active"}

    def check_environment_health(self):
        return {"healthy": True}

    def get_environment_metrics(self):
        return {}


class MockIsolatedEnvironment(IsolatedEnvironment):
    """模拟隔离环境"""

    def __init__(self, env_id, path, engine):
        super().__init__(env_id, path, engine, {})
        self.status = EnvironmentStatus.CREATED

    def activate(self):
        self.status = EnvironmentStatus.ACTIVE
        return True

    def deactivate(self):
        self.status = EnvironmentStatus.INACTIVE
        return True

    def validate_isolation(self):
        return True

    def get_isolation_info(self):
        return {"env_id": self.env_id, "status": str(self.status)}


class TestEngineRegistry(unittest.TestCase):
    """测试引擎注册表功能"""

    def setUp(self):
        """设置测试环境"""
        self.registry = EngineRegistry()
        self.registry.discover_engines()

    def tearDown(self):
        """清理测试环境"""
        self.registry.cleanup()

    def test_register_builtin_engines(self):
        """测试内置引擎注册"""
        engines = self.registry.list_engines()

        # 应该注册了3个内置引擎
        self.assertGreaterEqual(len(engines), 3)

        # 检查必需的引擎
        required_engines = ["basic", "virtualenv", "docker"]
        for engine in required_engines:
            self.assertIn(engine, engines)
            engine_info = engines[engine]
            self.assertIsNotNone(engine_info)
            # class_name 和 module 是不同的值
            self.assertIn("class_name", engine_info)
            self.assertIn("module", engine_info)
            # class_name 是类名，module 是模块路径
            self.assertNotEqual(engine_info["class_name"], engine_info["module"])

    def test_register_custom_engine(self):
        """测试自定义引擎注册"""
        # 注册自定义引擎
        success = self.registry.register_engine(
            name="custom_test",
            engine_class=MockEngine,
            description="测试引擎",
            version="1.0.0",
            author="test",
            supported_features=["test_feature"],
            priority=50,
        )

        self.assertTrue(success)

        # 验证引擎已注册
        engine_info = self.registry.get_engine_info("custom_test")
        self.assertIsNotNone(engine_info)
        self.assertEqual(engine_info.name, "custom_test")
        self.assertEqual(engine_info.version, "1.0.0")

    def test_engine_priority_ordering(self):
        """测试引擎优先级排序"""
        # 清理并重新注册
        self.registry.cleanup()

        # 注册高优先级引擎（数字越小优先级越高）
        self.registry.register_engine(
            name="high_priority",
            engine_class=MockEngine,
            priority=1,  # 最高优先级
        )

        # 注册低优先级引擎
        self.registry.register_engine(
            name="low_priority",
            engine_class=MockEngine,
            priority=100,  # 最低优先级
        )

        engines = self.registry.list_engines()
        engine_names = list(engines.keys())

        # 高优先级应该排在前面
        high_priority_idx = engine_names.index("high_priority")
        low_priority_idx = engine_names.index("low_priority")
        self.assertLess(high_priority_idx, low_priority_idx)

    def test_engine_creation_and_destruction(self):
        """测试引擎创建和销毁"""
        # 注册测试引擎
        self.registry.register_engine(name="test_creation", engine_class=MockEngine)

        # 创建引擎实例
        engine = self.registry.create_engine("test_creation")
        self.assertIsNotNone(engine)
        self.assertIsInstance(engine, MockEngine)

        # 销毁引擎实例
        success = self.registry.destroy_engine("test_creation")
        self.assertTrue(success)

    def test_dependency_management(self):
        """测试依赖管理"""
        # 清理注册表
        self.registry.cleanup()

        # 尝试注册依赖不存在的引擎（应该失败）
        success = self.registry.register_engine(
            name="dependent",
            engine_class=MockEngine,
            dependencies=["nonexistent_engine"],
        )
        self.assertFalse(success)

        # 先注册基础引擎
        self.registry.register_engine(name="base", engine_class=MockEngine)

        # 现在应该可以注册依赖引擎
        success = self.registry.register_engine(
            name="dependent", engine_class=MockEngine, dependencies=["base"]
        )
        self.assertTrue(success)

    def test_global_registry_functions(self):
        """测试全局注册表便捷函数"""
        # 确保本地注册表已发现引擎
        local_engines = self.registry.list_engines()

        # 获取全局引擎列表
        global_engines = global_list()

        # 两者都应该包含基本引擎
        self.assertGreater(len(local_engines), 0)
        self.assertGreater(len(global_engines), 0)

    def test_dependency_graph_and_load_order(self):
        """测试依赖图和加载顺序"""
        # 清理注册表
        self.registry.cleanup()

        # 注册带依赖关系的引擎
        self.registry.register_engine(
            name="engine_a", engine_class=MockEngine, priority=30
        )
        self.registry.register_engine(
            name="engine_b",
            engine_class=MockEngine,
            priority=20,
            dependencies=["engine_a"],
        )
        self.registry.register_engine(
            name="engine_c",
            engine_class=MockEngine,
            priority=10,
            dependencies=["engine_b"],
        )

        # 获取依赖图
        graph = self.registry.get_dependency_graph()
        self.assertEqual(graph["engine_a"], [])
        self.assertEqual(graph["engine_b"], ["engine_a"])
        self.assertEqual(graph["engine_c"], ["engine_b"])

        # 获取加载顺序（拓扑排序）
        load_order = self.registry.get_load_order()
        # 检查依赖顺序正确
        idx_a = load_order.index("engine_a")
        idx_b = load_order.index("engine_b")
        idx_c = load_order.index("engine_c")
        self.assertLess(idx_a, idx_b)
        self.assertLess(idx_b, idx_c)


if __name__ == "__main__":
    unittest.main()
