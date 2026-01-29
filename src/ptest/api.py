# ptest/api.py - 简化版本

import os
import sys
import json
import uuid
import time
from typing import Dict, List, Any, Optional, Union, TYPE_CHECKING
from pathlib import Path
from datetime import datetime

# 导入框架核心组件
from .environment import EnvironmentManager
from .objects.manager import ObjectManager
from .cases.manager import CaseManager
from .reports.generator import ReportGenerator

# 配置和常量
from .config import DEFAULT_CONFIG

# 使用框架的日志管理器
from .core import get_logger, execute_command

logger = get_logger("api")


class PTestAPI:
    """ptest Python API - 提供完整的编程接口"""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        work_path: Optional[str] = None,
    ):
        """初始化API实例"""

        # 设置配置
        self.config = config if config else DEFAULT_CONFIG

        # 设置工作路径
        if work_path:
            self.work_path = Path(work_path)
        else:
            self.work_path = Path.cwd()

        # 创建核心管理器
        self.env_manager = EnvironmentManager(self.config, self.work_path)
        self.case_manager = CaseManager(self.config, self.work_path)
        self.object_manager = ObjectManager(self.env_manager)
        self.report_generator = ReportGenerator(self.env_manager, self.case_manager)

        # 状态跟踪
        self.is_initialized = True

        logger.info("PTest API initialized")

    def create_environment(
        self,
        path: Optional[str] = None,
        isolation_level: Optional[str] = None,
        isolation_config: Optional[Dict[str, Any]] = None,
        env_config: Optional[Dict[str, Any]] = None,
    ) -> "EnvironmentManager":
        """创建测试环境"""
        try:
            # 使用默认工作路径或用户指定路径
            env_path = Path(path or self.work_path)

            # 自动选择隔离级别
            if isolation_level is None:
                isolation_level = self.config.get("default_isolation_level")

            env_id = f"env_{int(time.time())}"

            # 创建环境
            env = self.env_manager.create_environment(
                path=env_path,
                env_id=env_id,
                isolation_level=isolation_level,
                isolation_config=isolation_config,
                env_config=env_config,
            )

            logger.info(f"Created environment {env_id} at {env_path}")
            return env

        except Exception as e:
            logger.error(f"Failed to create environment: {e}")
            raise

    def get_environment(self, env_id: str) -> Optional["EnvironmentManager"]:
        """获取指定环境"""
        return self.env_manager.get_environment(env_id)

    def delete_environment(self, env_id: str) -> bool:
        """删除指定环境"""
        return self.env_manager.delete_environment(env_id)

    def list_environments(self) -> Dict[str, Dict[str, Any]]:
        """列出所有环境"""
        return self.env_manager.list_environments()

    def get_environment_status(self, env_id: str) -> Dict[str, Any]:
        """获取环境状态"""
        return self.env_manager.get_environment_status(env_id)

    def run_test_case(
        self,
        case_id: str,
        timeout: Optional[float] = None,
        env_ids: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """运行测试用例"""
        # 获取配置
        case_config = config if config else self.config
        env_ids = env_ids or [self.get_latest_environment_id()]

        results = {}
        for env_id in env_ids:
            if env_id in self.get_environment(env_id):
                env = self.get_environment(env_id)
                results[env_id] = self.case_manager.run_case(case_id, timeout, config)

        return results

    def run_all_cases(
        self,
        timeout: Optional[float] = None,
        filter_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """运行所有测试用例"""
        # 获取所有活跃环境
        env_ids = self.env_manager.get_active_environments()

        if not env_ids:
            logger.warning("No active environments found")
            return {}

        results = {}
        for env_id in env_ids:
            env = self.get_environment(env_id)
            results[env_id] = self.case_manager.run_all_cases(timeout, filter_config)

        return results

    def create_test_case(
        self,
        test_type: str,
        name: str,
        description: str,
        content: Union[str, Dict[str, Any]] = None,
        tags: List[str] = None,
        expected_result: str = None,
        timeout: Optional[float] = None,
        env_id: Optional[str] = None,
    ) -> str:
        """创建测试用例"""
        try:
            # 生成测试用例ID
            case_id = f"{test_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"

            # 创建测试用例
            case_data = {
                "type": test_type,
                "name": name,
                "description": description,
                "content": content or {},
                "tags": tags or [],
                "expected_result": expected_result,
                "created_at": datetime.now().isoformat(),
                "env_id": env_id,
                "timeout": timeout,
            }

            # 添加到管理器
            success = self.case_manager.create_case(case_data)

            if success:
                return case_id
            else:
                logger.error(f"Failed to create test case: {name}")
                return ""

        except Exception as e:
            logger.error(f"Failed to create test case: {e}")
            logger.error(f"Failed to create test case: {e}")
            return ""

    def get_test_case(self, case_id: str) -> Dict[str, Any]:
        """获取测试用例"""
        return self.case_manager.get_case(case_id)

    def get_test_cases(
        self,
        env_id: Optional[str] = None,
        test_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """获取测试用例列表"""
        return self.case_manager.get_cases(env_id, test_type, tags)

    def delete_test_case(self, case_id: str) -> bool:
        """删除测试用例"""
        return self.case_manager.delete_case(case_id)

    def get_test_result(self, case_id: str) -> Dict[str, Any]:
        """获取测试结果"""
        return self.case_manager.get_test_result(case_id)

    def generate_report(
        self,
        format_type: str = "html",
        output_path: Optional[str] = None,
        env_ids: Optional[List[str]] = None,
        case_ids: Optional[List[str]] = None,
        case_status: Optional[List[str]] = None,
    ) -> str:
        """生成测试报告"""
        try:
            report_path = self.report_generator.generate_report(
                format_type, output_path
            )
            logger.info(f"Generated {format_type} report: {report_path}")
            return report_path
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            raise

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return {
            "version": "1.0.1",
            "work_path": str(self.work_path),
            "isolation_engines": list(self.env_manager.isolation_engines.keys()),
            "active_environments": list(self.env_manager.get_active_environments()),
            "total_environments": len(self.env_manager.get_all_environments()),
            "api_version": "1.0.1",
            "objects_supported": list(self.object_manager.object_types.keys()),
            "cases_supported": list(self.case_manager.test_types),
            "reports_supported": ["html", "json", "xml"],
            "created_at": datetime.now().isoformat(),
            "framework_version": "PTEST-1.0.1",
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        return self.env_manager.get_performance_metrics()
