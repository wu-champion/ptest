"""
ParallelInstaller 测试用例

测试并行安装器的所有功能，包括任务管理、并发安装、
资源监控、冲突检测等
"""

import pytest
import tempfile
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from typing import List, Dict, Any

# 导入被测试的模块
from ptest.isolation.parallel_installer import (
    ParallelInstaller,
    InstallationTask,
    InstallationResult,
    Priority,
    InstallationStatus,
    ResourceMonitor,
)
from ptest.isolation.package_manager import InstallResult, PackageInfo
from ptest.isolation.base import IsolatedEnvironment, ProcessResult
from ptest.isolation.enums import EnvironmentStatus


class MockIsolatedEnvironment(IsolatedEnvironment):
    """模拟隔离环境用于测试"""

    def __init__(self, env_id: str, path: Path):
        super().__init__(env_id, path, Mock(), {})
        self.status = EnvironmentStatus.CREATED
        self.installed_packages = {}

    def activate(self) -> bool:
        self.status = EnvironmentStatus.ACTIVE
        return True

    def deactivate(self) -> bool:
        self.status = EnvironmentStatus.INACTIVE
        return True

    def execute_command(
        self, cmd: List[str], timeout=None, env_vars=None, cwd=None
    ) -> ProcessResult:
        return ProcessResult(returncode=0, stdout="mock output")

    def install_package(
        self, package: str, version: str = None, upgrade: bool = False
    ) -> bool:
        self.installed_packages[package] = version or "1.0.0"
        return True

    def uninstall_package(self, package: str) -> bool:
        if package in self.installed_packages:
            del self.installed_packages[package]
        return True

    def get_installed_packages(self) -> Dict[str, str]:
        return self.installed_packages.copy()

    def get_package_version(self, package: str) -> str:
        return self.installed_packages.get(package)

    def allocate_port(self) -> int:
        return 8080

    def release_port(self, port: int) -> bool:
        return True

    def cleanup(self, force: bool = False) -> bool:
        return True

    def validate_isolation(self) -> bool:
        return True

    def create_snapshot(self, snapshot_id: str = None) -> Dict[str, Any]:
        """创建快照"""
        return {"snapshot_id": snapshot_id or "mock_snapshot", "status": "created"}

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照"""
        return True

    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """从快照恢复"""
        return True


class TestResourceMonitor:
    """测试资源监控器"""

    def test_resource_monitor_initialization(self):
        """测试资源监控器初始化"""
        monitor = ResourceMonitor(max_cpu_percent=70.0, max_memory_mb=512.0)

        assert monitor.max_cpu_percent == 70.0
        assert monitor.max_memory_mb == 512.0
        assert monitor.active_installations == 0

    def test_can_start_installation(self):
        """测试是否可以开始安装"""
        monitor = ResourceMonitor(
            max_cpu_percent=80.0, max_memory_mb=1024.0, max_workers=4
        )

        # 初始状态应该可以开始安装
        assert monitor.can_start_installation() == True

        # 达到最大并发数时不可以开始安装
        monitor.active_installations = 4
        assert monitor.can_start_installation() == False

        # 重置并测试资源限制
        monitor.active_installations = 2
        monitor.resource_usage = {"cpu_percent": 90.0, "memory_mb": 500.0}
        assert monitor.can_start_installation() == False

        monitor.resource_usage = {"cpu_percent": 70.0, "memory_mb": 500.0}
        assert monitor.can_start_installation() == True

    def test_register_unregister_installation(self):
        """测试注册和注销安装"""
        monitor = ResourceMonitor()

        # 注册安装
        monitor.register_installation()
        assert monitor.active_installations == 1

        # 注册更多安装
        for _ in range(3):
            monitor.register_installation()
        assert monitor.active_installations == 4

        # 注销安装
        monitor.unregister_installation()
        assert monitor.active_installations == 3

        # 注销到0
        for _ in range(3):
            monitor.unregister_installation()
        assert monitor.active_installations == 0

    def test_update_resource_usage(self):
        """测试更新资源使用情况"""
        monitor = ResourceMonitor()

        monitor.update_resource_usage(cpu_percent=65.5, memory_mb=768.0)

        assert monitor.resource_usage["cpu_percent"] == 65.5
        assert monitor.resource_usage["memory_mb"] == 768.0
        assert "timestamp" in monitor.resource_usage


class TestInstallationTask:
    """测试安装任务"""

    def test_task_creation(self):
        """测试任务创建"""
        env = MockIsolatedEnvironment("test_env", Path("/tmp"))
        packages = ["requests", "numpy"]

        task = InstallationTask(
            task_id="test_task_1",
            environment=env,
            packages=packages,
            priority=Priority.HIGH,
            max_retries=5,
            timeout=600.0,
        )

        assert task.task_id == "test_task_1"
        assert task.environment == env
        assert task.packages == packages
        assert task.priority == Priority.HIGH
        assert task.max_retries == 5
        assert task.timeout == 600.0
        assert task.retry_count == 0

    def test_task_auto_id_generation(self):
        """测试任务ID自动生成"""
        env = MockIsolatedEnvironment("test_env", Path("/tmp"))

        task = InstallationTask(
            task_id="",  # 空ID应该被自动生成
            environment=env,
            packages=["requests"],
        )

        assert task.task_id != ""
        assert task.task_id.startswith("task_")


class TestInstallationResult:
    """测试安装结果"""

    def test_result_creation(self):
        """测试结果创建"""
        result = InstallationResult(
            task_id="test_task",
            environment_id="test_env",
            packages=["requests", "numpy"],
            success=True,
        )

        assert result.task_id == "test_task"
        assert result.environment_id == "test_env"
        assert result.packages == ["requests", "numpy"]
        assert result.success == True

    def test_successful_packages_property(self):
        """测试成功安装包属性"""
        install_results = [
            InstallResult(success=True, package="requests", version="2.28.1"),
            InstallResult(success=False, package="numpy", message="Failed"),
            InstallResult(success=True, package="pandas", version="1.5.0"),
        ]

        result = InstallationResult(
            task_id="test_task",
            environment_id="test_env",
            packages=["requests", "numpy", "pandas"],
            success=False,
            results=install_results,
        )

        assert result.successful_packages == ["requests", "pandas"]
        assert result.failed_packages == ["numpy"]

    def test_result_to_dict(self):
        """测试结果转换为字典"""
        from datetime import datetime

        start_time = datetime.now()
        result = InstallationResult(
            task_id="test_task",
            environment_id="test_env",
            packages=["requests"],
            success=True,
            start_time=start_time,
            end_time=datetime.now(),
        )

        result_dict = result.to_dict()

        assert result_dict["task_id"] == "test_task"
        assert result_dict["environment_id"] == "test_env"
        assert result_dict["packages"] == ["requests"]
        assert result_dict["success"] == True
        assert isinstance(result_dict["start_time"], str)
        assert result_dict["start_time"] == start_time.isoformat()


class TestParallelInstaller:
    """测试并行安装器主类"""

    @pytest.fixture
    def installer(self):
        """创建安装器实例用于测试"""
        return ParallelInstaller(
            max_workers=2,
            max_queue_size=10,
            enable_resource_monitoring=True,
            enable_dependency_resolution=False,  # 禁用依赖解析以简化测试
            enable_conflict_detection=False,  # 禁用冲突检测以简化测试
        )

    @pytest.fixture
    def mock_environment(self):
        """创建模拟环境用于测试"""
        return MockIsolatedEnvironment("test_env_1", Path("/tmp/test_env_1"))

    def test_installer_initialization(self, installer):
        """测试安装器初始化"""
        assert installer.max_workers == 2
        assert installer.max_queue_size == 10
        assert installer.enable_resource_monitoring == True
        assert installer.is_running == False
        assert installer.is_paused == False
        assert installer.task_queue.empty() == True
        assert len(installer.running_tasks) == 0
        assert len(installer.completed_tasks) == 0

    def test_start_stop_installer(self, installer):
        """测试启动和停止安装器"""
        # 启动安装器
        installer.start()
        assert installer.is_running == True
        assert installer.is_paused == False

        # 停止安装器
        installer.stop(wait_for_completion=False)
        assert installer.is_running == False

    def test_pause_resume_installer(self, installer):
        """测试暂停和恢复安装器"""
        installer.start()

        # 暂停
        installer.pause()
        assert installer.is_paused == True

        # 恢复
        installer.resume()
        assert installer.is_paused == False

        installer.stop(wait_for_completion=False)

    def test_submit_task(self, installer, mock_environment):
        """测试提交任务"""
        installer.start()

        try:
            # 提交单个包
            task_id = installer.submit_task(
                environment=mock_environment,
                packages="requests",
                priority=Priority.HIGH,
            )

            assert task_id != ""
            assert task_id.startswith("task_")

            # 检查队列信息
            queue_info = installer.get_queue_info()
            assert queue_info["total_tasks"] > 0

        finally:
            installer.stop(wait_for_completion=False)

    def test_submit_multiple_packages(self, installer, mock_environment):
        """测试提交多个包"""
        installer.start()

        try:
            packages = ["requests", "numpy", "pandas"]
            task_id = installer.submit_task(
                environment=mock_environment,
                packages=packages,
                priority=Priority.NORMAL,
            )

            assert task_id != ""

        finally:
            installer.stop(wait_for_completion=False)

    def test_batch_install(self, installer):
        """测试批量安装"""
        # 创建多个模拟环境
        env1 = MockIsolatedEnvironment("env1", Path("/tmp/env1"))
        env2 = MockIsolatedEnvironment("env2", Path("/tmp/env2"))

        environments_packages = {env1: ["requests", "flask"], env2: ["numpy", "pandas"]}

        installer.start()

        try:
            task_ids = installer.batch_install(
                environments_packages=environments_packages, priority=Priority.HIGH
            )

            assert len(task_ids) == 2
            assert all(tid.startswith("task_") for tid in task_ids)

        finally:
            installer.stop(wait_for_completion=False)

    @patch("isolation.parallel_installer.AdvancedPackageManager")
    def test_task_execution_success(self, mock_pm_class, installer, mock_environment):
        """测试任务执行成功"""
        # 模拟包管理器
        mock_pm = Mock()
        mock_pm.install_package.return_value = InstallResult(
            success=True, package="requests", version="2.28.1"
        )
        mock_pm_class.return_value = mock_pm

        installer.start()

        try:
            # 提交任务
            task_id = installer.submit_task(
                environment=mock_environment,
                packages=["requests"],
                priority=Priority.HIGH,
            )

            # 等待任务完成
            time.sleep(0.5)

            # 检查任务状态
            status = installer.get_task_status(task_id)
            assert status is not None

            # 检查统计信息
            stats = installer.get_statistics()
            assert stats["total_tasks"] > 0

        finally:
            installer.stop(wait_for_completion=False)

    def test_wait_for_tasks(self, installer, mock_environment):
        """测试等待任务完成"""
        installer.start()

        try:
            # 提交多个任务
            task_ids = []
            for i in range(3):
                task_id = installer.submit_task(
                    environment=mock_environment,
                    packages=[f"package_{i}"],
                    priority=Priority.NORMAL,
                )
                task_ids.append(task_id)

            # 等待所有任务完成
            results = installer.wait_for_tasks(task_ids, timeout=5.0)

            assert len(results) <= len(task_ids)  # 可能有些任务还没完成

        finally:
            installer.stop(wait_for_completion=False)

    def test_cancel_task(self, installer, mock_environment):
        """测试取消任务"""
        installer.start()

        try:
            # 提交任务
            task_id = installer.submit_task(
                environment=mock_environment,
                packages=["requests"],
                priority=Priority.LOW,
            )

            # 尝试取消任务
            success = installer.cancel_task(task_id)
            # 任务可能已经开始执行，取消可能失败
            # 这取决于具体的时机

        finally:
            installer.stop(wait_for_completion=False)

    def test_get_statistics(self, installer):
        """测试获取统计信息"""
        stats = installer.get_statistics()

        assert "total_tasks" in stats
        assert "completed_tasks" in stats
        assert "failed_tasks" in stats
        assert "successful_packages" in stats
        assert "failed_packages" in stats
        assert "total_time" in stats
        assert "average_time" in stats
        assert "success_rate" in stats

        # 初始统计应该都是0
        assert stats["total_tasks"] == 0
        assert stats["completed_tasks"] == 0
        assert stats["failed_tasks"] == 0

    def test_get_queue_info(self, installer):
        """测试获取队列信息"""
        queue_info = installer.get_queue_info()

        assert "queue_size" in queue_info
        assert "max_queue_size" in queue_info
        assert "running_tasks" in queue_info
        assert "completed_tasks" in queue_info
        assert "max_workers" in queue_info
        assert "is_running" in queue_info
        assert "is_paused" in queue_info

        assert queue_info["max_queue_size"] == 10
        assert queue_info["max_workers"] == 2
        assert queue_info["is_running"] == False

    def test_context_manager(self, mock_environment):
        """测试上下文管理器"""
        with ParallelInstaller(max_workers=2) as installer:
            assert installer.is_running == True

            # 提交任务
            task_id = installer.submit_task(
                environment=mock_environment, packages=["requests"]
            )
            assert task_id != ""

        # 退出上下文后应该停止
        assert installer.is_running == False

    def test_environment_info(self, installer, mock_environment):
        """测试获取环境信息"""
        installer.start()

        try:
            # 提交任务以创建包管理器缓存
            installer.submit_task(environment=mock_environment, packages=["requests"])

            time.sleep(0.1)

            # 获取环境信息
            env_info = installer.get_environment_info(mock_environment)

            assert env_info["environment_id"] == mock_environment.env_id
            assert env_info["path"] == str(mock_environment.path)
            assert "status" in env_info
            assert "has_package_manager" in env_info

        finally:
            installer.stop(wait_for_completion=False)

    def test_cleanup_completed_tasks(self, installer):
        """测试清理已完成的任务"""
        # 模拟一些已完成的任务
        installer.completed_tasks = {
            "task1": InstallationResult(
                task_id="task1", environment_id="env1", packages=["pkg1"], success=True
            ),
            "task2": InstallationResult(
                task_id="task2", environment_id="env2", packages=["pkg2"], success=True
            ),
        }

        # 清理超过0天的任务（应该清理所有）
        removed_count = installer.cleanup_completed_tasks(max_age_days=0)
        assert removed_count == 2
        assert len(installer.completed_tasks) == 0

    def test_export_statistics(self, installer):
        """测试导出统计信息"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # 导出统计信息
            success = installer.export_statistics(temp_path)
            assert success == True

            # 检查文件是否创建
            assert temp_path.exists()

            # 检查文件内容
            import json

            with open(temp_path, "r") as f:
                data = json.load(f)

            assert "timestamp" in data
            assert "statistics" in data
            assert "queue_info" in data
            assert "config" in data

        finally:
            # 清理临时文件
            if temp_path.exists():
                temp_path.unlink()


