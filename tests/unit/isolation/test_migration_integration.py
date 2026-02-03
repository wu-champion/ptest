"""
环境迁移功能测试

测试Virtualenv到Docker和Docker到Virtualenv的环境迁移功能
"""

import unittest
from pathlib import Path
import tempfile
import json
from datetime import datetime, timedelta
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ptest.isolation.environment_migration import (
    EnvironmentMigrator,
    MigrationProgress,
    SnapshotCrossEngineConverter,
    migrate_environment,
)

from ptest.isolation.base import (
    IsolationEngine,
    IsolatedEnvironment,
    EnvironmentSnapshot,
)


class MockSourceEngine:
    """模拟源引擎"""

    def __init__(self):
        self.engine_type = "virtualenv"
        self.environments = {
            "test_env_1": IsolatedEnvironment(
                env_id="test_env_1",
                path=Path("/tmp/test_env_1"),
                isolation_engine=self,
                config={},
                status="running",
                created_at=datetime.now(),
            ),
        }
        self.created_snapshots = []

    def create_environment(self, env_id: str, config: dict) -> IsolatedEnvironment:
        """创建环境"""
        env = self.environments.get(env_id)
        if not env:
            raise ValueError(f"Environment {env_id} not found")
        return env

    def create_snapshot(self, env_id: str) -> EnvironmentSnapshot:
        """创建快照"""
        snapshot = {
            "snapshot_id": f"snapshot_{env_id}_{len(self.created_snapshots)}",
            "env_id": env_id,
            "created_at": datetime.now().isoformat(),
            "packages": {"test_package": "1.0.0"},
            "config_files": [],
            "custom_scripts": [],
        }
        self.created_snapshots.append(snapshot)
        return snapshot

    def check_package_compatibility(self, package_name: str) -> dict:
        """检查包兼容性"""
        return {
            "compatible": True,
            "message": "",
        }

    def install_package(self, env_id: str, package: str, version: str) -> bool:
        """安装包"""
        return True


class MockTargetEngine:
    """模拟目标引擎"""

    def __init__(self):
        self.engine_type = "docker"
        self.environments = {}
        self.created_snapshots = []
        self.installed_packages = {}

    def create_environment(self, env_id: str, config: dict) -> IsolatedEnvironment:
        """创建环境"""
        env = self.environments.get(env_id)
        if not env:
            raise ValueError(f"Environment {env_id} not found")
        return env

    def create_snapshot(self, env_id: str) -> EnvironmentSnapshot:
        """创建快照"""
        snapshot = {
            "snapshot_id": f"snapshot_{env_id}_{len(self.created_snapshots)}",
            "env_id": env_id,
            "created_at": datetime.now().isoformat(),
            "packages": {},
            "config_files": [],
            "custom_scripts": [],
        }
        self.created_snapshots.append(snapshot)
        return snapshot

    def check_package_compatibility(self, package_name: str) -> dict:
        """检查包兼容性"""
        # Docker可以安装大多数Python包，假设兼容
        return {
            "compatible": True,
            "message": "",
        }

    def install_package(self, env_id: str, package: str, version: str) -> bool:
        """安装包"""
        return True


