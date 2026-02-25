# -*- coding: utf-8 -*-
# ptest 并行执行模块 / ptest Parallel Execution Module
#
# 版权所有 (c) 2026 ptest开发团队
# Copyright (c) 2026 ptest Development Team
#
# 许可证: MIT
# License: MIT

"""
ptest 并行执行模块 / ptest Parallel Execution Module

提供测试用例的并行执行能力，支持依赖管理和结果聚合。
Provides parallel test case execution with dependency management and result aggregation.

主要功能 / Main Features:
    - 基于线程池的并行执行
    - 依赖拓扑排序
    - 执行状态跟踪
    - 结果聚合和报告
    - 超时控制

示例 / Example:
    >>> from ptest.execution import ParallelExecutor
    >>> executor = ParallelExecutor(max_workers=4)
    >>> results = executor.execute(tasks, dependencies)
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ..core import get_logger

logger = get_logger("execution")


class TaskStatus(str, Enum):
    """任务执行状态 / Task execution status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class ExecutionTask:
    """执行任务 / Execution task"""

    task_id: str
    func: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    timeout: float = 300.0
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    start_time: float | None = None
    end_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 / Convert to dictionary"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "timeout": self.timeout,
            "result": self.result,
            "error": self.error,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


@dataclass
class ExecutionResult:
    """执行结果 / Execution result"""

    task_id: str
    success: bool
    result: Any = None
    error: str | None = None
    duration: float = 0.0
    status: TaskStatus = TaskStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 / Convert to dictionary"""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration": self.duration,
            "status": self.status.value,
        }


class DependencyResolver:
    """依赖解析器 / Dependency resolver"""

    def __init__(self, dependencies: dict[str, list[str]]):
        """
        初始化依赖解析器

        Args:
            dependencies: 依赖关系图 {task_id: [dependency_ids]}
        """
        self.dependencies = dependencies
        self._completed: set[str] = set()
        self._lock = threading.Lock()

    def get_ready_tasks(self, task_ids: list[str]) -> list[str]:
        """
        获取可以执行的任务（依赖已完成）

        Args:
            task_ids: 候选任务ID列表

        Returns:
            依赖已满足的任务ID列表
        """
        ready = []
        with self._lock:
            for task_id in task_ids:
                deps = self.dependencies.get(task_id, [])
                if all(dep in self._completed for dep in deps):
                    ready.append(task_id)
        return ready

    def mark_completed(self, task_id: str) -> None:
        """标记任务已完成"""
        with self._lock:
            self._completed.add(task_id)

    def get_execution_order(self, task_ids: list[str]) -> list[list[str]]:
        """
        获取执行顺序（拓扑排序分层）

        返回分层的执行顺序，每层内的任务可以并行执行。
        Returns layered execution order, tasks in same layer can run in parallel.

        Args:
            task_ids: 所有任务ID列表

        Returns:
            分层执行顺序 [[layer1_tasks], [layer2_tasks], ...]
        """
        # 构建依赖图
        in_degree: dict[str, int] = {task_id: 0 for task_id in task_ids}
        graph: dict[str, list[str]] = {task_id: [] for task_id in task_ids}

        for task_id, deps in self.dependencies.items():
            if task_id not in in_degree:
                continue
            for dep in deps:
                if dep in in_degree:
                    graph[dep].append(task_id)
                    in_degree[task_id] += 1

        # 拓扑排序分层
        layers = []
        remaining = set(task_ids)

        while remaining:
            # 找到入度为0的任务
            layer = [task_id for task_id in remaining if in_degree[task_id] == 0]

            if not layer:
                # 存在循环依赖
                raise ValueError(f"Circular dependency detected: {remaining}")

            layers.append(layer)
            remaining -= set(layer)

            # 更新入度
            for task_id in layer:
                for dependent in graph[task_id]:
                    in_degree[dependent] -= 1

        return layers


class ParallelExecutor:
    """并行执行器 / Parallel executor"""

    def __init__(self, max_workers: int = 4):
        """
        初始化并行执行器

        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._results: dict[str, ExecutionResult] = {}
        self._results_lock = threading.Lock()

    def execute(
        self,
        tasks: list[ExecutionTask],
        dependencies: dict[str, list[str]] | None = None,
    ) -> list[ExecutionResult]:
        """
        并行执行任务

        Args:
            tasks: 任务列表
            dependencies: 依赖关系图

        Returns:
            执行结果列表
        """
        if not tasks:
            return []

        dependencies = dependencies or {}
        resolver = DependencyResolver(dependencies)

        # 创建任务映射
        task_map = {task.task_id: task for task in tasks}
        task_ids = list(task_map.keys())

        # 获取分层执行顺序
        try:
            layers = resolver.get_execution_order(task_ids)
        except ValueError as e:
            logger.error(f"依赖解析失败: {e}")
            raise

        logger.info(f"执行计划: {len(layers)} 层, {len(tasks)} 个任务")

        # 逐层执行
        for layer_idx, layer in enumerate(layers):
            logger.info(f"执行第 {layer_idx + 1} 层: {len(layer)} 个任务")
            self._execute_layer(layer, task_map, resolver)

        # 收集结果
        return [self._results[task_id] for task_id in task_ids]

    def _execute_layer(
        self,
        layer: list[str],
        task_map: dict[str, ExecutionTask],
        resolver: DependencyResolver,
    ) -> None:
        """执行单层任务"""
        futures = {}

        for task_id in layer:
            task = task_map[task_id]
            task.status = TaskStatus.RUNNING
            task.start_time = time.time()

            # 提交任务
            future = self._executor.submit(self._run_task, task)
            futures[future] = task_id

        # 收集结果
        for future in as_completed(futures):
            task_id = futures[future]
            try:
                result = future.result()
                self._handle_success(task_id, result, task_map)
            except Exception as e:
                self._handle_error(task_id, str(e), task_map)

            resolver.mark_completed(task_id)

    def _run_task(self, task: ExecutionTask) -> Any:
        """运行单个任务"""
        try:
            result = task.func(*task.args, **task.kwargs)
            return result
        except Exception as e:
            logger.error(f"任务 {task.task_id} 执行失败: {e}")
            raise

    def _handle_success(
        self, task_id: str, result: Any, task_map: dict[str, ExecutionTask]
    ) -> None:
        """处理任务成功"""
        task = task_map[task_id]
        task.end_time = time.time()
        task.status = TaskStatus.COMPLETED
        task.result = result

        execution_result = ExecutionResult(
            task_id=task_id,
            success=True,
            result=result,
            duration=task.end_time - (task.start_time or task.end_time),
        )

        with self._results_lock:
            self._results[task_id] = execution_result

        logger.info(f"任务完成: {task_id}")

    def _handle_error(
        self, task_id: str, error: str, task_map: dict[str, ExecutionTask]
    ) -> None:
        """处理任务失败"""
        task = task_map[task_id]
        task.end_time = time.time()
        task.status = TaskStatus.FAILED
        task.error = error

        execution_result = ExecutionResult(
            task_id=task_id,
            success=False,
            error=error,
            duration=task.end_time - (task.start_time or task.end_time),
            status=TaskStatus.FAILED,
        )

        with self._results_lock:
            self._results[task_id] = execution_result

        logger.error(f"任务失败: {task_id} - {error}")

    def shutdown(self) -> None:
        """关闭执行器"""
        self._executor.shutdown(wait=True)
        logger.info("并行执行器已关闭")


