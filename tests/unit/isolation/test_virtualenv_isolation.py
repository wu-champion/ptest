"""
Virtualenv隔离引擎测试

测试Virtualenv隔离引擎的各项功能，包括环境创建、激活、包管理等
注意：在Windows环境下需要virtualenv包支持
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import subprocess

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 尝试不同的导入方式
try:
    from ptest.isolation.virtualenv_engine import (
        VirtualenvEnvironment,
        VirtualenvIsolationEngine,
    )
    from ptest.isolation.enums import EnvironmentStatus, IsolationEvent  # noqa: F401
    from ptest.core import get_logger
except ImportError:
    import sys

    # 添加当前目录到路径
    current_dir = Path(__file__).parent
    while current_dir.name != "ptest":
        current_dir = current_dir.parent
    sys.path.insert(0, str(current_dir))

    from ptest.isolation.virtualenv_engine import (
        VirtualenvEnvironment,
        VirtualenvIsolationEngine,
    )
    from ptest.isolation.enums import EnvironmentStatus
    from ptest.core import get_logger

logger = get_logger("test_virtualenv")


def _check_virtualenv_available():
    """检查virtualenv是否可用"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "virtualenv", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# Windows平台且virtualenv不可用时跳过测试
IS_WINDOWS = sys.platform == "win32"
VIRTUALENV_AVAILABLE = _check_virtualenv_available()
SHOULD_SKIP_VIRTUALENV_TESTS = IS_WINDOWS and not VIRTUALENV_AVAILABLE


