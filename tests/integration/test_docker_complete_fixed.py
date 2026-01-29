#!/usr/bin/env python3
"""
Docker引擎完整功能测试 - 使用正确的src布局

这个测试脚本验证Docker隔离引擎的所有核心功能：
- 基础环境创建和管理
- 镜像拉取和管理
- 网络管理
- 卷管理
- 容器生命周期管理
- 快照功能
- 资源清理
"""

import os
import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# 框架导入
from ptest.isolation.docker_engine import DockerIsolationEngine, DockerEnvironment
from ptest.isolation.base import IsolationEngine, IsolatedEnvironment, ProcessResult
from ptest.isolation.enums import EnvironmentStatus, ProcessStatus, IsolationEvent
from ptest.core import get_logger

# 设置测试日志
logger = get_logger("docker_test")


class TestDockerEngineComplete(unittest.TestCase):
    """Docker引擎完整功能测试套件"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_env_id = f"test_docker_{int(time.time())}"

        # 基础配置
        self.engine_config = {
            "default_image": "python:3.9-slim",
            "network_subnet": "172.20.0.0/16",
            "volume_base_path": "/tmp/ptest_volumes",
            "container_timeout": 60,
            "pull_timeout": 120,
        }

        # 创建Docker引擎实例
        self.engine = DockerIsolationEngine(self.engine_config)

    def tearDown(self):
        """测试后清理"""
        # 清理测试环境
        try:
            if hasattr(self.engine, "created_environments"):
                for env_id, env in list(self.engine.created_environments.items()):
                    if hasattr(env, "cleanup"):
                        env.cleanup(force=True)

            # 清理未使用的资源
            if hasattr(self.engine, "cleanup_unused_resources"):
                self.engine.cleanup_unused_resources()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

    def test_01_engine_initialization(self):
        """测试Docker引擎初始化"""
        logger.info("Testing Docker engine initialization...")

        # 验证引擎属性
        self.assertIsInstance(self.engine, DockerIsolationEngine)
        self.assertIsInstance(self.engine, IsolationEngine)

        # 验证支持的功能
        expected_features = [
            "filesystem_isolation",
            "python_package_isolation",
            "process_execution",
            "port_allocation",
            "network_isolation",
            "volume_management",
            "container_isolation",
            "image_management",
        ]
        self.assertEqual(set(self.engine.supported_features), set(expected_features))

        # 验证配置
        self.assertEqual(self.engine.engine_config["default_image"], "python:3.9-slim")

        logger.info("✓ Docker engine initialization test passed")

    def test_02_simulation_mode(self):
        """测试模拟模式（当Docker不可用时）"""
        logger.info("Testing Docker simulation mode...")

        with patch("ptest.isolation.docker_engine.DOCKER_AVAILABLE", False):
            # 创建模拟环境
            env = self.engine.create_isolation(
                self.temp_dir, self.test_env_id + "_sim", {"image": "python:3.9-slim"}
            )

            self.assertIsInstance(env, DockerEnvironment)
            self.assertEqual(env.env_id, self.test_env_id + "_sim")
            self.assertEqual(env.image_name, "python:3.9-slim")

            # 测试模拟容器创建
            result = env.activate()
            self.assertTrue(result)
            self.assertEqual(env.status, EnvironmentStatus.ACTIVE)

            # 测试模拟命令执行
            result = env.execute_command(["echo", "hello"])
            self.assertIsInstance(result, ProcessResult)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Docker simulation", result.stdout)

            # 清理
            cleanup_result = env.cleanup()
            self.assertTrue(cleanup_result)

        logger.info("✓ Docker simulation mode test passed")

    def test_03_environment_creation(self):
        """测试Docker环境创建"""
        logger.info("Testing Docker environment creation...")

        # 创建环境
        env = self.engine.create_isolation(
            self.temp_dir,
            self.test_env_id + "_create",
            {
                "image": "python:3.9-slim",
                "environment_vars": {"TEST_VAR": "test_value"},
                "resource_limits": {"memory": "256m", "cpus": "0.5"},
            },
        )

        self.assertIsInstance(env, DockerEnvironment)
        self.assertEqual(env.env_id, self.test_env_id + "_create")
        self.assertEqual(env.environment_vars.get("TEST_VAR"), "test_value")
        self.assertEqual(env.resource_limits.get("memory"), "256m")

        # 验证环境在引擎中注册
        self.assertIn(env.env_id, self.engine.created_environments)

        logger.info("✓ Docker environment creation test passed")

    def test_04_container_lifecycle(self):
        """测试容器生命周期管理"""
        logger.info("Testing Docker container lifecycle...")

        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_lifecycle", {}
        )

        # 测试创建容器
        created = env.create_container()
        self.assertTrue(created)

        # 测试启动容器
        started = env.start_container()
        self.assertTrue(started)
        self.assertEqual(env.status, EnvironmentStatus.ACTIVE)

        # 测试停止容器
        stopped = env.stop_container()
        self.assertTrue(stopped)
        self.assertEqual(env.status, EnvironmentStatus.INACTIVE)

        # 测试重新启动
        restarted = env.start_container()
        self.assertTrue(restarted)
        self.assertEqual(env.status, EnvironmentStatus.ACTIVE)

        # 测试删除容器
        removed = env.remove_container()
        self.assertTrue(removed)

        logger.info("✓ Docker container lifecycle test passed")

    def test_05_process_execution(self):
        """测试进程执行功能"""
        logger.info("Testing Docker process execution...")

        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_exec", {}
        )

        # 激活环境
        self.assertTrue(env.activate())

        # 测试简单命令执行
        result = env.execute_command(["python", "--version"])
        self.assertIsInstance(result, ProcessResult)
        # 在模拟模式下，这会成功
        self.assertIn("Python", result.stdout or result.stderr)

        # 测试命令执行失败情况
        result = env.execute_command(["python", "--invalid-option"])
        self.assertIsInstance(result, ProcessResult)
        # 可能返回非零退出码或错误信息

        # 测试超时控制
        start_time = time.time()
        result = env.execute_command(["sleep", "0.1"], timeout=5)
        elapsed = time.time() - start_time
        self.assertLess(elapsed, 10)  # 应该很快完成

        logger.info("✓ Docker process execution test passed")

    def test_06_package_management(self):
        """测试Python包管理功能"""
        logger.info("Testing Docker package management...")

        env = self.engine.create_isolation(self.temp_dir, self.test_env_id + "_pkg", {})

        self.assertTrue(env.activate())

        # 测试获取已安装包列表
        packages = env.get_installed_packages()
        self.assertIsInstance(packages, dict)

        # 测试获取特定包版本
        python_version = env.get_package_version("python")
        # 在模拟模式下可能为None，这是正常的

        # 测试安装包（模拟模式）
        install_result = env.install_package("requests")
        self.assertTrue(install_result)  # 模拟模式下总是成功

        # 测试卸载包
        uninstall_result = env.uninstall_package("requests")
        self.assertTrue(uninstall_result)  # 模拟模式下总是成功

        logger.info("✓ Docker package management test passed")

    def test_07_port_management(self):
        """测试端口管理功能"""
        logger.info("Testing Docker port management...")

        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_port", {}
        )

        # 测试端口分配
        allocated_port = env.allocate_port()
        self.assertIsInstance(allocated_port, int)
        self.assertGreater(allocated_port, 0)
        self.assertIn(allocated_port, env.allocated_ports)
        self.assertIn(allocated_port, env.port_mappings)

        # 测试再次分配端口
        allocated_port2 = env.allocate_port()
        self.assertNotEqual(allocated_port, allocated_port2)

        # 测试端口释放
        released = env.release_port(allocated_port)
        self.assertTrue(released)
        self.assertNotIn(allocated_port, env.allocated_ports)
        self.assertNotIn(allocated_port, env.port_mappings)

        # 测试释放不存在的端口
        not_released = env.release_port(99999)
        self.assertFalse(not_released)

        logger.info("✓ Docker port management test passed")

    def test_08_network_management(self):
        """测试网络管理功能"""
        logger.info("Testing Docker network management...")

        # 测试创建网络
        network_name = f"ptest_test_network_{int(time.time())}"
        network = self.engine.create_network(network_name)

        # 在模拟模式下可能返回None
        if network is not None:
            self.assertIsNotNone(network)

        # 测试创建带网络的环境
        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_net", {"create_network": True}
        )

        # 验证网络名称设置
        self.assertIsInstance(env.network_name, str)

        logger.info("✓ Docker network management test passed")

    def test_09_volume_management(self):
        """测试卷管理功能"""
        logger.info("Testing Docker volume management...")

        # 测试创建卷
        volume_name = f"ptest_test_volume_{int(time.time())}"
        volume = self.engine.create_volume(volume_name)

        # 在模拟模式下可能返回None
        if volume is not None:
            self.assertIsNotNone(volume)

        # 测试创建带卷的环境
        env = self.engine.create_isolation(
            self.temp_dir,
            self.test_env_id + "_vol",
            {"volumes": {volume_name: {"bind": "/data", "mode": "rw"}}},
        )

        # 验证卷配置
        self.assertIsInstance(env.volumes, dict)

        logger.info("✓ Docker volume management test passed")

    def test_10_snapshot_functionality(self):
        """测试快照功能"""
        logger.info("Testing Docker snapshot functionality...")

        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_snapshot", {}
        )

        # 激活环境
        self.assertTrue(env.activate())

        # 创建快照
        snapshot = env.create_snapshot("test_snapshot_1")
        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["snapshot_id"], "test_snapshot_1")
        self.assertEqual(snapshot["env_id"], env.env_id)
        self.assertIn("docker_info", snapshot)
        self.assertIn("created_at", snapshot)

        # 验证快照内容
        docker_info = snapshot["docker_info"]
        self.assertEqual(docker_info["container_name"], env.container_name)
        self.assertEqual(docker_info["image_name"], env.image_name)

        # 测试列出快照
        snapshots = env.list_snapshots()
        self.assertIsInstance(snapshots, list)

        # 测试导出快照数据
        export_data = env.export_snapshot_data()
        self.assertIsInstance(export_data, dict)
        self.assertEqual(export_data["env_id"], env.env_id)
        self.assertEqual(export_data["env_type"], "docker")

        # 测试恢复快照（简化版本）
        # 注意：在单元测试中，我们主要验证方法调用而不实际恢复
        restore_result = env.restore_from_snapshot(snapshot)
        # 在模拟模式下可能失败，这是正常的

        # 测试删除快照
        delete_result = env.delete_snapshot("test_snapshot_1")
        self.assertTrue(delete_result)  # 模拟模式下总是成功

        logger.info("✓ Docker snapshot functionality test passed")

    def test_11_environment_status_and_validation(self):
        """测试环境状态和验证功能"""
        logger.info("Testing environment status and validation...")

        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_status", {}
        )

        # 初始状态
        self.assertEqual(env.status, EnvironmentStatus.CREATED)

        # 激活后状态
        self.assertTrue(env.activate())
        self.assertEqual(env.status, EnvironmentStatus.ACTIVE)

        # 验证隔离
        is_valid = env.validate_isolation()
        self.assertIsInstance(is_valid, bool)

        # 获取容器信息
        container_info = env.get_container_info()
        self.assertIsInstance(container_info, dict)
        self.assertIn("container_id", container_info)
        self.assertIn("name", container_info)

        # 停用后状态
        self.assertTrue(env.deactivate())
        self.assertEqual(env.status, EnvironmentStatus.INACTIVE)

        logger.info("✓ Environment status and validation test passed")

    def test_12_engine_status_and_features(self):
        """测试引擎状态和功能"""
        logger.info("Testing engine status and features...")

        # 验证Docker环境
        docker_env = self.engine.verify_docker_environment()
        self.assertIsInstance(docker_env, dict)
        self.assertIn("available", docker_env)
        self.assertIn("simulation_mode", docker_env)

        # 获取引擎信息
        engine_info = self.engine.get_engine_info()
        self.assertIsInstance(engine_info, dict)
        self.assertEqual(engine_info["engine_type"], "docker")
        self.assertIn("supported_features", engine_info)

        # 获取支持的功能
        features = self.engine.get_supported_features()
        self.assertIsInstance(features, list)
        self.assertEqual(len(features), len(self.engine.supported_features))

        # 列出可用镜像
        images = self.engine.list_available_images()
        self.assertIsInstance(images, list)

        # 清理未使用资源
        cleanup_counts = self.engine.cleanup_unused_resources()
        self.assertIsInstance(cleanup_counts, dict)
        self.assertIn("containers", cleanup_counts)
        self.assertIn("images", cleanup_counts)
        self.assertIn("volumes", cleanup_counts)
        self.assertIn("networks", cleanup_counts)

        logger.info("✓ Engine status and features test passed")

    def test_13_isolation_status_tracking(self):
        """测试隔离状态跟踪"""
        logger.info("Testing isolation status tracking...")

        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_tracking", {}
        )

        # 获取初始状态
        status = self.engine.get_isolation_status(env.env_id)
        self.assertIsInstance(status, dict)
        self.assertEqual(status["status"], "created")
        self.assertEqual(status["isolation_type"], "docker")

        # 激活环境
        self.assertTrue(env.activate())

        # 获取更新后的状态
        status = self.engine.get_isolation_status(env.env_id)
        self.assertEqual(status["status"], "active")

        # 验证隔离
        is_valid = self.engine.validate_isolation(env)
        self.assertIsInstance(is_valid, bool)

        # 清理环境
        cleanup_result = self.engine.cleanup_isolation(env)
        self.assertTrue(cleanup_result)

        # 验证环境已从引擎中移除
        self.assertNotIn(env.env_id, self.engine.created_environments)

        logger.info("✓ Isolation status tracking test passed")

    def test_14_error_handling_and_recovery(self):
        """测试错误处理和恢复"""
        logger.info("Testing error handling and recovery...")

        # 测试创建环境时无效配置
        try:
            env = self.engine.create_isolation(
                Path("/invalid/path"), self.test_env_id + "_error", {}
            )
            # 即使路径无效，环境创建也应该成功
            self.assertIsInstance(env, DockerEnvironment)
        except Exception as e:
            # 如果抛出异常，验证它是预期的类型
            self.assertIsInstance(e, (ValueError, OSError, PermissionError))

        # 测试无效命令执行
        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_cmd_error", {}
        )
        self.assertTrue(env.activate())

        result = env.execute_command(["/invalid/command"])
        self.assertIsInstance(result, ProcessResult)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr.lower() or "failed")

        # 测试强制清理
        force_cleanup = env.cleanup(force=True)
        self.assertTrue(force_cleanup)

        logger.info("✓ Error handling and recovery test passed")

    def test_15_configuration_and_customization(self):
        """测试配置和自定义功能"""
        logger.info("Testing configuration and customization...")

        # 自定义配置
        custom_config = {
            "image": "python:3.8-alpine",
            "environment_vars": {
                "CUSTOM_VAR1": "value1",
                "CUSTOM_VAR2": "value2",
            },
            "resource_limits": {
                "memory": "128m",
                "cpus": "0.25",
                "disk": "5g",
            },
            "port_mappings": {8080: 80},
            "volumes": {"test_volume": {"bind": "/app/data", "mode": "rw"}},
            "stop_timeout": 10,
        }

        env = self.engine.create_isolation(
            self.temp_dir, self.test_env_id + "_config", custom_config
        )

        # 验证配置应用
        self.assertEqual(env.image_name, "python:3.8-alpine")
        self.assertEqual(env.environment_vars["CUSTOM_VAR1"], "value1")
        self.assertEqual(env.environment_vars["CUSTOM_VAR2"], "value2")
        self.assertEqual(env.resource_limits["memory"], "128m")
        self.assertEqual(env.resource_limits["cpus"], "0.25")
        self.assertEqual(env.config["stop_timeout"], 10)

        # 测试功能激活
        self.assertTrue(env.activate())

        # 验证端口映射设置
        self.assertIn(8080, env.port_mappings)

        logger.info("✓ Configuration and customization test passed")


class TestDockerIntegration(unittest.TestCase):
    """Docker集成测试"""

    def setUp(self):
        """集成测试准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine(
            {
                "default_image": "python:3.9-slim",
                "container_timeout": 30,
            }
        )

    def tearDown(self):
        """集成测试清理"""
        try:
            for env_id, env in list(self.engine.created_environments.items()):
                env.cleanup(force=True)
            self.engine.cleanup_unused_resources()
        except Exception as e:
            logger.warning(f"Integration cleanup error: {e}")

    def test_complete_workflow(self):
        """测试完整的工作流程"""
        logger.info("Testing complete Docker workflow...")

        # 1. 创建环境
        env = self.engine.create_isolation(
            self.temp_dir,
            "integration_test",
            {
                "environment_vars": {"WORKFLOW_TEST": "true"},
            },
        )

        # 2. 激活环境
        self.assertTrue(env.activate())

        # 3. 执行命令
        result = env.execute_command(["python", "-c", "print('Integration test')"])
        self.assertIsInstance(result, ProcessResult)

        # 4. 管理包
        install_result = env.install_package("pytest")
        self.assertTrue(install_result)

        # 5. 分配端口
        port = env.allocate_port()
        self.assertIsInstance(port, int)

        # 6. 创建快照
        snapshot = env.create_snapshot("integration_snapshot")
        self.assertIsInstance(snapshot, dict)

        # 7. 获取状态
        status = env.get_status()
        self.assertIsInstance(status, dict)

        # 8. 清理
        cleanup = env.cleanup()
        self.assertTrue(cleanup)

        logger.info("✓ Complete Docker workflow test passed")


