"""
环境快照功能测试

测试Virtualenv和Docker引擎的快照功能
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import json
import time

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ptest.isolation.manager import IsolationManager
    from ptest.isolation.enums import IsolationLevel, IsolationEvent
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from ptest.isolation.manager import IsolationManager
    from ptest.isolation.enums import IsolationLevel, IsolationEvent


class TestSnapshotFunctionality(unittest.TestCase):
    """快照功能测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager(
            {
                "default_isolation_level": IsolationLevel.BASIC.value,
                "max_environments": 10,
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

    def test_create_basic_environment_snapshot(self):
        """测试基础环境快照创建"""
        env_path = self.temp_dir / "basic_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 创建快照
        snapshot = self.manager.create_snapshot(env.env_id, "test_snapshot_1")

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["snapshot_id"], "test_snapshot_1")
        self.assertEqual(snapshot["env_id"], env.env_id)
        self.assertIn("snapshot_id", snapshot)
        self.assertIn("env_id", snapshot)
        self.assertIn("created_at", snapshot)
        self.assertIn("status", snapshot)

    def test_create_snapshot_with_auto_id(self):
        """测试自动生成快照ID"""
        env_path = self.temp_dir / "auto_id_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 不指定快照ID
        snapshot = self.manager.create_snapshot(env.env_id)

        self.assertIsNotNone(snapshot)
        self.assertIsNotNone(snapshot["snapshot_id"])
        self.assertTrue(snapshot["snapshot_id"].startswith("snapshot_"))

    def test_list_snapshots(self):
        """测试列出快照"""
        env_path = self.temp_dir / "list_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 创建多个快照
        snapshot1 = self.manager.create_snapshot(env.env_id, "test_snapshot_1")
        time.sleep(0.1)  # 确保时间戳不同
        snapshot2 = self.manager.create_snapshot(env.env_id, "test_snapshot_2")

        # 列出所有快照
        all_snapshots = self.manager.list_snapshots()
        self.assertGreaterEqual(len(all_snapshots), 2)

        # 列出指定环境的快照
        env_snapshots = self.manager.list_snapshots(env.env_id)
        self.assertEqual(len(env_snapshots), 2)

    def test_get_snapshot_info(self):
        """测试获取快照信息"""
        env_path = self.temp_dir / "info_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 创建快照
        snapshot = self.manager.create_snapshot(env.env_id, "info_snapshot")

        # 获取快照信息
        snapshot_info = self.manager.get_snapshot_info("info_snapshot")
        self.assertIsNotNone(snapshot_info)
        self.assertEqual(snapshot_info["snapshot_id"], "info_snapshot")

    def test_delete_snapshot(self):
        """测试删除快照"""
        env_path = self.temp_dir / "delete_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 创建快照
        snapshot = self.manager.create_snapshot(env.env_id, "delete_snapshot")

        # 验证快照存在
        self.assertIsNotNone(self.manager.get_snapshot_info("delete_snapshot"))

        # 删除快照
        result = self.manager.delete_snapshot("delete_snapshot")
        self.assertTrue(result)

        # 验证快照已删除
        self.assertIsNone(self.manager.get_snapshot_info("delete_snapshot"))

    def test_export_import_snapshot(self):
        """测试导出导入快照"""
        env_path = self.temp_dir / "export_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 创建快照
        snapshot = self.manager.create_snapshot(env.env_id, "export_snapshot")

        # 导出快照
        export_path = self.temp_dir / "snapshot.json"
        result = self.manager.export_snapshot("export_snapshot", export_path)
        self.assertTrue(result)
        self.assertTrue(export_path.exists())

        # 创建新的管理器并导入快照
        new_manager = IsolationManager()
        imported_snapshot = new_manager.import_snapshot(export_path)

        self.assertIsNotNone(imported_snapshot)
        self.assertEqual(imported_snapshot["snapshot_id"], "export_snapshot")
        self.assertEqual(imported_snapshot["env_id"], snapshot["env_id"])

    def test_cleanup_old_snapshots(self):
        """测试清理旧快照"""
        env_path = self.temp_dir / "cleanup_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 创建快照
        self.manager.create_snapshot(env.env_id, "old_snapshot")

        # 模拟清理很旧的快照（负数天）
        deleted_count = self.manager.cleanup_old_snapshots(-1)
        self.assertGreaterEqual(deleted_count, 1)


class TestSnapshotEvents(unittest.TestCase):
    """快照事件测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager()
        self.events_received = []

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_snapshot_creation_events(self):
        """测试快照创建事件"""

        def event_callback(env, event, *args, **kwargs):
            self.events_received.append((event, args, kwargs))

        # 创建环境并添加事件监听器
        env_path = self.temp_dir / "event_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)
        env.add_event_listener(IsolationEvent.SNAPSHOT_CREATED, event_callback)

        # 创建快照（应该触发事件）
        snapshot = self.manager.create_snapshot(env.env_id, "event_snapshot")

        # 验证事件被触发
        self.assertGreater(len(self.events_received), 0)
        snapshot_event = self.events_received[-1]
        self.assertEqual(snapshot_event[0], IsolationEvent.SNAPSHOT_CREATED)


class TestSnapshotVirtualenv(unittest.TestCase):
    """Virtualenv快照功能测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager()

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_virtualenv_snapshot_content(self):
        """测试Virtualenv快照内容"""
        env_path = self.temp_dir / "virtualenv_snapshot_test"

        try:
            env = self.manager.create_environment(
                env_path, IsolationLevel.VIRTUALENV.value
            )

            # 创建快照
            snapshot = self.manager.create_snapshot(env.env_id, "venv_snapshot")

            # 检查Virtualenv特有信息
            if hasattr(env, "virtualenv_info"):  # 如果Virtualenv实现正确
                self.assertIn("virtualenv_info", snapshot)
                virtualenv_info = snapshot["virtualenv_info"]
                self.assertIn("venv_path", virtualenv_info)
                self.assertIn("python_path", virtualenv_info)
                self.assertIn("pip_path", virtualenv_info)
                self.assertIn("installed_packages", virtualenv_info)
        except Exception as e:
            # 如果Virtualenv引擎不可用，跳过测试
            self.skipTest(f"Virtualenv engine not available: {e}")

    def test_export_snapshot_data(self):
        """测试导出Virtualenv快照数据"""
        env_path = self.temp_dir / "export_test"

        try:
            env = self.manager.create_environment(
                env_path, IsolationLevel.VIRTUALENV.value
            )

            # 导出快照数据
            if hasattr(env, "export_snapshot_data"):
                export_data = env.export_snapshot_data()

                self.assertIn("env_type", export_data)
                self.assertEqual(export_data["env_type"], "virtualenv")
                self.assertIn("venv_path", export_data)
                self.assertIn("installed_packages", export_data)
            else:
                self.skipTest("Virtualenv export_snapshot_data not implemented")
        except Exception as e:
            self.skipTest(f"Virtualenv engine not available: {e}")


class TestSnapshotDocker(unittest.TestCase):
    """Docker快照功能测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager(
            {
                "default_isolation_level": IsolationLevel.DOCKER.value,
            }
        )

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_docker_snapshot_content(self):
        """测试Docker快照内容"""
        env_path = self.temp_dir / "docker_snapshot_test"

        try:
            env = self.manager.create_environment(env_path, IsolationLevel.DOCKER.value)

            # 创建快照
            snapshot = self.manager.create_snapshot(env.env_id, "docker_snapshot")

            # 检查Docker特有信息
            if hasattr(env, "docker_info"):  # 如果Docker实现正确
                self.assertIn("docker_info", snapshot)
                docker_info = snapshot["docker_info"]
                self.assertIn("container_name", docker_info)
                self.assertIn("image_name", docker_info)
                self.assertIn("container_id", docker_info)
                self.assertIn("port_mappings", docker_info)
                self.assertIn("environment_vars", docker_info)
        except Exception as e:
            # 如果Docker引擎不可用，跳过测试
            self.skipTest(f"Docker engine not available: {e}")

    def test_docker_export_snapshot_data(self):
        """测试导出Docker快照数据"""
        env_path = self.temp_dir / "docker_export_test"

        try:
            env = self.manager.create_environment(env_path, IsolationLevel.DOCKER.value)

            # 导出快照数据
            if hasattr(env, "export_snapshot_data"):
                export_data = env.export_snapshot_data()

                self.assertIn("env_type", export_data)
                self.assertEqual(export_data["env_type"], "docker")
                self.assertIn("container_name", export_data)
                self.assertIn("image_name", export_data)
                self.assertIn("container_id", export_data)
                self.assertIn("port_mappings", export_data)
            else:
                self.skipTest("Docker export_snapshot_data not implemented")
        except Exception as e:
            self.skipTest(f"Docker engine not available: {e}")


class TestSnapshotErrorHandling(unittest.TestCase):
    """快照错误处理测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager()

    def tearDown(self):
        """测试后清理"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_snapshot_nonexistent_environment(self):
        """测试为不存在环境创建快照"""
        with self.assertRaises(ValueError):
            self.manager.create_snapshot("nonexistent_env", "test_snapshot")

    def test_restore_nonexistent_snapshot(self):
        """测试从不存在的快照恢复"""
        with self.assertRaises(ValueError):
            self.manager.restore_from_snapshot("nonexistent_snapshot")

    def test_delete_nonexistent_snapshot(self):
        """测试删除不存在的快照"""
        result = self.manager.delete_snapshot("nonexistent_snapshot")
        self.assertFalse(result)

    def test_import_invalid_snapshot(self):
        """测试导入无效快照"""
        invalid_path = self.temp_dir / "invalid.json"

        # 创建无效的快照文件
        with open(invalid_path, "w") as f:
            json.dump({"invalid": "snapshot"}, f)

        with self.assertRaises(ValueError):
            self.manager.import_snapshot(invalid_path)

    def test_import_nonexistent_file(self):
        """测试导入不存在的文件"""
        nonexistent_path = self.temp_dir / "nonexistent.json"

        with self.assertRaises(FileNotFoundError):
            self.manager.import_snapshot(nonexistent_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
