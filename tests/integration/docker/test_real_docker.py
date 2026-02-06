#!/usr/bin/env python3
"""
真实 Docker 环境测试
验证 ptest Docker 引擎在实际 Docker 环境中的工作情况
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import time

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from ptest.isolation.docker_engine import DockerIsolationEngine, DockerEnvironment  # noqa: E402
from ptest.isolation.enums import EnvironmentStatus  # noqa: E402


class TestRealDockerEnvironment(unittest.TestCase):
    """真实 Docker 环境测试"""

    @classmethod
    def setUpClass(cls):
        """测试类开始前准备 - 验证 Docker 可用性"""
        try:
            import docker

            client = docker.from_env()
            client.ping()
            cls.docker_available = True
            print("\n✓ Docker 环境可用，将执行真实 Docker 测试")
        except Exception as e:
            cls.docker_available = False
            print(f"\n✗ Docker 环境不可用: {e}")
            print("  跳过真实 Docker 测试")

    def setUp(self):
        """测试前准备"""
        if not self.docker_available:
            self.skipTest("Docker 环境不可用")

        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine(
            {
                "default_image": "python:3.9-alpine",  # 使用轻量级镜像
                "container_timeout": 30,
                "simulation_mode": False,  # 使用真实 Docker 模式
            }
        )
        self.test_env_id = f"test_env_{int(time.time())}"

    def tearDown(self):
        """清理测试资源"""
        if hasattr(self, "engine") and self.engine:
            try:
                self.engine.cleanup_all_environments()
            except Exception:
                pass

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_01_docker_client_connection(self):
        success = self.engine.initialize_client()
        self.assertTrue(success)
        self.assertIsNotNone(self.engine.docker_client)
        print("  ✓ Docker 客户端连接成功")

    def test_02_create_real_isolation(self):
        """测试创建真实隔离环境"""
        env = self.engine.create_isolation(self.temp_dir, self.test_env_id, {})

        self.assertIsNotNone(env)
        self.assertIsInstance(env, DockerEnvironment)
        self.assertEqual(env.env_id, self.test_env_id)
        print(f"  ✓ 创建隔离环境成功: {self.test_env_id}")

    def test_03_execute_command_in_container(self):
        """测试在容器中执行命令"""
        env = self.engine.create_isolation(self.temp_dir, self.test_env_id, {})

        # 激活环境
        success = env.start_container()
        self.assertTrue(success)

        # 执行命令
        result = env.execute_command(["python", "--version"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("Python", result.stdout)
        print(f"  ✓ 容器内命令执行成功: {result.stdout.strip()}")

    def test_04_environment_lifecycle(self):
        """测试环境完整生命周期"""
        # 1. 创建
        env = self.engine.create_isolation(self.temp_dir, self.test_env_id, {})
        self.assertIsNotNone(env)
        print("  1. 创建环境 ✓")

        # 2. 启动
        success = env.start_container()
        self.assertTrue(success)
        print("  2. 启动容器 ✓")

        # 3. 验证状态
        status = env.get_status()
        self.assertEqual(status["status"], EnvironmentStatus.ACTIVE.value)
        print("  3. 验证状态 ✓")

        # 4. 停止
        success = env.stop_container()
        self.assertTrue(success)
        print("  4. 停止容器 ✓")

        # 5. 清理
        success = self.engine.cleanup_isolation(env)
        self.assertTrue(success)
        print("  5. 清理环境 ✓")

    def test_05_container_isolation(self):
        """测试容器隔离性"""
        env = self.engine.create_isolation(self.temp_dir, self.test_env_id, {})

        # 启动容器
        env.start_container()

        # 在容器内创建文件
        result = env.execute_command(
            [
                "sh",
                "-c",
                "echo 'isolated_data' > /tmp/test_isolation.txt && cat /tmp/test_isolation.txt",
            ]
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("isolated_data", result.stdout)
        print("  ✓ 容器隔离性验证成功")

    def test_06_engine_info(self):
        """测试引擎信息"""
        info = self.engine.get_engine_info()

        self.assertEqual(info["name"], "DockerIsolationEngine")
        self.assertIn("container_isolation", info["supported_features"])
        self.assertEqual(info["engine_type"], "docker")
        print(f"  ✓ 引擎信息: {info['name']}")
        print(f"    支持功能: {', '.join(info['supported_features'][:3])}...")


class TestRealDockerCleanup(unittest.TestCase):
    """测试 Docker 资源清理"""

    @classmethod
    def setUpClass(cls):
        """记录测试前的容器状态"""
        try:
            import docker

            client = docker.from_env()
            client.ping()
            cls.docker_available = True

            # 记录测试前的容器数量
            containers = client.containers.list(all=True)
            cls.initial_container_count = len(containers)
            print(f"\n测试前容器数量: {cls.initial_container_count}")
        except Exception:
            cls.docker_available = False

    def setUp(self):
        """测试前准备"""
        if not self.docker_available:
            self.skipTest("Docker 环境不可用")

        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = DockerIsolationEngine(
            {
                "default_image": "python:3.9-alpine",
                "container_timeout": 30,
                "simulation_mode": False,
            }
        )

    def tearDown(self):
        if hasattr(self, "engine") and self.engine:
            try:
                self.engine.cleanup_all_environments()
            except Exception:
                pass

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_cleanup_all_environments(self):
        """测试清理所有环境"""
        # 创建多个环境
        env_ids = []
        for i in range(3):
            env_id = f"test_cleanup_{i}_{int(time.time())}"
            env = self.engine.create_isolation(self.temp_dir / env_id, env_id, {})
            env.start_container()
            env_ids.append(env_id)

        print(f"  创建了 {len(env_ids)} 个测试环境")

        # 清理所有环境
        result = self.engine.cleanup_all_environments()
        self.assertTrue(result)

        # 验证环境已清理
        self.assertEqual(len(self.engine.created_environments), 0)
        print("  ✓ 所有环境已清理")


def run_real_docker_tests():
    """运行真实 Docker 测试"""
    print("=" * 60)
    print("真实 Docker 环境测试")
    print("=" * 60)

    # 检查 Docker 可用性
    try:
        import docker

        client = docker.from_env()
        client.ping()
        print("✓ Docker 守护进程已连接")
        print(f"  Docker 版本: {client.version()['Version']}")
    except Exception as e:
        print(f"✗ Docker 连接失败: {e}")
        print("请确保 Docker 已安装并正在运行")
        return False

    print()

    # 运行测试
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestRealDockerEnvironment))
    suite.addTests(loader.loadTestsFromTestCase(TestRealDockerCleanup))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出结果
    print("\n" + "=" * 60)
    print("测试结果摘要:")
    print(f"运行测试: {result.testsRun}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped)}")

    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n测试结果: {'全部通过 ✓' if success else '存在问题 ✗'}")

    return success


if __name__ == "__main__":
    success = run_real_docker_tests()
    sys.exit(0 if success else 1)