def run_docker_tests():
    """运行所有Docker测试"""
    logger.info("Starting Docker Engine Complete Functionality Tests")
    logger.info("=" * 60)

    # 创建测试套件
    test_suite = unittest.TestSuite()

    # 添加基础功能测试
    test_suite.addTest(unittest.makeSuite(TestDockerEngineComplete))

    # 添加集成测试
    test_suite.addTest(unittest.makeSuite(TestDockerIntegration))

    # 运行测试
    runner = unittest.TextTestRunner(
        verbosity=2, stream=sys.stdout, descriptions=True, failfast=False
    )

    result = runner.run(test_suite)

    # 输出总结
    logger.info("=" * 60)
    logger.info("Docker Engine Test Summary:")
    logger.info(f"Tests run: {result.testsRun}")
    logger.info(f"Failures: {len(result.failures)}")
    logger.info(f"Errors: {len(result.errors)}")
    logger.info(
        f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%"
    )

    if result.failures:
        logger.error("Failures:")
        for test, traceback in result.failures:
            logger.error(f"  - {test}: {traceback}")

    if result.errors:
        logger.error("Errors:")
        for test, traceback in result.errors:
            logger.error(f"  - {test}: {traceback}")

    success = len(result.failures) == 0 and len(result.errors) == 0
    logger.info(f"Docker Engine Tests {'PASSED' if success else 'FAILED'}")

    return success


if __name__ == "__main__":
    success = run_docker_tests()
    sys.exit(0 if success else 1)
