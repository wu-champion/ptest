"""
隔离管理器测试

测试IsolationManager的各项功能，包括引擎管理、环境创建、自动选择等
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from isolation.manager import IsolationManager
    from isolation.enums import IsolationLevel, EnvironmentStatus
except ImportError:
    try:
        from pypj.ptest.isolation.manager import IsolationManager
        from pypj.ptest.isolation.enums import IsolationLevel, EnvironmentStatus
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        from isolation.manager import IsolationManager
        from isolation.enums import IsolationLevel, EnvironmentStatus


class TestIsolationManager(unittest.TestCase):
    """隔离管理器测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager(
            {
                "default_isolation_level": IsolationLevel.VIRTUALENV.value,
                "max_environments": 10,
                "cleanup_policy": "on_request",
            }
        )

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        try:
            self.manager.cleanup_all_environments(force=True)
        except:
            pass

    def test_manager_initialization(self):
        """测试管理器初始化"""
        self.assertIsNotNone(self.manager)
        self.assertEqual(len(self.manager.engines), 3)  # basic, virtualenv, docker
        self.assertEqual(
            self.manager.default_isolation_level, IsolationLevel.VIRTUALENV.value
        )
        self.assertEqual(self.manager.max_environments, 10)

    def test_engine_registration(self):
        """测试引擎注册"""
        # 检查内置引擎是否注册
        self.assertIn(IsolationLevel.BASIC.value, self.manager.engines)
        self.assertIn(IsolationLevel.VIRTUALENV.value, self.manager.engines)
        self.assertIn(IsolationLevel.DOCKER.value, self.manager.engines)

    def test_create_environment_basic(self):
        """测试基础环境创建"""
        env_path = self.temp_dir / "basic_test"
        env = self.manager.create_environment(env_path)

        self.assertIsNotNone(env)
        self.assertEqual(env.env_id[:4], "env_")  # 环境ID格式检查
        self.assertIn(env.env_id, self.manager.active_environments)

    def test_create_environment_with_level(self):
        """测试指定隔离级别创建环境"""
        env_path = self.temp_dir / "basic_level_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        self.assertIsNotNone(env)
        self.assertIsNotNone(env.isolation_engine)

    def test_unsupported_isolation_level(self):
        """测试不支持的隔离级别"""
        env_path = self.temp_dir / "unsupported_test"

        with self.assertRaises(ValueError):
            self.manager.create_environment(env_path, "unsupported_level")

    def test_max_environments_limit(self):
        """测试最大环境数量限制"""
        # 创建小限制的管理器
        small_manager = IsolationManager(
            {
                "max_environments": 2,
            }
        )

        try:
            # 创建最大数量的环境
            for i in range(2):
                env_path = self.temp_dir / f"max_test_{i}"
                small_manager.create_environment(env_path)

            # 尝试创建超出限制的环境
            env_path = self.temp_dir / "overflow_test"
            with self.assertRaises(RuntimeError):
                small_manager.create_environment(env_path)
        finally:
            small_manager.cleanup_all_environments(force=True)

    def test_get_environment(self):
        """测试获取环境"""
        env_path = self.temp_dir / "get_test"
        env = self.manager.create_environment(env_path)
        env_id = env.env_id

        # 获取环境
        retrieved_env = self.manager.get_environment(env_id)
        self.assertEqual(retrieved_env, env)

        # 获取不存在的环境
        non_existent = self.manager.get_environment("non_existent")
        self.assertIsNone(non_existent)

    def test_cleanup_environment(self):
        """测试环境清理"""
        env_path = self.temp_dir / "cleanup_test"
        env = self.manager.create_environment(env_path)
        env_id = env.env_id

        # 清理环境
        success = self.manager.cleanup_environment(env_id)
        self.assertTrue(success)
        self.assertNotIn(env_id, self.manager.active_environments)

    def test_list_environments(self):
        """测试列出环境"""
        # 创建多个环境
        env_ids = []
        for i in range(3):
            env_path = self.temp_dir / f"list_test_{i}"
            env = self.manager.create_environment(env_path)
            env_ids.append(env.env_id)

        # 列出环境
        env_list = self.manager.list_environments()
        self.assertEqual(len(env_list), 3)

        for env_id in env_ids:
            self.assertIn(env_id, env_list)

    def test_get_manager_status(self):
        """测试获取管理器状态"""
        status = self.manager.get_manager_status()

        self.assertIsInstance(status, dict)
        self.assertIn("total_environments", status)
        self.assertIn("max_environments", status)
        self.assertIn("available_engines", status)
        self.assertIn("default_isolation_level", status)

    def test_set_default_isolation_level(self):
        """测试设置默认隔离级别"""
        # 设置新的默认级别
        self.manager.set_default_isolation_level(IsolationLevel.BASIC.value)
        self.assertEqual(
            self.manager.default_isolation_level, IsolationLevel.BASIC.value
        )

        # 测试无效级别
        with self.assertRaises(ValueError):
            self.manager.set_default_isolation_level("invalid_level")

    def test_update_config(self):
        """测试更新配置"""
        new_config = {
            "max_environments": 20,
            "cleanup_policy": "auto",
        }

        self.manager.update_config(new_config)
        self.assertEqual(self.manager.max_environments, 20)
        self.assertEqual(self.manager.cleanup_policy, "auto")

    def test_find_environments_by_path(self):
        """测试根据路径查找环境"""
        env_path = self.temp_dir / "find_test"
        env = self.manager.create_environment(env_path)

        # 查找环境
        found_envs = self.manager.find_environments_by_path(env_path)
        self.assertEqual(len(found_envs), 1)
        self.assertEqual(found_envs[0], env.env_id)

    def test_get_environment_resource_usage(self):
        """测试获取环境资源使用情况"""
        env_path = self.temp_dir / "resource_test"
        env = self.manager.create_environment(env_path)

        # 获取资源使用情况
        usage = self.manager.get_environment_resource_usage(env.env_id)
        self.assertIsInstance(usage, dict)
        self.assertIn("cpu_percent", usage)
        self.assertIn("memory_mb", usage)

    def test_context_manager(self):
        """测试上下文管理器"""
        with IsolationManager() as manager:
            # 创建环境
            env_path = self.temp_dir / "context_test"
            env = manager.create_environment(env_path)
            self.assertIsNotNone(env)
            self.assertIn(env.env_id, manager.active_environments)

        # 退出上下文后，环境应该被清理
        self.assertNotIn(env.env_id, manager.active_environments)


