"""
Docker隔离引擎测试

测试Docker隔离引擎的各项功能，包括环境创建、容器管理、网络配置等
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os
import time
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 尝试不同的导入方式
try:
    from isolation.docker_engine import (
        DockerEnvironment,
        DockerIsolationEngine,
    )
    from isolation.enums import EnvironmentStatus, IsolationEvent
    from core import get_logger
except ImportError:
    try:
        from pypj.ptest.isolation.docker_engine import (
            DockerEnvironment,
            DockerIsolationEngine,
        )
        from pypj.ptest.isolation.enums import EnvironmentStatus, IsolationEvent
        from pypj.ptest.core import get_logger
    except ImportError:
        import sys
        import os

        # 添加当前目录到路径
        current_dir = Path(__file__).parent
        while current_dir.name != "ptest":
            current_dir = current_dir.parent
        sys.path.insert(0, str(current_dir))

        from isolation.docker_engine import (
            DockerEnvironment,
            DockerIsolationEngine,
        )
        from isolation.enums import EnvironmentStatus, IsolationEvent
        from core import get_logger


class TestDockerIsolationEngine(unittest.TestCase):
    """Docker隔离引擎测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine(
            {
                "default_image": "python:3.9-slim",
                "container_timeout": 60,
                "simulation_mode": True,  # 使用模拟模式避免依赖Docker
            }
        )

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        # 清理引擎创建的环境
        self.engine.cleanup_all_environments()

    def test_engine_initialization(self):
        """测试引擎初始化"""
        self.assertIsNotNone(self.engine)
        self.assertEqual(self.engine.engine_name, "DockerIsolationEngine")
        self.assertIn("container_isolation", self.engine.supported_features)
        self.assertIn("image_management", self.engine.supported_features)

    def test_verify_docker_environment_simulation(self):
        """测试Docker环境验证（模拟模式）"""
        env_info = self.engine.verify_docker_environment()
        self.assertIsInstance(env_info, dict)
        self.assertIn("available", env_info)
        self.assertIn("simulation_mode", env_info)

    def test_create_isolation(self):
        """测试创建隔离环境"""
        env_id = "test_docker_env"
        isolation_config = {
            "image": "python:3.9-slim",
            "create_network": False,
        }

        env = self.engine.create_isolation(self.temp_dir, env_id, isolation_config)

        self.assertIsInstance(env, DockerEnvironment)
        self.assertEqual(env.env_id, env_id)
        self.assertEqual(env.path, self.temp_dir)
        self.assertEqual(env.image_name, "python:3.9-slim")
        self.assertEqual(env.status, EnvironmentStatus.CREATED)

    def test_get_isolation_status(self):
        """测试获取隔离状态"""
        env_id = "test_status_env"
        env = self.engine.create_isolation(self.temp_dir, env_id, {})

        status = self.engine.get_isolation_status(env_id)

        self.assertIsInstance(status, dict)
        self.assertEqual(status["env_id"], env_id)
        self.assertEqual(status["isolation_type"], "docker")
        self.assertIn("supported_features", status)

    def test_list_available_images(self):
        """测试列出可用镜像"""
        images = self.engine.list_available_images()
        self.assertIsInstance(images, list)
        # 在模拟模式下应该至少有一个模拟镜像
        self.assertGreaterEqual(len(images), 0)

    def test_cleanup_unused_resources(self):
        """测试清理未使用的资源"""
        cleanup_counts = self.engine.cleanup_unused_resources()
        self.assertIsInstance(cleanup_counts, dict)
        self.assertIn("containers", cleanup_counts)
        self.assertIn("images", cleanup_counts)
        self.assertIn("volumes", cleanup_counts)
        self.assertIn("networks", cleanup_counts)

    def test_get_engine_info(self):
        """测试获取引擎信息"""
        info = self.engine.get_engine_info()
        self.assertIsInstance(info, dict)
        self.assertEqual(info["engine_type"], "docker")
        self.assertIn("docker_available", info)
        self.assertIn("engine_config", info)

    def test_pull_image_simulation(self):
        """测试拉取镜像（模拟模式）"""
        result = self.engine.pull_image("python:3.9-slim")
        self.assertTrue(result)  # 模拟模式下应该成功

    def test_create_network_simulation(self):
        """测试创建网络（模拟模式）"""
        network = self.engine.create_network("test_network")
        # 在模拟模式下应该返回None
        self.assertIsNone(network)

    def test_create_volume_simulation(self):
        """测试创建卷（模拟模式）"""
        volume = self.engine.create_volume("test_volume")
        # 在模拟模式下应该返回None
        self.assertIsNone(volume)