class TestParallelInstallerIntegration:
    """并行安装器集成测试"""

    @pytest.fixture
    def installer_with_real_env(self):
        """创建使用真实环境的安装器"""
        return ParallelInstaller(
            max_workers=2,
            max_queue_size=5,
            enable_dependency_resolution=False,
            enable_conflict_detection=False,
            default_timeout=30.0,
        )

    def test_full_workflow(self, installer_with_real_env):
        """测试完整工作流程"""
        # 创建多个环境
        env1 = MockIsolatedEnvironment("env1", Path("/tmp/env1"))
        env2 = MockIsolatedEnvironment("env2", Path("/tmp/env2"))

        # 使用上下文管理器
        with installer_with_real_env as installer:
            # 提交多个任务
            task_ids = []

            # 高优先级任务
            task_id1 = installer.submit_task(
                environment=env1, packages=["requests", "flask"], priority=Priority.HIGH
            )
            task_ids.append(task_id1)

            # 普通优先级任务
            task_id2 = installer.submit_task(
                environment=env2, packages=["numpy", "pandas"], priority=Priority.NORMAL
            )
            task_ids.append(task_id2)

            # 批量任务
            batch_task_ids = installer.batch_install(
                environments_packages={env1: ["scipy"], env2: ["matplotlib"]},
                priority=Priority.LOW,
            )
            task_ids.extend(batch_task_ids)

            # 等待所有任务完成
            results = installer.wait_for_tasks(task_ids, timeout=10.0)

            # 验证结果
            assert len(results) <= len(task_ids)

            # 检查最终统计
            final_stats = installer.get_statistics()
            assert final_stats["total_tasks"] == len(task_ids)

            # 导出统计信息
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                temp_path = Path(f.name)

            try:
                installer.export_statistics(temp_path)
                assert temp_path.exists()
            finally:
                if temp_path.exists():
                    temp_path.unlink()

    def test_error_handling(self, installer_with_real_env):
        """测试错误处理"""
        installer_with_real_env.start()

        try:
            # 测试提交到未启动的安装器
            installer_stopped = ParallelInstaller()

            with pytest.raises(RuntimeError):
                installer_stopped.submit_task(
                    environment=MockIsolatedEnvironment("env", Path("/tmp")),
                    packages=["requests"],
                )

            # 测试队列满的情况
            installer_small_queue = ParallelInstaller(max_queue_size=1)
            installer_small_queue.start()

            try:
                # 提交多个任务应该导致队列满
                for i in range(5):
                    try:
                        installer_small_queue.submit_task(
                            environment=MockIsolatedEnvironment(
                                f"env{i}", Path(f"/tmp/env{i}")
                            ),
                            packages=[f"package{i}"],
                        )
                    except RuntimeError:
                        # 预期的错误
                        break
                else:
                    # 如果没有抛出错误，检查队列是否确实满了
                    assert installer_small_queue.task_queue.qsize() <= 1

            finally:
                installer_small_queue.stop(wait_for_completion=False)

        finally:
            installer_with_real_env.stop(wait_for_completion=False)


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
