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

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ptest.isolation.engine_registry import (
    EngineRegistry,
    get_global_registry,
)
from ptest.isolation.registry import list_available_engines as global_list
from ptest.isolation.base import IsolationEngine, IsolatedEnvironment


class TestEngineRegistry(unittest.TestCase):
    """测试引擎注册表功能"""

    def setUp(self):
        """设置测试环境"""
        self.registry = EngineRegistry()

    def test_register_builtin_engines(self):
        """测试内置引擎注册"""
        # 触发内置引擎加载
        count = self.registry.discover_engines()

        # 应该注册了3个内置引擎
        engines = self.registry.list_engines()
        self.assertGreaterEqual(len(engines), 3)

        # 检查必需的引擎
        required_engines = ["basic", "virtualenv", "docker"]
        for engine in required_engines:
            self.assertIn(engine, engines)
            engine_info = engines[engine]
            self.assertIsNotNone(engine_info)
            self.assertEqual(engine_info["class_name"], engine_info["module"])

    def test_register_custom_engine(self):
        """测试自定义引擎注册"""

        class CustomEngine(IsolationEngine):
            engine_name = "custom_test"
            isolation_level = "custom"

            def __init__(self, config):
                self.config = config
                self.engine_name = "custom_test"
                self.isolation_level = "custom"
                self.created_environments = {}

            def create_isolation(self, path, env_id, config):
                return None

            def cleanup_isolation(self, env):
                return True

            def activate(self):
                return True

            def deactivate(self):
                return True

            def execute_command(self, cmd, timeout=None, env_vars=None, cwd=None):
                from ptest.isolation.base import ProcessResult

                return ProcessResult(returncode=0)

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
                return ["test_feature"]

        # 注册自定义引擎
        success = self.registry.register_engine(
            name="custom_test",
            engine_class=CustomEngine,
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

        class HighPriorityEngine(IsolationEngine):
            engine_name = "high_priority"
            isolation_level = "high"

            def __init__(self, config):
                pass

            def create_isolation(self, path, env_id, config):
                pass

            def cleanup_isolation(self, env):
                return True

            def activate(self):
                return True

            def deactivate(self):
                return True

            def execute_command(self, cmd, timeout=None, env_vars=None, cwd=None):
                from ptest.isolation.base import ProcessResult

                return ProcessResult(returncode=0)

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
                return []

        # 注册高优先级引擎
        self.registry.register_engine(
            name="high_priority",
            engine_class=HighPriorityEngine,
            priority=1,  # 最高优先级
        )

        # 注册低优先级引擎
        self.registry.register_engine(
            name="low_priority",
            engine_class=HighPriorityEngine,
            priority=100,  # 最低优先级
        )

        engines = self.registry.list_engines()

        # 检查优先级排序
        engine_names = list(engines.keys())
        self.assertEqual(engine_names[0], "basic")  # 内置引擎优先级10
        self.assertEqual(engine_names[-1], "low_priority")  # 最低优先级

    def test_engine_creation_and_destruction(self):
        """测试引擎创建和销毁"""

        # 注册测试引擎
        class TestEngine(IsolationEngine):
            engine_name = "test_creation"
            isolation_level = "test"
            created = False
            destroyed = False

            def __init__(self, config):
                self.config = config
                self.engine_name = "test_creation"
                self.isolation_level = "test"
                self.created_environments = {}

            def create_isolation(self, path, env_id, config):
                self.created = True
                return TestEnvironment(self, env_id)

            def cleanup_isolation(self, env):
                self.destroyed = True
                return True

            def activate(self):
                return True

            def deactivate(self):
                return True

            def execute_command(self, cmd, timeout=None, env_vars=None, cwd=None):
                from ptest.isolation.base import ProcessResult

                return ProcessResult(returncode=0)

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
                return []

        self.registry.register_engine(name="test_creation", engine_class=TestEngine)

        # 创建引擎实例
        engine = self.registry.create_engine("test_creation")
        self.assertIsNotNone(engine)
        self.assertTrue(engine.created)

        # 销毁引擎实例
        success = self.registry.destroy_engine("test_creation")
        self.assertTrue(success)
        self.assertTrue(engine.destroyed)

    def test_dependency_management(self):
        """测试依赖管理"""
        # 清理注册表
        self.registry.cleanup()

        # 注册有依赖的引擎
        class DependentEngine(IsolationEngine):
            engine_name = "dependent"
            isolation_level = "dependent"

            def __init__(self, config):
                pass

            def create_isolation(self, path, env_id, config):
                pass

            def cleanup_isolation(self, env):
                return True

            def activate(self):
                return True

            def deactivate(self):
                return True

            def execute_command(self, cmd, timeout=None, env_vars=None, cwd=None):
                from ptest.isolation.base import ProcessResult

                return ProcessResult(returncode=0)

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
                return []

        # 尝试注册依赖不存在的引擎（应该失败）
        success = self.registry.register_engine(
            name="dependent",
            engine_class=DependentEngine,
            dependencies=["nonexistent_engine"],
        )
        self.assertFalse(success)

        # 先注册基础引擎
        class BaseEngine(IsolationEngine):
            engine_name = "base"
            isolation_level = "base"

            def __init__(self, config):
                pass

            def create_isolation(self, path, env_id, config):
                pass

            def cleanup_isolation(self, env):
                return True

            def activate(self):
                return True

            def deactivate(self):
                return True

            def execute_command(self, cmd, timeout=None, env_vars=None, cwd=None):
                from ptest.isolation.base import ProcessResult

                return ProcessResult(returncode=0)

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
                return []

        self.registry.register_engine(name="base", engine_class=BaseEngine)

        # 现在应该可以注册依赖引擎
        success = self.registry.register_engine(
            name="dependent", engine_class=DependentEngine, dependencies=["base"]
        )
        self.assertTrue(success)

    def test_global_registry_functions(self):
        """测试全局注册表便捷函数"""
        from ptest.isolation.registry import (
            register_engine as global_register,
            create_engine as global_create,
            list_available_engines as global_list,
        )

        # 全局函数应该与注册表实例同步
        local_engines = self.registry.list_engines()
        global_engines = global_list()

        self.assertEqual(len(local_engines), len(global_engines))

        # 检查引擎一致性
        for name in local_engines:
            self.assertIn(name, global_engines)

    def test_dependency_graph_and_load_order(self):
        """测试依赖图和加载顺序"""
        # 清理注册表
        self.registry.cleanup()

        # 创建有依赖关系的引擎
        self.registry.register_engine(name="engine_a", priority=30, engine_class=object)
        self.registry.register_engine(
            name="engine_b", priority=20, dependencies=["engine_a"], engine_class=object
        )
        self.registry.register_engine(
            name="engine_c", priority=10, dependencies=["engine_b"], engine_class=object
        )

        # 获取依赖图
        graph = self.registry.get_dependency_graph()
        self.assertEqual(graph["engine_a"], [])
        self.assertEqual(graph["engine_b"], ["engine_a"])
        self.assertEqual(graph["engine_c"], ["engine_b"])

        # 获取加载顺序（拓扑排序）
        load_order = self.registry.get_load_order()
        self.assertEqual(load_order, ["engine_a", "engine_b", "engine_c"])


class TestEnvironment(IsolatedEnvironment):
    """测试环境实现"""

    def __init__(self, env_id):
        self.env_id = env_id
        self.status = None


if __name__ == "__main__":
    unittest.main()