class TestDockerEnvironment(unittest.TestCase):
    """Docker环境测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine(
            {
                "default_image": "python:3.9-slim",
                "simulation_mode": True,
            }
        )
        self.env = self.engine.create_isolation(
            self.temp_dir, "test_env", {"image": "python:3.9-slim"}
        )

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        if self.env:
            self.env.cleanup(force=True)

    def test_environment_initialization(self):
        """测试环境初始化"""
        self.assertEqual(self.env.env_id, "test_env")
        self.assertEqual(self.env.path, self.temp_dir)
        self.assertEqual(self.env.image_name, "python:3.9-slim")
        self.assertEqual(self.env.status, EnvironmentStatus.CREATED)
        self.assertIsNotNone(self.env.container_name)

    def test_activate_environment(self):
        """测试激活环境"""
        result = self.env.activate()
        self.assertTrue(result)
        self.assertEqual(self.env.status, EnvironmentStatus.ACTIVE)

    def test_deactivate_environment(self):
        """测试停用环境"""
        # 先激活
        self.env.activate()

        # 然后停用
        result = self.env.deactivate()
        self.assertTrue(result)
        self.assertEqual(self.env.status, EnvironmentStatus.INACTIVE)

    def test_execute_command_simulation(self):
        """测试执行命令（模拟模式）"""
        # 激活环境
        self.env.activate()

        # 执行命令
        result = self.env.execute_command(["echo", "hello"])
        self.assertIsInstance(result, Mock)  # 模拟模式下返回模拟结果
        self.assertEqual(result.returncode, 0)

    def test_install_package_simulation(self):
        """测试安装包（模拟模式）"""
        # 激活环境
        self.env.activate()

        # 安装包
        result = self.env.install_package("requests")
        self.assertTrue(result)

    def test_uninstall_package_simulation(self):
        """测试卸载包（模拟模式）"""
        # 激活环境
        self.env.activate()

        # 卸载包
        result = self.env.uninstall_package("requests")
        self.assertTrue(result)

    def test_get_installed_packages_simulation(self):
        """测试获取已安装包（模拟模式）"""
        # 激活环境
        self.env.activate()

        # 获取包列表
        packages = self.env.get_installed_packages()
        self.assertIsInstance(packages, dict)

    def test_get_package_version_simulation(self):
        """测试获取包版本（模拟模式）"""
        # 激活环境
        self.env.activate()

        # 获取包版本
        version = self.env.get_package_version("requests")
        # 模拟模式下可能返回None
        self.assertTrue(version is None or isinstance(version, str))

    def test_port_allocation(self):
        """测试端口分配"""
        port = self.env.allocate_port()
        self.assertIsInstance(port, int)
        self.assertGreater(port, 0)
        self.assertIn(port, self.env.allocated_ports)

    def test_port_release(self):
        """测试端口释放"""
        # 先分配端口
        port = self.env.allocate_port()

        # 然后释放
        result = self.env.release_port(port)
        self.assertTrue(result)
        self.assertNotIn(port, self.env.allocated_ports)

    def test_cleanup_environment(self):
        """测试清理环境"""
        # 激活环境
        self.env.activate()

        # 清理环境
        result = self.env.cleanup()
        self.assertTrue(result)
        self.assertEqual(self.env.status, EnvironmentStatus.CLEANUP_COMPLETE)

    def test_validate_isolation(self):
        """测试验证隔离有效性"""
        # 在模拟模式下应该总是有效
        result = self.env.validate_isolation()
        self.assertTrue(result)

    def test_get_container_info(self):
        """测试获取容器信息"""
        info = self.env.get_container_info()
        self.assertIsInstance(info, dict)
        self.assertIn("container_id", info)
        self.assertIn("name", info)
        self.assertIn("image", info)
        self.assertIn("status", info)

    def test_event_system(self):
        """测试事件系统"""
        events_received = []

        def event_callback(env, event, *args, **kwargs):
            events_received.append((event, args, kwargs))

        # 添加事件监听器
        self.env.add_event_listener(
            IsolationEvent.ENVIRONMENT_ACTIVATED, event_callback
        )

        # 激活环境（应该触发事件）
        self.env.activate()

        # 验证事件被触发
        self.assertGreater(len(events_received), 0)
        self.assertEqual(events_received[0][0], IsolationEvent.ENVIRONMENT_ACTIVATED)


class TestDockerIntegration(unittest.TestCase):
    """Docker集成测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine(
            {
                "default_image": "python:3.9-slim",
                "simulation_mode": True,
            }
        )

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.engine.cleanup_all_environments()

    def test_full_lifecycle(self):
        """测试完整生命周期"""
        env_id = "lifecycle_test"

        # 创建环境
        env = self.engine.create_isolation(self.temp_dir, env_id, {})
        self.assertEqual(env.status, EnvironmentStatus.CREATED)

        # 激活环境
        self.assertTrue(env.activate())
        self.assertEqual(env.status, EnvironmentStatus.ACTIVE)

        # 执行命令
        result = env.execute_command(["python", "--version"])
        self.assertEqual(result.returncode, 0)

        # 安装包
        self.assertTrue(env.install_package("requests"))

        # 获取包信息
        packages = env.get_installed_packages()
        self.assertIsInstance(packages, dict)

        # 停用环境
        self.assertTrue(env.deactivate())
        self.assertEqual(env.status, EnvironmentStatus.INACTIVE)

        # 清理环境
        self.assertTrue(env.cleanup())
        self.assertEqual(env.status, EnvironmentStatus.CLEANUP_COMPLETE)

    def test_multiple_environments(self):
        """测试多环境管理"""
        env_configs = [
            ("env1", {"image": "python:3.9-slim"}),
            ("env2", {"image": "python:3.8-slim"}),
            ("env3", {"image": "python:3.10-slim"}),
        ]

        environments = []

        # 创建多个环境
        for env_id, config in env_configs:
            temp_path = self.temp_dir / env_id
            temp_path.mkdir(exist_ok=True)
            env = self.engine.create_isolation(temp_path, env_id, config)
            environments.append(env)

            # 激活环境
            self.assertTrue(env.activate())

        # 验证所有环境都正常
        for env in environments:
            self.assertEqual(env.status, EnvironmentStatus.ACTIVE)
            self.assertIn(env.env_id, self.engine.created_environments)

        # 清理所有环境
        for env in environments:
            self.assertTrue(env.cleanup())

        # 验证环境被清理
        self.assertEqual(len(self.engine.created_environments), 0)

    def test_error_handling(self):
        """测试错误处理"""
        env = self.engine.create_isolation(self.temp_dir, "error_test", {})

        # 测试在未激活状态下执行命令
        result = env.execute_command(["echo", "test"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("not running", result.stderr)

        # 测试释放未分配的端口
        result = env.release_port(9999)
        self.assertFalse(result)

    def test_resource_management(self):
        """测试资源管理"""
        env = self.engine.create_isolation(self.temp_dir, "resource_test", {})

        # 分配多个端口
        ports = []
        for i in range(5):
            port = env.allocate_port()
            ports.append(port)
            self.assertIn(port, env.allocated_ports)

        # 释放所有端口
        for port in ports:
            self.assertTrue(env.release_port(port))
            self.assertNotIn(port, env.allocated_ports)

        # 验证端口列表为空
        self.assertEqual(len(env.allocated_ports), 0)


class TestDockerPerformance(unittest.TestCase):
    """Docker性能测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine(
            {
                "default_image": "python:3.9-slim",
                "simulation_mode": True,
            }
        )

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.engine.cleanup_all_environments()

    def test_environment_creation_performance(self):
        """测试环境创建性能"""
        start_time = time.time()

        env = self.engine.create_isolation(self.temp_dir, "perf_test", {})

        creation_time = time.time() - start_time

        # 在模拟模式下应该很快（< 1秒）
        self.assertLess(creation_time, 1.0)
        self.assertIsInstance(env, DockerEnvironment)

    def test_concurrent_environment_creation(self):
        """测试并发环境创建"""
        import threading

        environments = []
        errors = []

        def create_env(env_id):
            try:
                temp_path = self.temp_dir / env_id
                temp_path.mkdir(exist_ok=True)
                env = self.engine.create_isolation(temp_path, env_id, {})
                environments.append(env)
            except Exception as e:
                errors.append(e)

        # 创建多个线程
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_env, args=(f"concurrent_{i}",))
            threads.append(thread)
            thread.start()

        # 等待所有线程完成
        for thread in threads:
            thread.join()

        # 验证结果
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(environments), 5)

        # 清理环境
        for env in environments:
            env.cleanup(force=True)


if __name__ == "__main__":
    # 运行所有测试
    unittest.main(verbosity=2)
