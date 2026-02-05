# ptest/api.py - Python API 接口

import os
import sys
import json
import uuid
import time
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from datetime import datetime

# 导入框架核心组件
from .environment import EnvironmentManager
from .objects.manager import ObjectManager
from .cases.manager import CaseManager
from .reports.generator import ReportGenerator
from .isolation.manager import IsolationManager

# 配置和常量
from .config import DEFAULT_CONFIG

# 使用框架的日志管理器
from .core import get_logger

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
        self.env_manager = EnvironmentManager()
        self.isolation_manager = IsolationManager(self.config)

        # 状态跟踪
        self.is_initialized = True
        self._active_env_path: Optional[Path] = None

        logger.info("PTest API initialized")

    def init_environment(self, path: Optional[str] = None) -> Path:
        """初始化测试环境

        Args:
            path: 环境路径，默认为当前工作路径

        Returns:
            Path: 初始化后的环境路径
        """
        env_path = Path(path) if path else self.work_path
        result = self.env_manager.init_environment(env_path)
        self._active_env_path = env_path
        return result

    def get_environment_status(self) -> Union[Dict[str, Any], str]:
        """获取当前环境状态"""
        return self.env_manager.get_env_status()

    def create_test_case(
        self,
        test_type: str,
        name: str,
        description: str = "",
        content: Union[str, Dict[str, Any]] = None,
        tags: List[str] = None,
        expected_result: str = None,
        timeout: Optional[float] = None,
    ) -> str:
        """创建测试用例

        注意：需要先初始化环境
        """
        if not self._active_env_path:
            # 如果没有初始化环境，使用当前工作路径
            self.init_environment()

        # 创建用例管理器（使用当前环境）
        case_manager = CaseManager(self.env_manager)

        # 创建测试用例
        case_id = f"{test_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        case_data = {
            "type": test_type,
            "name": name,
            "description": description,
            "content": content or {},
            "tags": tags or [],
            "expected_result": expected_result,
            "timeout": timeout,
            "created_at": datetime.now().isoformat(),
        }

        case_manager.add_case(case_id, case_data)
        return case_id

    def list_test_cases(self) -> str:
        """列出所有测试用例"""
        if not self._active_env_path:
            return "No environment initialized"

        case_manager = CaseManager(self.env_manager)
        return case_manager.list_cases()

    def run_test_case(self, case_id: str):
        """运行指定测试用例"""
        if not self._active_env_path:
            raise ValueError(
                "Environment not initialized. Call init_environment() first."
            )

        case_manager = CaseManager(self.env_manager)
        return case_manager.run_case(case_id)

    def create_object(self, obj_type: str, name: str, **kwargs) -> str:
        """创建测试对象

        注意：需要先初始化环境
        """
        if not self._active_env_path:
            self.init_environment()

        obj_manager = ObjectManager(self.env_manager)
        result = obj_manager.create_object(obj_type, name, **kwargs)
        return result

    def list_objects(self) -> str:
        """列出所有对象"""
        if not self._active_env_path:
            return "No environment initialized"

        obj_manager = ObjectManager(self.env_manager)
        return obj_manager.list_objects()

    def generate_report(
        self,
        format_type: str = "html",
        output_path: Optional[str] = None,
    ) -> str:
        """生成测试报告

        注意：需要先初始化环境
        """
        if not self._active_env_path:
            self.init_environment()

        report_gen = ReportGenerator(self.env_manager)
        return report_gen.generate_report(format_type, output_path)

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        isolation_engines = list(self.isolation_manager.engines.keys())

        return {
            "version": "1.0.1",
            "api_version": "1.0.1",
            "work_path": str(self.work_path),
            "environment_initialized": self._active_env_path is not None,
            "environment_path": str(self._active_env_path)
            if self._active_env_path
            else None,
            "isolation_engines": isolation_engines,
            "framework_version": "PTEST-1.0.1",
            "created_at": datetime.now().isoformat(),
        }

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        # 清理资源
        pass


# 便捷函数
def create_ptest_api(
    config: Optional[Dict[str, Any]] = None, work_path: Optional[str] = None
) -> PTestAPI:
    """创建PTestAPI实例的便捷函数"""
    return PTestAPI(config=config, work_path=work_path)