class SequentialExecutor:
    """串行执行器 / Sequential executor"""

    def __init__(self, stop_on_failure: bool = False, timeout: float = 0):
        """
        初始化串行执行器

        Args:
            stop_on_failure: 失败时是否停止执行
            timeout: 超时时间(秒), 0 表示无超时
        """
        self.stop_on_failure = stop_on_failure
        self.timeout = timeout
        self._results: dict[str, ExecutionResult] = {}

    def shutdown(self) -> None:
        """关闭执行器（串行执行器无需清理）"""
        logger.info("串行执行器已关闭")

    def execute(
        self,
        tasks: list[ExecutionTask],
        dependencies: dict[str, list[str]] | None = None,
    ) -> list[ExecutionResult]:
        """
        串行执行任务

        Args:
            tasks: 任务列表
            dependencies: 依赖关系图

        Returns:
            执行结果列表
        """
        if not tasks:
            return []

        dependencies = dependencies or {}
        resolver = DependencyResolver(dependencies)

        task_map = {task.task_id: task for task in tasks}
        task_ids = list(task_map.keys())

        # 获取执行顺序
        try:
            layers = resolver.get_execution_order(task_ids)
        except ValueError as e:
            logger.error(f"依赖解析失败: {e}")
            raise

        failed_count = 0

        # 按顺序执行任务
        for layer in layers:
            for task_id in layer:
                # 检查 stop_on_failure
                if self.stop_on_failure and failed_count > 0:
                    # 标记剩余任务为跳过
                    logger.info(f"因前面的失败，跳过任务: {task_id}")
                    task = task_map[task_id]
                    self._results[task_id] = ExecutionResult(
                        task_id=task_id,
                        success=False,
                        error="Skipped due to previous failure",
                        status=TaskStatus.SKIPPED,
                    )
                    resolver.mark_completed(task_id)
                    continue

                task = task_map[task_id]
                # 使用全局 timeout 或任务自身的 timeout
                task_timeout = self.timeout if self.timeout > 0 else task.timeout
                self._execute_task(task, task_timeout)

                if not self._results.get(
                    task_id, ExecutionResult(task_id="", success=False)
                ).success:
                    failed_count += 1

                resolver.mark_completed(task_id)

        return [self._results[task_id] for task_id in task_ids]

    def _execute_task(self, task: ExecutionTask, timeout: float = 0) -> None:
        """执行单个任务"""
        import signal
        import sys

        task.status = TaskStatus.RUNNING
        task.start_time = time.time()

        # 信号处理仅在 Unix 主线程上可用
        use_signal_timeout = timeout > 0 and sys.platform != "win32"

        if use_signal_timeout:
            # 定义超时处理函数
            def timeout_handler(signum, frame):
                raise TimeoutError(
                    f"Task {task.task_id} timed out after {timeout} seconds"
                )

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout))

        try:
            result = task.func(*task.args, **task.kwargs)
            task.end_time = time.time()
            task.status = TaskStatus.COMPLETED
            task.result = result

            self._results[task.task_id] = ExecutionResult(
                task_id=task.task_id,
                success=True,
                result=result,
                duration=task.end_time - task.start_time,
            )

            logger.info(f"任务完成: {task.task_id}")

        except TimeoutError as e:
            task.end_time = time.time()
            task.status = TaskStatus.TIMEOUT
            task.error = str(e)

            self._results[task.task_id] = ExecutionResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
                duration=task.end_time - task.start_time,
                status=TaskStatus.TIMEOUT,
            )

            logger.error(f"任务超时: {task.task_id} - {e}")

        except Exception as e:
            task.end_time = time.time()
            task.status = TaskStatus.FAILED
            task.error = str(e)

            self._results[task.task_id] = ExecutionResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
                duration=task.end_time - task.start_time,
                status=TaskStatus.FAILED,
            )

            logger.error(f"任务失败: {task.task_id} - {e}")

        finally:
            # 取消超时信号
            if use_signal_timeout:
                signal.alarm(0)


def create_executor(
    parallel: bool = True, max_workers: int = 4
) -> ParallelExecutor | SequentialExecutor:
    """
    创建执行器工厂函数

    Args:
        parallel: 是否并行执行
        max_workers: 最大工作线程数

    Returns:
        执行器实例
    """
    if parallel:
        return ParallelExecutor(max_workers=max_workers)
    else:
        return SequentialExecutor()