class TestAutoSelection(unittest.TestCase):
    """自动隔离级别选择测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager()

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        try:
            self.manager.cleanup_all_environments(force=True)
        except:
            pass

    def test_auto_select_docker_for_container(self):
        """测试容器需求自动选择Docker"""
        requirements = {
            "container_required": True,
        }

        level = self.manager.auto_select_isolation_level(requirements)
        self.assertEqual(level, IsolationLevel.DOCKER.value)

    def test_auto_select_docker_for_network_isolation(self):
        """测试网络隔离需求自动选择Docker"""
        requirements = {
            "network_isolation": True,
        }

        level = self.manager.auto_select_isolation_level(requirements)
        self.assertEqual(level, IsolationLevel.DOCKER.value)

    def test_auto_select_docker_for_custom_image(self):
        """测试自定义镜像需求自动选择Docker"""
        requirements = {
            "custom_image": "my-custom-image:latest",
        }

        level = self.manager.auto_select_isolation_level(requirements)
        self.assertEqual(level, IsolationLevel.DOCKER.value)

    def test_auto_select_docker_for_high_security(self):
        """测试高安全需求自动选择Docker"""
        requirements = {
            "security_level": "high",
        }

        level = self.manager.auto_select_isolation_level(requirements)
        self.assertEqual(level, IsolationLevel.DOCKER.value)

    def test_auto_select_virtualenv_for_python_isolation(self):
        """测试Python隔离需求自动选择Virtualenv"""
        requirements = {
            "python_isolation": True,
        }

        level = self.manager.auto_select_isolation_level(requirements)
        self.assertEqual(level, IsolationLevel.VIRTUALENV.value)

    def test_auto_select_virtualenv_for_medium_security(self):
        """测试中等安全需求自动选择Virtualenv"""
        requirements = {
            "security_level": "medium",
        }

        level = self.manager.auto_select_isolation_level(requirements)
        self.assertEqual(level, IsolationLevel.VIRTUALENV.value)

    def test_auto_select_for_resource_limits(self):
        """测试资源限制需求自动选择Docker"""
        requirements = {
            "resource_limits": {
                "memory": "512m",
                "cpu": "1.0",
            },
        }

        level = self.manager.auto_select_isolation_level(requirements)
        self.assertEqual(level, IsolationLevel.DOCKER.value)

    def test_create_environment_with_auto_selection(self):
        """测试自动选择创建环境"""
        requirements = {
            "python_isolation": True,
        }

        env_path = self.temp_dir / "auto_test"
        env = self.manager.create_environment_with_auto_selection(
            env_path, requirements
        )

        self.assertIsNotNone(env)
        self.assertEqual(
            env.config.get("auto_selected_level"), IsolationLevel.VIRTUALENV.value
        )


class TestEnvironmentMigration(unittest.TestCase):
    """环境迁移测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager()

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        try:
            self.manager.cleanup_all_environments(force=True)
        except:
            pass

    def test_migrate_environment_success(self):
        """测试成功迁移环境"""
        # 创建源环境
        env_path = self.temp_dir / "migration_test"
        source_env = self.manager.create_environment(
            env_path, IsolationLevel.BASIC.value
        )
        source_env_id = source_env.env_id

        # 迁移到Virtualenv
        new_env = self.manager.migrate_environment(
            source_env_id, IsolationLevel.VIRTUALENV.value, copy_files=True
        )

        self.assertIsNotNone(new_env)
        self.assertNotEqual(new_env.env_id, source_env_id)
        self.assertNotIn(source_env_id, self.manager.active_environments)
        self.assertIn(new_env.env_id, self.manager.active_environments)

    def test_migrate_nonexistent_environment(self):
        """测试迁移不存在的环境"""
        with self.assertRaises(ValueError):
            self.manager.migrate_environment(
                "nonexistent", IsolationLevel.VIRTUALENV.value
            )

    def test_migrate_to_same_level(self):
        """测试迁移到相同级别"""
        env_path = self.temp_dir / "same_level_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 迁移到相同级别应该返回原环境
        migrated_env = self.manager.migrate_environment(
            env.env_id, IsolationLevel.BASIC.value
        )

        self.assertEqual(migrated_env, env)


