"""
Docker隔离引擎简化测试

测试Docker隔离引擎的核心功能，使用模拟模式
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os

from ptest.isolation.docker_engine import DockerIsolationEngine, DockerEnvironment
from ptest.isolation.enums import EnvironmentStatus, IsolationEvent


class TestDockerBasic(unittest.TestCase):
    """Docker基础功能测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine(
            {
                "default_image": "python:3.9-slim",
                "container_timeout": 60,
            }
        )

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        try:
            self.engine.cleanup_all_environments()
        except:
            pass

    def test_engine_creation(self):
        """测试引擎创建"""
        self.assertIsNotNone(self.engine)
        self.assertEqual(self.engine.engine_name, "DockerIsolationEngine")
        self.assertIsInstance(self.engine.supported_features, list)

    def test_engine_info(self):
        """测试引擎信息"""
        info = self.engine.get_engine_info()
        self.assertIsInstance(info, dict)
        self.assertIn("engine_type", info)
        self.assertEqual(info["engine_type"], "docker")

    def test_docker_environment_verification(self):
        """测试Docker环境验证"""
        env_info = self.engine.verify_docker_environment()
        self.assertIsInstance(env_info, dict)
        self.assertIn("available", env_info)
        self.assertIn("simulation_mode", env_info)

    def test_create_environment(self):
        """测试创建环境"""
        env = self.engine.create_isolation(self.temp_dir, "test_env", {})
        self.assertIsInstance(env, DockerEnvironment)
        self.assertEqual(env.env_id, "test_env")
        self.assertEqual(env.path, self.temp_dir)

    def test_get_status_for_nonexistent_env(self):
        """测试获取不存在环境的状态"""
        status = self.engine.get_isolation_status("nonexistent")
        self.assertIsInstance(status, dict)
        self.assertEqual(status["status"], "not_found")

    def test_list_images(self):
        """测试列出镜像"""
        images = self.engine.list_available_images()
        self.assertIsInstance(images, list)

    def test_cleanup_resources(self):
        """测试清理资源"""
        counts = self.engine.cleanup_unused_resources()
        self.assertIsInstance(counts, dict)
        self.assertIn("containers", counts)

    def test_environment_basic_operations(self):
        """测试环境基本操作"""
        env = self.engine.create_isolation(self.temp_dir, "basic_test", {})

        # 测试端口分配
        port = env.allocate_port()
        self.assertIsInstance(port, int)
        self.assertGreater(port, 0)

        # 测试端口释放
        result = env.release_port(port)
        self.assertTrue(result)

        # 测试清理
        result = env.cleanup(force=True)
        self.assertTrue(result)

    def test_get_container_info(self):
        """测试获取容器信息"""
        env = self.engine.create_isolation(self.temp_dir, "info_test", {})
        info = env.get_container_info()
        self.assertIsInstance(info, dict)
        self.assertIn("container_id", info)
        self.assertIn("name", info)
        self.assertIn("image", info)


class TestDockerEvents(unittest.TestCase):
    """Docker事件系统测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine({})
        self.env = self.engine.create_isolation(self.temp_dir, "event_test", {})
        self.events_received = []

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_event_listener(self):
        """测试事件监听器"""

        def callback(env, event, *args, **kwargs):
            self.events_received.append((event, args, kwargs))

        # 添加事件监听器
        self.env.add_event_listener(IsolationEvent.ENVIRONMENT_CREATED, callback)

        # 手动触发事件
        self.env._emit_event(IsolationEvent.ENVIRONMENT_CREATED, test="data")

        # 验证事件被记录
        self.assertEqual(len(self.events_received), 1)
        self.assertEqual(self.events_received[0][0], IsolationEvent.ENVIRONMENT_CREATED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