class TestEnvironmentMigration(unittest.TestCase):
    """环境迁移功能测试"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()

        # 创建模拟引擎
        self.source_engine = MockSourceEngine()
        self.target_engine = MockTargetEngine()

        # 创建迁移器
        self.migrator = EnvironmentMigrator(
            self.source_engine,
            self.target_engine,
            progress_callback=None,
        )

    def tearDown(self):
        """清理测试环境"""
        import shutil

        if hasattr(self, "temp_dir"):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_virtualenv_to_docker_migration(self):
        """测试Virtualenv到Docker迁移"""

        # 创建源环境
        source_env = self.source_engine.create_environment(
            "test_env_1", {"python": "3.12"}
        )

        # 创建快照
        source_snapshot = self.source_engine.create_snapshot("test_env_1")

        # 执行迁移
        result = self.migrator.migrate_virtualenv_to_docker(
            source_env_id="test_env_1",
            target_env_id="test_env_docker",
            include_packages=True,
            include_data=False,
        )

        # 验证结果
        self.assertTrue(result["success"])
        self.assertEqual(result["source_env_id"], "test_env_1")
        self.assertEqual(result["target_env_id"], "test_env_docker")
        self.assertEqual(result["packages_migrated"], 1)
        self.assertIn("elapsed_time", result)

    def test_docker_to_virtualenv_migration(self):
        """测试Docker到Virtualenv迁移"""

        # 创建源环境
        source_env = self.target_engine.create_environment(
            "test_env_docker", {"python": "3.12"}
        )

        # 执行迁移
        result = self.migrator.migrate_docker_to_virtualenv(
            source_env_id="test_env_docker",
            target_env_id="test_env_2",
            include_packages=True,
            include_data=False,
        )

        # 验证结果
        self.assertTrue(result["success"])
        self.assertEqual(result["source_env_id"], "test_env_docker")
        self.assertEqual(result["target_env_id"], "test_env_2")
        self.assertEqual(result["packages_migrated"], 1)
        self.assertIn("elapsed_time", result)

    def test_snapshot_cross_engine_conversion(self):
        """测试快照跨引擎转换"""

        # 创建快照
        snapshot = self.source_engine.create_snapshot("test_env_1")

        # 创建目标环境
        target_env = self.target_engine.create_environment("test_env_docker")

        # 执行转换
        converter = SnapshotCrossEngineConverter(
            self.source_engine,
            self.target_engine,
        )

        result = converter.convert_snapshot(snapshot, "test_env_docker")

        # 验证结果
        self.assertTrue(result)

    def test_progress_tracking(self):
        """测试迁移进度追踪"""

        progress_calls = []

        class TestProgress:
            def __init__(self):
                self.steps = []

            def start(self, total_steps: int):
                self.steps = []
                progress_calls.append(("start", total_steps))

            def update_step(self, step: str):
                self.steps.append(step)
                progress_calls.append(("update", step))

            def complete_step(self):
                progress_calls.append(("complete", None))

            def finish(self, success: bool = True):
                progress_calls.append(("finish", success))

        progress = TestProgress()
        progress.start(5)

        # 执行迁移
        result = self.migrator.migrate_virtualenv_to_docker(
            source_env_id="test_env_1",
            target_env_id="test_env_docker",
            include_packages=True,
            include_data=False,
            progress_callback=progress,
        )

        # 验证进度调用
        self.assertEqual(len(progress_calls), 7)  # start, 5步, complete
        self.assertIn(("start", 5), progress_calls[0])
        self.assertEqual(len([c for c in progress_calls if c[0] == "start"]), 1)
        self.assertEqual(
            len([c for c in progress_calls if c[0] == "update"]), 5
        )  # 5步更新
        self.assertEqual(
            len([c for c in progress_calls if c[0] == "complete"]), 1
        )  # 最终完成

        # 验证结果
        self.assertTrue(result["success"])
        self.assertIn("elapsed_time", result)

    def test_package_compatibility_validation(self):
        """测试包兼容性验证"""

        # 测试Virtualenv源引擎的包兼容性检查
        result1 = self.source_engine.check_package_compatibility("numpy")
        self.assertTrue(result1["compatible"])

        # 测试Docker目标引擎的包兼容性检查
        result2 = self.target_engine.check_package_compatibility("numpy")
        self.assertTrue(result2["compatible"])

        # 测试不存在的包
        result3 = self.source_engine.check_package_compatibility("nonexistent_package")
        self.assertFalse(result3["compatible"])
        self.assertIn("message", result3)

    def test_migration_error_handling(self):
        """测试迁移错误处理"""

        # 测试源环境不存在
        result1 = self.migrator.migrate_virtualenv_to_docker(
            source_env_id="nonexistent_source",
            target_env_id="test_env_docker",
            include_packages=False,
            include_data=False,
        )

        self.assertFalse(result1["success"])
        self.assertIn("error", result1)

        # 测试目标环境已存在
        self.source_engine.create_environment("test_env_existing", {"python": "3.12"})

        result2 = self.migrator.migrate_virtualenv_to_docker(
            source_env_id="test_env_existing",
            target_env_id="test_env_docker",
            include_packages=False,
            include_data=False,
        )

        self.assertFalse(result2["success"])
        self.assertIn("error", result2)


if __name__ == "__main__":
    unittest.main()
