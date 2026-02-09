# -*- coding: utf-8 -*-
# ptest 测试套件模块 / ptest Test Suite Module
#
# 版权所有 (c) 2026 cp
# Copyright (c) 2026 ptest Development Team
#
# 许可证: MIT
# License: MIT

"""
ptest 测试套件模块 / ptest Test Suite Module

提供测试套件管理功能,支持用例组织、依赖关系和批量执行。
Provides test suite management supporting case organization,
dependency relationships and batch execution.

主要功能 / Main Features:
    - 测试套件定义和管理
    - 用例引用和依赖关系
    - 串行/并行执行模式
    - 套件验证和排序

示例 / Example:
    >>> from ptest.suites import TestSuite, CaseRef, ExecutionMode
    >>> suite = TestSuite(
    ...     name="regression",
    ...     cases=[CaseRef(case_id="test_1", order=1)]
    ... )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..core import get_logger

logger = get_logger("suites")


class ExecutionMode(str, Enum):
    """套件执行模式 / Suite execution mode"""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


@dataclass
class CaseRef:
    """测试用例引用 / Test case reference"""

    case_id: str
    order: int
    depends_on: list[str] = field(default_factory=list)
    skip: bool = False
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 / Convert to dictionary"""
        return {
            "case_id": self.case_id,
            "order": self.order,
            "depends_on": self.depends_on,
            "skip": self.skip,
            "skip_reason": self.skip_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaseRef:
        """从字典创建 / Create from dictionary"""
        return cls(
            case_id=data.get("case_id", ""),
            order=data.get("order", 0),
            depends_on=data.get("depends_on", []),
            skip=data.get("skip", False),
            skip_reason=data.get("skip_reason"),
        )


@dataclass
class TestSuite:
    """测试套件 / Test suite"""

    name: str
    description: str | None = None
    setup: list[str] = field(default_factory=list)
    cases: list[CaseRef] = field(default_factory=list)
    teardown: list[str] = field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    max_workers: int = 4

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 / Convert to dictionary"""
        return {
            "name": self.name,
            "description": self.description,
            "setup": self.setup,
            "cases": [case.to_dict() for case in self.cases],
            "teardown": self.teardown,
            "execution_mode": self.execution_mode.value,
            "max_workers": self.max_workers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TestSuite:
        """从字典创建 / Create from dictionary"""
        cases_data = data.get("cases", [])
        return cls(
            name=data.get("name", ""),
            description=data.get("description"),
            setup=data.get("setup", []),
            cases=[CaseRef.from_dict(case) for case in cases_data],
            teardown=data.get("teardown", []),
            execution_mode=ExecutionMode(data.get("execution_mode", "sequential")),
            max_workers=data.get("max_workers", 4),
        )

    def validate(self) -> tuple[bool, list[str]]:
        """验证套件配置 / Validate suite configuration"""
        errors = []

        if not self.name:
            errors.append("套件名称不能为空 / Suite name cannot be empty")

        if not self.cases:
            errors.append("套件至少需要一个用例 / Suite must have at least one case")

        orders = [case.order for case in self.cases]
        if len(orders) != len(set(orders)):
            errors.append(f"用例执行顺序重复: {orders} / Duplicate execution orders")

        case_ids = set(case.case_id for case in self.cases)
        for case in self.cases:
            for dep in case.depends_on:
                if dep not in case_ids:
                    errors.append(
                        f"用例 '{case.case_id}' 依赖不存在的用例 '{dep}' / "
                        f"Case '{case.case_id}' depends on non-existent case"
                    )

        return len(errors) == 0, errors

    def get_sorted_cases(self) -> list[CaseRef]:
        """获取按执行顺序排序的用例列表 / Get sorted cases by order"""
        return sorted(self.cases, key=lambda x: x.order)


class SuiteManager:
    """测试套件管理器 / Test suite manager"""

    def __init__(self, storage_dir: str | Path | None = None):
        """初始化套件管理器 / Initialize suite manager"""
        self.storage_dir = (
            Path(storage_dir) if storage_dir else Path.cwd() / ".ptest" / "suites"
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._suites: dict[str, TestSuite] = {}

    def create_suite(self, suite_data: dict[str, Any]) -> TestSuite:
        """创建测试套件 / Create test suite"""
        if isinstance(suite_data, (str, Path)):
            suite_path = Path(suite_data)
            if not suite_path.exists():
                raise FileNotFoundError(
                    f"套件文件不存在: {suite_path} / Suite file not found"
                )

            with open(suite_path, "r", encoding="utf-8") as f:
                suite_dict = json.load(f)
        else:
            suite_dict = suite_data

        suite = TestSuite.from_dict(suite_dict)
        self._save_suite(suite)
        self._suites[suite.name] = suite

        logger.info(f"测试套件创建成功: {suite.name}")
        return suite

    def _save_suite(self, suite: TestSuite) -> None:
        """保存套件到文件 / Save suite to file"""
        suite_file = self.storage_dir / f"{suite.name}.json"
        with open(suite_file, "w", encoding="utf-8") as f:
            json.dump(suite.to_dict(), f, ensure_ascii=False, indent=2)
        logger.debug(f"套件保存到: {suite_file}")

    def load_suite(self, name: str) -> TestSuite | None:
        """加载测试套件 / Load test suite"""
        if name in self._suites:
            return self._suites[name]

        suite_file = self.storage_dir / f"{name}.json"
        if not suite_file.exists():
            return None

        try:
            with open(suite_file, "r", encoding="utf-8") as f:
                suite_dict = json.load(f)
            suite = TestSuite.from_dict(suite_dict)
            self._suites[name] = suite
            return suite
        except Exception as e:
            logger.error(f"加载套件失败: {e}")
            return None

    def list_suites(self) -> list[str]:
        """列出所有测试套件 / List all test suites"""
        return sorted(self._suites.keys())

    def delete_suite(self, name: str) -> bool:
        """删除测试套件 / Delete test suite"""
        if name not in self._suites:
            logger.warning(f"套件不存在: {name}")
            return False

        suite_file = self.storage_dir / f"{name}.json"
        if suite_file.exists():
            suite_file.unlink()
            del self._suites[name]
            logger.info(f"测试套件删除成功: {name}")
            return True

        logger.warning(f"套件文件不存在: {suite_file}")
        return False

    def get_suite_cases(self, suite_name: str) -> list[CaseRef]:
        """获取套件中的测试用例（已排序）/ Get sorted cases from suite"""
        suite = self.load_suite(suite_name)
        if not suite:
            return []

        return suite.get_sorted_cases()

    def execute_suite(
        self,
        suite_name: str,
        case_manager=None,
        parallel: bool = False,
        max_workers: int = 4,
    ) -> dict[str, Any]:
        """
        执行测试套件 / Execute test suite

        Args:
            suite_name: 套件名称
            case_manager: 用例管理器（用于执行用例）
            parallel: 是否并行执行
            max_workers: 最大并行工作数

        Returns:
            执行结果统计
        """
        from ..execution import (
            ParallelExecutor,
            SequentialExecutor,
            ExecutionTask,
        )

        suite = self.load_suite(suite_name)
        if not suite:
            logger.error(f"套件不存在: {suite_name}")
            return {"success": False, "error": "Suite not found"}

        # 验证套件
        is_valid, errors = suite.validate()
        if not is_valid:
            logger.error(f"套件验证失败: {errors}")
            return {"success": False, "errors": errors}

        logger.info(f"开始执行套件: {suite_name} (并行={parallel})")

        # 构建依赖图
        dependencies = {}
        for case in suite.cases:
            if case.depends_on:
                dependencies[case.case_id] = case.depends_on

        # 创建执行任务
        tasks = []
        for case in suite.cases:
            if case.skip:
                logger.info(f"跳过用例: {case.case_id}")
                continue

            def execute_case(case_id=case.case_id):
                if case_manager:
                    case_data = case_manager.get_case(case_id)
                    if case_data:
                        return case_manager.run_case(case_data)
                return {"case_id": case_id, "status": "executed"}

            task = ExecutionTask(
                task_id=case.case_id,
                func=execute_case,
            )
            tasks.append(task)

        if not tasks:
            logger.warning("没有可执行的用例")
            return {"success": True, "total": 0, "passed": 0, "failed": 0}

        # 选择执行器
        if parallel or suite.execution_mode.value == "parallel":
            executor = ParallelExecutor(max_workers=max_workers)
        else:
            executor = SequentialExecutor()

        try:
            # 执行
            results = executor.execute(tasks, dependencies)

            # 统计结果
            total = len(results)
            passed = sum(1 for r in results if r.success)
            failed = total - passed

            logger.info(
                f"套件执行完成: {suite_name} - 总计={total}, 通过={passed}, 失败={failed}"
            )

            return {
                "success": failed == 0,
                "total": total,
                "passed": passed,
                "failed": failed,
                "results": [r.to_dict() for r in results],
            }

        except Exception as e:
            logger.error(f"套件执行失败: {e}")
            return {"success": False, "error": str(e)}

        finally:
            if hasattr(executor, "shutdown"):
                executor.shutdown()
