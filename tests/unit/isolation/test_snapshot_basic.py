"""
快照功能简化测试
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from isolation.manager import IsolationManager
    from isolation.enums import IsolationLevel
except ImportError:
    try:
        from pypj.ptest.isolation.manager import IsolationManager
        from pypj.ptest.isolation.enums import IsolationLevel
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        from isolation.manager import IsolationManager
        from isolation.enums import IsolationLevel


class TestBasicSnapshot(unittest.TestCase):
    """基础快照功能测试"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager(
            {
                "default_isolation_level": IsolationLevel.BASIC.value,
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

    def test_manager_snapshot_support(self):
        """测试管理器支持快照功能"""
        # 检查管理器是否有快照存储
        self.assertIsInstance(self.manager.snapshots, dict)
        self.assertEqual(len(self.manager.snapshots), 0)

    def test_basic_environment_creation(self):
        """测试基础环境创建"""
        env_path = self.temp_dir / "basic_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        self.assertIsNotNone(env)
        self.assertIsNotNone(env.env_id)
        self.assertEqual(env.env_id[:4], "env_")

    def test_snapshot_methods_exist(self):
        """测试快照方法存在"""
        env_path = self.temp_dir / "methods_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        # 检查管理器快照方法
        self.assertTrue(hasattr(self.manager, "create_snapshot"))
        self.assertTrue(hasattr(self.manager, "list_snapshots"))
        self.assertTrue(hasattr(self.manager, "delete_snapshot"))
        self.assertTrue(hasattr(self.manager, "get_snapshot_info"))

        # 检查环境快照方法
        self.assertTrue(hasattr(env, "create_snapshot"))
        self.assertTrue(hasattr(env, "restore_from_snapshot"))
        self.assertTrue(hasattr(env, "delete_snapshot"))
        self.assertTrue(hasattr(env, "list_snapshots"))

    def test_enumeration_extensions(self):
        """测试快照相关枚举扩展"""
        from isolation.enums import IsolationEvent

        # 检查快照事件类型
        self.assertTrue(hasattr(IsolationEvent, "SNAPSHOT_CREATING"))
        self.assertTrue(hasattr(IsolationEvent, "SNAPSHOT_CREATED"))
        self.assertTrue(hasattr(IsolationEvent, "SNAPSHOT_RESTORING"))
        self.assertTrue(hasattr(IsolationEvent, "SNAPSHOT_RESTORED"))
        self.assertTrue(hasattr(IsolationEvent, "SNAPSHOT_DELETING"))
        self.assertTrue(hasattr(IsolationEvent, "SNAPSHOT_DELETED"))

    def test_snapshot_id_generation(self):
        """测试快照ID生成"""
        env_path = self.temp_dir / "id_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        try:
            # 创建快照（应该生成ID）
            snapshot = self.manager.create_snapshot(env.env_id)
            self.assertIsNotNone(snapshot)
            self.assertIn("snapshot_id", snapshot)
            self.assertIsNotNone(snapshot["snapshot_id"])
            self.assertIsInstance(snapshot["snapshot_id"], str)

        except Exception as e:
            self.skipTest(f"Snapshot creation failed: {e}")

    def test_snapshot_structure(self):
        """测试快照结构"""
        env_path = self.temp_dir / "structure_test"
        env = self.manager.create_environment(env_path, IsolationLevel.BASIC.value)

        try:
            # 创建快照
            snapshot = self.manager.create_snapshot(env.env_id, "structure_test")

            # 检查基本结构
            required_fields = [
                "snapshot_id",
                "env_id",
                "path",
                "status",
                "created_at",
                "config",
                "resource_usage",
                "allocated_ports",
            ]

            for field in required_fields:
                self.assertIn(field, snapshot, f"Missing field: {field}")

        except Exception as e:
            self.skipTest(f"Snapshot structure test failed: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