class TestEngineCompatibility(unittest.TestCase):
    """引擎兼容性测试"""

    def setUp(self):
        """测试前准备"""
        self.manager = IsolationManager()

    def test_get_engine_info(self):
        """测试获取引擎信息"""
        info = self.manager.get_engine_info(IsolationLevel.VIRTUALENV.value)
        self.assertIsInstance(info, dict)
        self.assertIn("name", info)
        self.assertIn("supported_features", info)

    def test_list_available_engines(self):
        """测试列出可用引擎"""
        engines = self.manager.list_available_engines()
        self.assertIsInstance(engines, dict)
        self.assertIn(IsolationLevel.BASIC.value, engines)
        self.assertIn(IsolationLevel.VIRTUALENV.value, engines)
        self.assertIn(IsolationLevel.DOCKER.value, engines)

    def test_get_engine_compatibility_matrix(self):
        """测试获取引擎兼容性矩阵"""
        matrix = self.manager.get_engine_compatibility_matrix()
        self.assertIsInstance(matrix, dict)

        # 检查基本兼容性信息
        self.assertIn("basic", matrix)
        self.assertIn("name", matrix["basic"])
        self.assertIn("features", matrix["basic"])
        self.assertIn("resource_requirements", matrix["basic"])
        self.assertIn("isolation_strength", matrix["basic"])


class TestBenchmarking(unittest.TestCase):
    """基准测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager()

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        try:
            self.manager.cleanup_all_environments(force=True)
        except:
            pass

    def test_benchmark_engines(self):
        """测试引擎基准测试"""
        results = self.manager.benchmark_engines(["creation"])
        self.assertIsInstance(results, dict)

        # 应该包含所有引擎的结果
        for level in [IsolationLevel.BASIC.value, IsolationLevel.VIRTUALENV.value]:
            self.assertIn(level, results)
            self.assertIn("benchmarks", results[level])
            self.assertIn("creation_time", results[level]["benchmarks"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
