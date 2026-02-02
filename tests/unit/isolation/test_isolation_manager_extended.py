"""
隔离管理器功能测试

测试IsolationManager的关键功能
"""

import unittest
from pathlib import Path
import tempfile
import shutil


class TestIsolationManagerBasic(unittest.TestCase):
    """测试隔离管理器基础功能"""

    def setUp(self):
        """设置测试环境"""
        from ptest.isolation.manager import IsolationManager

        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IsolationManager({})

    def tearDown(self):
        """清理测试环境"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_manager_initialization(self):
        """测试管理器初始化"""
        self.assertIsNotNone(self.manager)
        self.assertIsInstance(self.manager.config, dict)
        self.assertIsInstance(self.manager.engines, dict)
        self.assertIsInstance(self.manager.active_environments, dict)

    def test_list_environments_empty(self):
        """测试空环境列表"""
        environments = self.manager.list_environments()
        self.assertIsInstance(environments, dict)
        self.assertEqual(len(environments), 0)

    def test_get_environment_not_found(self):
        """测试获取不存在的环境"""
        env = self.manager.get_environment("nonexistent")
        self.assertIsNone(env)

    def test_cleanup_nonexistent_environment(self):
        """测试清理不存在的环境"""
        result = self.manager.cleanup_environment("nonexistent")
        self.assertFalse(result)

    def test_get_manager_status(self):
        """测试获取管理器状态"""
        status = self.manager.get_manager_status()
        self.assertIsInstance(status, dict)
        self.assertIn("total_environments", status)
        self.assertIn("available_engines", status)
        self.assertIn("default_isolation_level", status)


class TestIsolationManagerEngines(unittest.TestCase):
    """测试隔离管理器引擎功能"""

    def setUp(self):
        """设置测试环境"""
        from ptest.isolation.manager import IsolationManager

        self.manager = IsolationManager({})

    def test_list_available_engines(self):
        """测试列出可用引擎"""
        engines = self.manager.list_available_engines()
        self.assertIsInstance(engines, dict)
        # 应该至少包含内置引擎
        self.assertTrue(len(engines) >= 3)
        # 检查每个引擎的格式
        for level, info in engines.items():
            self.assertIn("name", info)
            self.assertIn("supported_features", info)

    def test_get_engine_info(self):
        """测试获取引擎信息"""
        info = self.manager.get_engine_info("basic")
        self.assertIsNotNone(info)
        # 返回的key是"name"而不是"engine_type"
        self.assertIn("name", info)
        self.assertIn("supported_features", info)

    def test_set_default_isolation_level(self):
        """测试设置默认隔离级别"""
        # 方法没有返回值，直接检查状态变化
        self.manager.set_default_isolation_level("virtualenv")
        self.assertEqual(self.manager.default_isolation_level, "virtualenv")


class TestIsolationManagerStatus(unittest.TestCase):
    """测试隔离管理器状态查询"""

    def setUp(self):
        """设置测试环境"""
        from ptest.isolation.manager import IsolationManager

        self.manager = IsolationManager({})
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """清理测试环境"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_get_environment_status_no_env(self):
        """测试无环境时的状态查询"""
        # 不存在的环境应该返回包含"status"键的字典
        status = self.manager.get_environment_status("nonexistent")
        self.assertIsInstance(status, dict)
        self.assertIn("status", status)


class TestAutoSelection(unittest.TestCase):
    """测试自动选择功能"""

    def setUp(self):
        """设置测试环境"""
        from ptest.isolation.manager import IsolationManager

        self.manager = IsolationManager({})

    def test_auto_select_basic(self):
        """测试基本自动选择"""
        level = self.manager.auto_select_isolation_level({})
        self.assertIsNotNone(level)
        self.assertIn(level, ["basic", "virtualenv", "docker"])

    def test_auto_select_with_limits(self):
        """测试带资源限制的自动选择"""
        level = self.manager.auto_select_isolation_level({"cpus": 2.0, "memory": "4g"})
        self.assertIsNotNone(level)
        self.assertIn(level, ["basic", "virtualenv", "docker"])

    def test_get_recommendations_no_env(self):
        """测试无环境时获取推荐会返回错误"""
        recommendations = self.manager.get_environment_recommendations("nonexistent")
        self.assertIsInstance(recommendations, dict)
        self.assertIn("error", recommendations)


class TestSnapshotManagement(unittest.TestCase):
    """测试快照管理功能"""

    def setUp(self):
        """设置测试环境"""
        from ptest.isolation.manager import IsolationManager

        self.manager = IsolationManager({})
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """清理测试环境"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_list_snapshots_no_env(self):
        """测试无环境时列出快照"""
        snapshots = self.manager.list_snapshots("nonexistent")
        self.assertEqual(snapshots, [])

    def test_get_snapshot_info_no_snap(self):
        """测试无快照时获取信息"""
        info = self.manager.get_snapshot_info("snap_001")
        self.assertIsNone(info)


class TestMetricsCollection(unittest.TestCase):
    """测试指标收集功能"""

    def setUp(self):
        """设置测试环境"""
        from ptest.isolation.manager import IsolationManager

        self.manager = IsolationManager({})
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """清理测试环境"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_collect_metrics_no_env(self):
        """测试无环境时收集指标"""
        metrics = self.manager.collect_environment_metrics()
        self.assertIsInstance(metrics, dict)
        self.assertEqual(len(metrics), 0)


class TestHealthCheck(unittest.TestCase):
    """测试健康检查功能"""

    def setUp(self):
        """设置测试环境"""
        from ptest.isolation.manager import IsolationManager

        self.manager = IsolationManager({})
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """清理测试环境"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_check_health_no_env(self):
        """测试无环境时检查健康"""
        health = self.manager.check_environments_health()
        self.assertIsInstance(health, dict)
        self.assertEqual(len(health), 0)


class TestBulkOperations(unittest.TestCase):
    """测试批量操作功能"""

    def setUp(self):
        """设置测试环境"""
        from ptest.isolation.manager import IsolationManager

        self.manager = IsolationManager({})
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """清理测试环境"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_cleanup_all_no_env(self):
        """测试无环境时清理所有"""
        # 没有环境时返回0（清理数量）
        result = self.manager.cleanup_all_environments()
        self.assertEqual(result, 0)

    def test_cleanup_old_snapshots_no_env(self):
        """测试无快照时清理旧快照"""
        count = self.manager.cleanup_old_snapshots(days_old=30)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