@unittest.skipIf(
    SHOULD_SKIP_VIRTUALENV_TESTS,
    "Virtualenv not available on Windows - install with: pip install virtualenv",
)
class TestVirtualenvEnvironment(unittest.TestCase):
    """VirtualenvEnvironment测试类"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.env_id = "test_env"
        self.config = {
            "python_path": sys.executable,
            "system_site_packages": False,
            "command_timeout": 30,
            "pip_timeout": 30,
        }

        # 创建隔离引擎
        self.engine = VirtualenvIsolationEngine({})

        # 创建测试环境
        self.env = VirtualenvEnvironment(
            self.env_id, self.temp_dir, self.engine, self.config
        )

        logger.info(f"Test setup completed for {self.env_id} at {self.temp_dir}")

    def tearDown(self):
        """测试后清理"""
        try:
            self.env.cleanup(force=True)
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

    def test_virtualenv_creation(self):
        """测试虚拟环境创建"""
        # 测试创建虚拟环境
        result = self.env.create_virtualenv()
        self.assertTrue(result, "Virtual environment creation should succeed")
        self.assertEqual(self.env.status, EnvironmentStatus.CREATED)

        # 验证关键文件存在
        self.assertTrue(
            self.env.venv_path.exists(), "Virtual environment directory should exist"
        )
        self.assertTrue(self.env.python_path.exists(), "Python executable should exist")
        self.assertTrue(self.env.pip_path.exists(), "Pip executable should exist")

    def test_environment_activation(self):
        """测试环境激活"""
        # 先创建虚拟环境
        self.env.create_virtualenv()

        # 测试激活
        result = self.env.activate()
        self.assertTrue(result, "Environment activation should succeed")
        self.assertEqual(self.env.status, EnvironmentStatus.ACTIVE)
        self.assertTrue(self.env._is_active, "Environment should be marked as active")

    def test_environment_deactivation(self):
        """测试环境停用"""
        # 先创建并激活环境
        self.env.create_virtualenv()
        self.env.activate()

        # 测试停用
        result = self.env.deactivate()
        self.assertTrue(result, "Environment deactivation should succeed")
        self.assertEqual(self.env.status, EnvironmentStatus.INACTIVE)
        self.assertFalse(self.env._is_active, "Environment should not be active")

    def test_command_execution(self):
        """测试命令执行"""
        # 创建并激活环境
        self.env.create_virtualenv()
        self.env.activate()

        # 测试Python版本查询
        result = self.env.execute_command([str(self.env.python_path), "--version"])
        self.assertEqual(result.returncode, 0, "Python version command should succeed")
        self.assertIn("Python", result.stdout, "Output should contain Python version")

    def test_package_installation(self):
        """测试包安装"""
        # 创建并激活环境
        self.env.create_virtualenv()
        self.env.activate()

        # 测试安装requests包
        result = self.env.install_package("requests==2.28.1")
        self.assertTrue(result, "Package installation should succeed")

        # 验证包已安装
        packages = self.env.get_installed_packages()
        self.assertIn("requests", packages, "requests should be in installed packages")

    def test_package_uninstallation(self):
        """测试包卸载"""
        # 先安装包
        self.env.create_virtualenv()
        self.env.activate()
        self.env.install_package("requests==2.28.1")

        # 测试卸载
        result = self.env.uninstall_package("requests")
        self.assertTrue(result, "Package uninstallation should succeed")

        # 验证包已卸载
        packages = self.env.get_installed_packages()
        self.assertNotIn(
            "requests", packages, "requests should not be in installed packages"
        )

    def test_port_allocation(self):
        """测试端口分配"""
        # 测试分配端口
        port = self.env.allocate_port()
        self.assertGreater(port, 0, "Allocated port should be greater than 0")
        self.assertIn(
            port, self.env.allocated_ports, "Port should be in allocated ports list"
        )

        # 测试释放端口
        result = self.env.release_port(port)
        self.assertTrue(result, "Port release should succeed")
        self.assertNotIn(
            port,
            self.env.allocated_ports,
            "Port should be removed from allocated ports",
        )

    def test_isolation_validation(self):
        """测试隔离验证"""
        # 创建并激活环境
        self.env.create_virtualenv()
        self.env.activate()

        # 验证隔离有效性
        result = self.env.validate_isolation()
        self.assertTrue(
            result, "Isolation validation should succeed for active environment"
        )

    def test_environment_cleanup(self):
        """测试环境清理"""
        # 创建并激活环境
        self.env.create_virtualenv()
        self.env.activate()

        # 测试清理
        result = self.env.cleanup()
        self.assertTrue(result, "Environment cleanup should succeed")
        self.assertEqual(self.env.status, EnvironmentStatus.CLEANUP_COMPLETE)
        self.assertFalse(
            self.env.venv_path.exists(), "Virtual environment should be removed"
        )


@unittest.skipIf(
    SHOULD_SKIP_VIRTUALENV_TESTS,
    "Virtualenv not available on Windows - install with: pip install virtualenv",
)
class TestVirtualenvIsolationEngine(unittest.TestCase):
    """VirtualenvIsolationEngine测试类"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = {
            "python_path": sys.executable,
            "command_timeout": 30,
            "pip_timeout": 30,
        }
        self.engine = VirtualenvIsolationEngine(self.config)

    def tearDown(self):
        """测试后清理"""
        try:
            self.engine.cleanup_all_environments()
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Engine cleanup failed: {e}")

    def test_engine_initialization(self):
        """测试引擎初始化"""
        self.assertIsNotNone(self.engine, "Engine should be initialized")
        self.assertIsNotNone(self.engine.engine_config, "Engine config should be set")
        self.assertIn(
            "python_path", self.engine.engine_config, "Python path should be in config"
        )

    def test_isolation_creation(self):
        """测试隔离环境创建"""
        env_id = "test_isolation"
        isolation_config = {"test": True}

        # 创建隔离环境
        env = self.engine.create_isolation(self.temp_dir, env_id, isolation_config)

        self.assertIsNotNone(env, "Environment should be created")
        self.assertEqual(env.env_id, env_id, "Environment ID should match")
        self.assertIn(
            env_id,
            self.engine.created_environments,
            "Environment should be in engine's list",
        )

    def test_isolation_status(self):
        """测试隔离状态查询"""
        env_id = "test_status"

        # 创建环境
        self.engine.create_isolation(self.temp_dir, env_id, {})

        # 查询状态
        status = self.engine.get_isolation_status(env_id)

        self.assertIsNotNone(status, "Status should not be None")
        self.assertEqual(
            status["isolation_type"],
            "virtualenv",
            "Isolation type should be virtualenv",
        )
        self.assertIn(
            "supported_features", status, "Status should include supported features"
        )

    def test_isolation_validation(self):
        """测试隔离验证"""
        env_id = "test_validation"

        # 创建环境
        env = self.engine.create_isolation(self.temp_dir, env_id, {})

        # 激活环境
        env.activate()

        # 验证隔离
        is_valid = self.engine.validate_isolation(env)
        self.assertTrue(is_valid, "Isolation validation should succeed")

    def test_supported_features(self):
        """测试支持的功能"""
        features = self.engine.get_supported_features()

        self.assertIsInstance(features, list, "Features should be a list")
        self.assertIn(
            "filesystem_isolation", features, "Should support filesystem isolation"
        )
        self.assertIn(
            "python_package_isolation", features, "Should support package isolation"
        )
        self.assertIn("process_execution", features, "Should support process execution")

    def test_engine_info(self):
        """测试引擎信息"""
        info = self.engine.get_engine_info()

        self.assertIsNotNone(info, "Engine info should not be None")
        self.assertIn("engine_type", info, "Info should include engine type")
        self.assertEqual(
            info["engine_type"], "virtualenv", "Engine type should be virtualenv"
        )

    def test_cleanup_all_environments(self):
        """测试清理所有环境"""
        # 创建多个环境
        for i in range(3):
            env_id = f"test_env_{i}"
            env_path = self.temp_dir / env_id
            env_path.mkdir(exist_ok=True)
            self.engine.create_isolation(env_path, env_id, {})

        # 验证环境存在
        self.assertEqual(
            len(self.engine.created_environments), 3, "Should have 3 environments"
        )

        # 清理所有环境
        cleaned_count = self.engine.cleanup_all_environments()

        self.assertEqual(cleaned_count, 3, "Should clean all 3 environments")
        self.assertEqual(
            len(self.engine.created_environments),
            0,
            "Should have no environments after cleanup",
        )


