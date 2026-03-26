"""测试 Docker 隔离引擎核心功能 - ptest 断言版本

迁移说明:
- 原文件使用 pytest/unittest 断言，现已迁移到 ptest 断言
- 迁移对照表:
  - assertEqual(x, y) → assert_that(x).equals(y)
  - assertIsNotNone(x) → assert_that(x).not_none()
  - assertIsInstance(x, T) → assert_that(x).is_instance(T)
  - assertIn(key, dict) → assert_that(dict).contains(key)
  - assertGreater(x, y) → assert_that(x > y).is_true()
  - assertTrue(x) → assert_that(x).is_true()
  - assertEqual(len(x), n) → assert_that(len(x)).equals(n)
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from ptest.assertions import assert_that

from ptest.isolation.docker_engine import DockerIsolationEngine, DockerEnvironment
from ptest.isolation.enums import IsolationEvent


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
        except Exception:
            pass

    def test_engine_creation(self):
        """测试引擎创建"""
        assert_that(self.engine).not_none()
        assert_that(self.engine.engine_name).equals("DockerIsolationEngine")
        assert_that(self.engine.supported_features).is_instance(list)

    def test_engine_info(self):
        """测试引擎信息"""
        info = self.engine.get_engine_info()
        assert_that(info).is_instance(dict)
        assert_that(info).contains("engine_type")
        assert_that(info["engine_type"]).equals("docker")

    def test_docker_environment_verification(self):
        """测试Docker环境验证"""
        env_info = self.engine.verify_docker_environment()
        assert_that(env_info).is_instance(dict)
        assert_that(env_info).contains("available")
        assert_that(env_info).contains("simulation_mode")

    def test_create_environment(self):
        """测试创建环境"""
        env = self.engine.create_isolation(self.temp_dir, "test_env", {})
        assert_that(env).is_instance(DockerEnvironment)
        assert_that(env.env_id).equals("test_env")
        assert_that(env.path).equals(self.temp_dir)

    def test_get_status_for_nonexistent_env(self):
        """测试获取不存在环境的状态"""
        status = self.engine.get_isolation_status("nonexistent")
        assert_that(status).is_instance(dict)
        assert_that(status["status"]).equals("not_found")

    def test_list_images(self):
        """测试列出镜像"""
        images = self.engine.list_available_images()
        assert_that(images).is_instance(list)

    def test_cleanup_resources(self):
        """测试清理资源"""
        counts = self.engine.cleanup_unused_resources()
        assert_that(counts).is_instance(dict)
        assert_that(counts).contains("containers")

    def test_environment_basic_operations(self):
        """测试环境基本操作"""
        env = self.engine.create_isolation(self.temp_dir, "basic_test", {})

        # 测试端口分配
        port = env.allocate_port()
        assert_that(port).is_instance(int)
        assert_that(port > 0).is_true()

        # 测试端口释放
        result = env.release_port(port)
        assert_that(result).is_true()

        # 测试清理
        result = env.cleanup(force=True)
        assert_that(result).is_true()

    def test_get_container_info(self):
        """测试获取容器信息"""
        env = self.engine.create_isolation(self.temp_dir, "info_test", {})
        info = env.get_container_info()
        assert_that(info).is_instance(dict)
        assert_that(info).contains("container_id")
        assert_that(info).contains("name")
        assert_that(info).contains("image")


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
        assert_that(len(self.events_received)).equals(1)
        assert_that(self.events_received[0][0]).equals(
            IsolationEvent.ENVIRONMENT_CREATED
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
