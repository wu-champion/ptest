"""
并行安装器 (ParallelInstaller)

提供高效的并行包安装功能，支持多个隔离环境的同时包安装，
包含冲突检测、依赖解析、资源管理等高级功能。
"""

import os
import sys
import time
import threading
import queue
import uuid
from typing import Dict, List, Optional, Set, Tuple, Any, Union, Callable
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from enum import Enum
import json
import logging

from .package_manager import (
    AdvancedPackageManager,
    InstallResult,
    UninstallResult,
    PackageInfo,
)
from .base import IsolatedEnvironment
from .enums import IsolationEvent, EnvironmentStatus
from .dependency_resolver import DependencyResolver
from .conflict_detector import ConflictDetector
from core import get_logger

logger = get_logger("parallel_installer")


class InstallationStatus(Enum):
    """安装状态枚举"""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class Priority(Enum):
    """安装优先级枚举"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class InstallationTask:
    """安装任务数据类"""

    task_id: str
    environment: IsolatedEnvironment
    packages: List[str]
    priority: Priority = Priority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    timeout: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    requirements_file: Optional[Path] = None
    upgrade: bool = False
    force_reinstall: bool = False
    ignore_deps: bool = False
    editable: bool = False
    callback: Optional[Callable[[str, 'InstallationResult'], None]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """生成任务ID如果没有提供"""
        if not self.task_id:
            self.task_id = f"task_{uuid.uuid4().hex[:12]}"


@dataclass
class InstallationResult:
    """安装结果数据类"""

    task_id: str
    environment_id: str
    packages: List[str]
    success: bool
    results: List[InstallResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: float = 0.0
    error_message: str = ""
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def successful_packages(self) -> List[str]:
        """成功安装的包列表"""
        return [r.package for r in self.results if r.success]

    @property
    def failed_packages(self) -> List[str]:
        """失败的包列表"""
        return [r.package for r in self.results if not r.success]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "environment_id": self.environment_id,
            "packages": self.packages,
            "success": self.success,
            "successful_packages": self.successful_packages,
            "failed_packages": self.failed_packages,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
            "results": [r.__dict__ for r in self.results],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InstallationResult':
        """从字典创建实例"""
        # 处理时间字段
        start_time = None
        if data.get("start_time"):
            start_time = datetime.fromisoformat(data["start_time"])
        
        end_time = None
        if data.get("end_time"):
            end_time = datetime.fromisoformat(data["end_time"])

        # 处理结果字段
        results = []
        for result_data in data.get("results", []):
            if isinstance(result_data, dict):
                results.append(InstallResult(**result_data))

        return cls(
            task_id=data["task_id"],
            environment_id=data["environment_id"],
            packages=data["packages"],
            success=data["success"],
            results=results,
            start_time=start_time,
            end_time=end_time,
            duration=data["duration"],
            error_message=data.get("error_message", ""),
            retry_count=data.get("retry_count", 0),
            metadata=data.get("metadata", {}),
        )


class ResourceMonitor:
    """资源监控器"""

    def __init__(self, max_cpu_percent: float = 80.0, max_memory_mb: float = 1024.0, max_workers: int = 4):
        self.max_cpu_percent = max_cpu_percent
        self.max_memory_mb = max_memory_mb
        self.max_workers = max_workers
        self.active_installations = 0
        self.resource_usage = {}
        self.lock = threading.Lock()

    def can_start_installation(self) -> bool:
        """检查是否可以开始新的安装"""
        with self.lock:
            if self.active_installations >= 4:  # 最大并发数限制
                return False

            # 检查资源使用情况
            current_cpu = self.resource_usage.get("cpu_percent", 0.0)
            current_memory = self.resource_usage.get("memory_mb", 0.0)

            if (
                current_cpu > self.max_cpu_percent
                or current_memory > self.max_memory_mb
            ):
                return False

            return True

    def register_installation(self):
        """注册新的安装任务"""
        with self.lock:
            self.active_installations += 1

    def unregister_installation(self):
        """注销安装任务"""
        with self.lock:
            self.active_installations = max(0, self.active_installations - 1)

    def update_resource_usage(self, cpu_percent: float, memory_mb: float):
        """更新资源使用情况"""
        with self.lock:
            self.resource_usage["cpu_percent"] = cpu_percent
            self.resource_usage["memory_mb"] = memory_mb
            self.resource_usage["timestamp"] = datetime.now()


class ParallelInstaller:
    """并行安装器主类"""

    def __init__(
        self,
        max_workers: int = 4,
        max_queue_size: int = 100,
        enable_resource_monitoring: bool = True,
        enable_dependency_resolution: bool = True,
        enable_conflict_detection: bool = True,
        default_timeout: float = 300.0,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化并行安装器

        Args:
            max_workers: 最大工作线程数
            max_queue_size: 最大队列大小
            enable_resource_monitoring: 是否启用资源监控
            enable_dependency_resolution: 是否启用依赖解析
            enable_conflict_detection: 是否启用冲突检测
            default_timeout: 默认超时时间（秒）
            config: 配置选项
        """
        self.config = config or {}
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.default_timeout = default_timeout

        # 功能开关
        self.enable_resource_monitoring = enable_resource_monitoring
        self.enable_dependency_resolution = enable_dependency_resolution
        self.enable_conflict_detection = enable_conflict_detection

        # 初始化组件
        self.resource_monitor = (
            ResourceMonitor() if enable_resource_monitoring else None
        )
        self.dependency_resolver = (
            None  # Will be initialized with package manager when needed
        )
        self.conflict_detector = (
            None  # Will be initialized with package manager when needed
        )

        # 任务队列和执行器
        self.task_queue = queue.PriorityQueue(maxsize=max_queue_size)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.running_tasks: Dict[str, Future] = {}
        self.completed_tasks: Dict[str, InstallationResult] = {}

        # 状态管理
        self.is_running = False
        self.is_paused = False
        self.task_counter = 0
        self.start_time = None
        self.stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "successful_packages": 0,
            "failed_packages": 0,
            "total_time": 0.0,
            "average_time": 0.0,
            "peak_queue_size": 0,
            "peak_active_tasks": 0,
            "total_wait_time": 0.0,
            "workers_active": 0,
        }

        # 线程安全
        self.lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()  # 初始为运行状态

        # 包管理器缓存
        self.package_managers: Dict[str, AdvancedPackageManager] = {}

        logger.info(f"ParallelInstaller initialized with max_workers={max_workers}")

    def start(self):
        """启动并行安装器"""
        if self.is_running:
            logger.warning("ParallelInstaller is already running")
            return

        self.is_running = True
        self.is_paused = False
        self.start_time = datetime.now()
        self.pause_event.set()

        # 启动工作线程
        for i in range(self.max_workers):
            threading.Thread(
                target=self._worker_loop, daemon=True, name=f"ParallelInstaller-Worker-{i}"
            ).start()

        logger.info(f"ParallelInstaller started with {self.max_workers} workers")

    def stop(self, wait_for_completion: bool = True, timeout: Optional[float] = None):
        """停止并行安装器"""
        self.is_running = False

        if wait_for_completion:
            # 等待所有任务完成
            self.executor.shutdown(wait=True)
        else:
            # 取消所有任务
            for task_id, future in self.running_tasks.items():
                future.cancel()
            self.executor.shutdown(wait=False)

        logger.info(f"ParallelInstaller stopped. Stats: {self.stats}")

    def pause(self):
        """暂停安装器"""
        self.is_paused = True
        self.pause_event.clear()
        logger.info("ParallelInstaller paused")

    def resume(self):
        """恢复安装器"""
        self.is_paused = False
        self.pause_event.set()
        logger.info("ParallelInstaller resumed")

    def submit_task(
        self,
        environment: IsolatedEnvironment,
        packages: Union[str, List[str]],
        priority: Priority = Priority.NORMAL,
        **kwargs,
    ) -> str:
        """
        提交安装任务

        Args:
            environment: 目标隔离环境
            packages: 要安装的包列表
            priority: 任务优先级
            **kwargs: 其他任务参数

        Returns:
            任务ID
            
        Raises:
            RuntimeError: 当安装器未运行时
            ValueError: 当包列表为空时
            TypeError: 当参数类型不正确时
        """
        if not self.is_running:
            raise RuntimeError("ParallelInstaller is not running")
            
        # 验证输入参数
        if not environment:
            raise ValueError("Environment cannot be None")
            
        if not packages:
            raise ValueError("Packages cannot be empty")
            
        if not isinstance(environment, IsolatedEnvironment):
            raise TypeError(f"Expected IsolatedEnvironment, got {type(environment)}")

        # 标准化包列表
        if isinstance(packages, str):
            packages = [packages]

        # 创建任务
        task = InstallationTask(
            task_id=f"task_{self.task_counter}_{uuid.uuid4().hex[:8]}",
            environment=environment,
            packages=packages,
            priority=priority,
            **kwargs,
        )

        # 依赖解析
        if self.enable_dependency_resolution and self.dependency_resolver:
            try:
                resolved_tree = self.dependency_resolver.resolve_dependencies(
                    packages[0] if len(packages) == 1 else packages[0]
                )
                if hasattr(resolved_tree, "get_all_dependencies"):
                    for pkg in packages:
                        deps = resolved_tree.get_all_dependencies(pkg)
                        task.dependencies.extend(list(deps))
                logger.debug(f"Resolved dependencies for task {task.task_id}")
            except Exception as e:
                logger.warning(
                    f"Dependency resolution failed for task {task.task_id}: {e}"
                )

        # 冲突检测
        if self.enable_conflict_detection and self.conflict_detector:
            try:
                conflict_analysis = self.conflict_detector.detect_version_conflicts(
                    packages
                )
                if conflict_analysis.total_conflicts > 0:
                    conflicts = []
                    for pkg in conflict_analysis.conflicts_by_package:
                        pkg_conflicts = conflict_analysis.conflicts_by_package[pkg]
                        for conflict in pkg_conflicts:
                            conflicts.append(
                                {
                                    "package": conflict.package,
                                    "error_message": conflict.error_message,
                                    "severity": conflict.severity,
                                }
                            )
                    logger.warning(
                        f"Package conflicts detected for task {task.task_id}: {len(conflicts)} conflicts"
                    )
                    task.metadata["conflicts"] = conflicts
            except Exception as e:
                logger.warning(
                    f"Conflict detection failed for task {task.task_id}: {e}"
                )

        # 添加到队列
        try:
            # 使用负优先级值，因为PriorityQueue是最小堆
            queue_item = (-priority.value, task.task_id, task)
            self.task_queue.put(queue_item, timeout=5.0)

            with self.lock:
                self.task_counter += 1
                self.stats["total_tasks"] += 1

            logger.info(
                f"Submitted installation task {task.task_id} for packages: {packages}"
            )
            return task.task_id

        except queue.Full:
            raise RuntimeError("Task queue is full. Cannot submit new task.")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        with self.lock:
            # 检查运行中的任务
            if task_id in self.running_tasks:
                future = self.running_tasks[task_id]
                return {
                    "task_id": task_id,
                    "status": "running" if future.running() else "pending",
                    "cancelled": future.cancelled(),
                    "done": future.done(),
                }

            # 检查已完成的任务
            if task_id in self.completed_tasks:
                result = self.completed_tasks[task_id]
                return {
                    "task_id": task_id,
                    "status": "completed" if result.success else "failed",
                    "result": result.to_dict(),
                }

        return None

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self.lock:
            if task_id in self.running_tasks:
                future = self.running_tasks[task_id]
                success = future.cancel()
                if success:
                    del self.running_tasks[task_id]
                    logger.info(f"Cancelled task {task_id}")
                return success

        return False

    def get_queue_info(self) -> Dict[str, Any]:
        """获取队列信息"""
        with self.lock:
            return {
                "queue_size": self.task_queue.qsize(),
                "max_queue_size": self.max_queue_size,
                "running_tasks": len(self.running_tasks),
                "completed_tasks": len(self.completed_tasks),
                "max_workers": self.max_workers,
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "total_tasks": self.stats.get("total_tasks", 0),
            }

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            stats = self.stats.copy()

            # 计算平均时间
            if stats["completed_tasks"] > 0:
                stats["average_time"] = stats["total_time"] / stats["completed_tasks"]

            # 计算成功率
            if stats["total_tasks"] > 0:
                stats["success_rate"] = (
                    stats["completed_tasks"] / stats["total_tasks"]
                ) * 100
            else:
                stats["success_rate"] = 0.0

            return stats

    def _worker_loop(self):
        """工作线程主循环"""
        logger.info(f"Worker loop started with {self.max_workers} workers")
        worker_id = threading.current_thread().name
        
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self.is_running:
            try:
                # 等待任务或停止信号
                if not self.pause_event.wait(timeout=1.0):
                    # 暂停状态，继续等待
                    continue

                # 检查资源限制
                if (
                    self.resource_monitor
                    and not self.resource_monitor.can_start_installation()
                ):
                    logger.debug(f"Resource limit reached, worker {worker_id} waiting")
                    time.sleep(0.1)
                    continue

                # 获取任务
                try:
                    priority, task_id, task = self.task_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                logger.debug(f"Worker {worker_id} picked up task {task_id}")
                
                # 提交任务到线程池
                try:
                    future = self.executor.submit(self._execute_task, task)

                    with self.lock:
                        self.running_tasks[task_id] = future

                    # 注册资源使用
                    if self.resource_monitor:
                        self.resource_monitor.register_installation()

                    logger.debug(f"Submitted task {task_id} to executor")

                except Exception as submit_error:
                    logger.error(f"Failed to submit task {task_id} to executor: {submit_error}")
                    # 将任务放回队列
                    try:
                        self.task_queue.put((priority, task_id, task), timeout=1.0)
                    except queue.Full:
                        logger.error(f"Failed to re-queue task {task_id}, queue is full")
                    continue

                # 重置错误计数
                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in worker loop {worker_id} (consecutive errors: {consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Too many consecutive errors in worker {worker_id}, stopping loop")
                    break
                    
                time.sleep(min(0.1 * consecutive_errors, 1.0))  # Exponential backoff

        logger.info(f"Worker loop {worker_id} finished")

    def _execute_task(self, task: InstallationTask) -> InstallationResult:
        """执行安装任务"""
        start_time = datetime.now()
        logger.info(f"Executing installation task {task.task_id}")
        result = None

        try:
            # 获取或创建包管理器
            package_manager = self._get_package_manager(task.environment)

            # 执行安装
            results = []
            all_success = True

            for package in task.packages:
                try:
                    result = package_manager.install_package(
                        package=package,
                        upgrade=task.upgrade,
                        force_reinstall=task.force_reinstall,
                        ignore_deps=task.ignore_deps,
                        editable=task.editable,
                        constraints=task.constraints,
                        requirements_file=task.requirements_file,
                    )

                    results.append(result)

                    if not result.success:
                        all_success = False
                        logger.error(
                            f"Failed to install package {package}: {result.error_details}"
                        )
                    else:
                        logger.info(
                            f"Successfully installed package {package} v{result.version}"
                        )

                except Exception as e:
                    logger.error(f"Exception installing package {package}: {e}")
                    results.append(
                        InstallResult(
                            success=False,
                            package=package,
                            message=f"Exception during installation: {e}",
                            error_details=str(e),
                        )
                    )
                    all_success = False

            # 创建结果
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            result = InstallationResult(
                task_id=task.task_id,
                environment_id=task.environment.env_id,
                packages=task.packages,
                success=all_success,
                results=results,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                retry_count=task.retry_count,
                metadata=task.metadata.copy(),
            )

            # 更新统计信息
            self._update_statistics(result)

            # 调用回调函数
            if task.callback:
                try:
                    task.callback(task.task_id, result)
                except Exception as e:
                    logger.error(f"Error in task callback: {e}")

            return result

        except Exception as e:
            logger.error(f"Exception executing task {task.task_id}: {e}")

            # 创建错误结果
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            result = InstallationResult(
                task_id=task.task_id,
                environment_id=task.environment.env_id,
                packages=task.packages,
                success=False,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                error_message=str(e),
                retry_count=task.retry_count,
                metadata=task.metadata.copy(),
            )

            return result

        finally:
            # 清理
            with self.lock:
                if task.task_id in self.running_tasks:
                    del self.running_tasks[task.task_id]

                if result:
                    self.completed_tasks[task.task_id] = result

            # 注销资源使用
            if self.resource_monitor:
                self.resource_monitor.unregister_installation()

            if result:
                logger.info(
                    f"Completed task {task.task_id} in {result.duration:.2f}s"
                )

    def _get_package_manager(
        self, environment: IsolatedEnvironment
    ) -> AdvancedPackageManager:
        """获取环境的包管理器"""
        env_id = environment.env_id

        if env_id not in self.package_managers:
            # 创建新的包管理器
            pm_config = self.config.get("package_manager", {})
            package_manager = AdvancedPackageManager(environment.path, pm_config)
            self.package_managers[env_id] = package_manager

        return self.package_managers[env_id]

    def _update_statistics(self, result: InstallationResult):
        """更新统计信息"""
        with self.lock:
            if result.success:
                self.stats["completed_tasks"] += 1
                self.stats["successful_packages"] += len(result.successful_packages)
            else:
                self.stats["failed_tasks"] += 1
                self.stats["failed_packages"] += len(result.failed_packages)

            self.stats["total_time"] += result.duration

    def batch_install(
        self,
        environments_packages: Dict[IsolatedEnvironment, List[str]],
        priority: Priority = Priority.NORMAL,
        wait_for_completion: bool = False,
        timeout: Optional[float] = None,
    ) -> List[str]:
        """
        批量安装包到多个环境

        Args:
            environments_packages: 环境到包列表的映射
            priority: 任务优先级
            wait_for_completion: 是否等待完成
            timeout: 等待超时时间

        Returns:
            任务ID列表
        """
        task_ids = []

        for environment, packages in environments_packages.items():
            task_id = self.submit_task(
                environment=environment,
                packages=packages,
                priority=priority,
            )
            task_ids.append(task_id)

        if wait_for_completion:
            self.wait_for_tasks(task_ids, timeout)

        return task_ids

    def wait_for_tasks(
        self,
        task_ids: List[str],
        timeout: Optional[float] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, InstallationResult]:
        """
        等待多个任务完成

        Args:
            task_ids: 任务ID列表
            timeout: 超时时间
            progress_callback: 进度回调函数

        Returns:
            任务结果字典
        """
        start_time = time.time()
        results = {}
        remaining_tasks = set(task_ids)

        while remaining_tasks and (
            timeout is None or time.time() - start_time < timeout
        ):
            completed = set()

            for task_id in remaining_tasks:
                status = self.get_task_status(task_id)

                if status and status.get("status") in ["completed", "failed"]:
                    completed.add(task_id)

                    # 获取结果
                    if "result" in status:
                        results[task_id] = InstallationResult.from_dict(status["result"])

                    # 调用进度回调
                    if progress_callback:
                        progress_callback(task_id, status)

            # 移除已完成的任务
            remaining_tasks -= completed

            if remaining_tasks:
                time.sleep(0.1)

        # 超时处理
        if remaining_tasks:
            logger.warning(f"Timeout waiting for tasks: {remaining_tasks}")
            for task_id in remaining_tasks:
                self.cancel_task(task_id)

        return results

    def get_environment_info(self, environment: IsolatedEnvironment) -> Dict[str, Any]:
        """获取环境相关信息"""
        env_id = environment.env_id

        info = {
            "environment_id": env_id,
            "path": str(environment.path),
            "status": environment.status.value,
            "has_package_manager": env_id in self.package_managers,
        }

        # 获取安装的包信息
        if env_id in self.package_managers:
            pm = self.package_managers[env_id]
            try:
                packages = pm.list_packages()
                info["installed_packages"] = {
                    name: pkg.version for name, pkg in packages.items()
                }
                info["package_count"] = len(packages)
            except Exception as e:
                logger.error(
                    f"Error getting package list for environment {env_id}: {e}"
                )
                info["package_error"] = str(e)

        # 获取相关任务
        related_tasks = []
        with self.lock:
            for task_id, result in self.completed_tasks.items():
                if result.environment_id == env_id:
                    related_tasks.append(
                        {
                            "task_id": task_id,
                            "packages": result.packages,
                            "success": result.success,
                            "duration": result.duration,
                        }
                    )

        info["recent_tasks"] = sorted(
            related_tasks, key=lambda x: x.get("duration", 0), reverse=True
        )[:5]

        return info

    def cleanup_completed_tasks(self, max_age_days: int = 7) -> int:
        """清理已完成的任务历史"""
        cutoff_time = datetime.now() - timedelta(days=max_age_days)
        removed_count = 0

        with self.lock:
            tasks_to_remove = []

            for task_id, result in self.completed_tasks.items():
                # Tasks without end_time are considered very old and should be cleaned up
                if result.end_time is None or result.end_time < cutoff_time:
                    tasks_to_remove.append(task_id)

            for task_id in tasks_to_remove:
                del self.completed_tasks[task_id]
                removed_count += 1

        logger.info(
            f"Cleaned up {removed_count} completed tasks older than {max_age_days} days"
        )
        return removed_count

    def export_statistics(self, file_path: Path) -> bool:
        """导出统计信息到文件"""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "statistics": self.get_statistics(),
                "queue_info": self.get_queue_info(),
                "completed_tasks_count": len(self.completed_tasks),
                "config": self.config,
            }

            # 添加最近任务信息
            recent_tasks = []
            with self.lock:
                for task_id, result in list(self.completed_tasks.items())[-10:]:
                    recent_tasks.append(result.to_dict())
            data["recent_tasks"] = recent_tasks

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Statistics exported to {file_path}")
            return True

        except Exception as e:
            logger.error(f"Error exporting statistics: {e}")
            return False

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()