@unittest.skipIf(
    SHOULD_SKIP_VIRTUALENV_TESTS,
    "Virtualenv not available on Windows - install with: pip install virtualenv",
)
class TestIntegration(unittest.TestCase):
    """集成测试类"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """测试后清理"""
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Integration cleanup failed: {e}")

    def test_full_workflow(self):
        """测试完整工作流程"""
        # 创建引擎
        engine = VirtualenvIsolationEngine({})

        try:
            # 创建环境
            env_id = "integration_test"
            env = engine.create_isolation(self.temp_dir, env_id, {})

            # 激活环境
            self.assertTrue(env.activate(), "Environment activation should succeed")

            # 安装包
            self.assertTrue(
                env.install_package("requests==2.28.1"),
                "Package installation should succeed",
            )

            # 执行命令
            result = env.execute_command(
                [str(env.python_path), "-c", "import requests; print('OK')"]
            )
            self.assertEqual(result.returncode, 0, "Command execution should succeed")
            self.assertIn("OK", result.stdout, "Output should be correct")

            # 验证隔离
            self.assertTrue(
                engine.validate_isolation(env), "Isolation validation should succeed"
            )

            # 清理环境
            self.assertTrue(
                engine.cleanup_isolation(env), "Environment cleanup should succeed"
            )

        finally:
            # 最终清理
            engine.cleanup_all_environments()

    def test_concurrent_environments(self):
        """测试并发环境"""
        engines = []
        environments = []

        try:
            # 创建多个引擎和环境
            for i in range(3):
                engine = VirtualenvIsolationEngine({})
                env_id = f"concurrent_test_{i}"
                env_path = self.temp_dir / env_id
                env_path.mkdir(exist_ok=True)

                env = engine.create_isolation(env_path, env_id, {})
                self.assertTrue(
                    env.create_virtualenv(), f"Environment {i} creation should succeed"
                )

                engines.append(engine)
                environments.append(env)

            # 验证所有环境都是独立的
            for i, env in enumerate(environments):
                packages = env.get_installed_packages()
                # 每个环境应该有不同的包列表（至少是空的）
                self.assertIsInstance(
                    packages, dict, f"Environment {i} should have package list"
                )

        finally:
            # 清理所有引擎和环境
            for engine in engines:
                engine.cleanup_all_environments()


if __name__ == "__main__":
    # 运行测试
    logger.info("Starting Virtualenv engine tests")

    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestVirtualenvEnvironment))
    suite.addTests(loader.loadTestsFromTestCase(TestVirtualenvIsolationEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出结果
    if result.wasSuccessful():
        logger.info("All tests passed successfully!")
    else:
        logger.error(
            f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors"
        )

    sys.exit(0 if result.wasSuccessful() else 1)
