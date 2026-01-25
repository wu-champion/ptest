# ptest/api.py
"""
ptest 框架 Python API 接口
提供完整的编程接口，支持环境管理、对象管理、测试用例管理和报告生成
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import json

# 导入框架核心组件
from .environment import EnvironmentManager
from .objects.manager import ObjectManager
from .cases.manager import CaseManager
from .reports.generator import ReportGenerator

# 导入隔离模块
try:
    from .isolation import IsolationManager, IsolationLevel, IsolatedEnvironment
except ImportError:
    # 如果隔离模块还未完全实现，使用占位符
    IsolationManager = None
    IsolationLevel = None
    IsolatedEnvironment = None

# 导入核心工具和配置
from .core import (
    PtestConfig,
    ObjectStatus,
    TestStatus,
    ReportFormat,
    get_logger,
    execute_command,
    PathManager,
    HookManager,
    FRAMEWORK_INFO,
    get_default_config,
)


class TestEnvironment:
    """测试环境类 - 管理单个测试环境"""

    def __init__(self, path: str, isolation: str = "basic", framework=None):
        """
        初始化测试环境

        Args:
            path: 测试环境路径
            isolation: 隔离级别 ("basic", "virtualenv", "docker")
            framework: 关联的框架实例
        """
        self.path = Path(path).resolve()
        self.isolation = isolation
        self.framework = framework
        self.env_manager = EnvironmentManager()
        self.obj_manager = ObjectManager(self.env_manager)
        self.case_manager = CaseManager(self.env_manager)
        self.report_generator = ReportGenerator(self.env_manager, self.case_manager)

        # 新增：隔离环境支持
        self.isolated_env = None
        self._setup_isolation()

        # 初始化环境
        self.env_manager.init_environment(str(self.path))

    def _setup_isolation(self):
        """设置隔离环境"""
        if IsolationManager is None or self.framework is None:
            return

        try:
            # 从框架获取隔离管理器
            if hasattr(self.framework, "isolation_manager"):
                isolation_manager = self.framework.isolation_manager
                # 创建隔离环境
                self.isolated_env = isolation_manager.create_environment(
                    path=self.path, isolation_level=self.isolation
                )
                # 激活隔离环境
                self.isolated_env.activate()
                get_logger(__name__).info(
                    f"Activated isolation environment: {self.isolated_env.env_id}"
                )
        except Exception as e:
            get_logger(__name__).warning(f"Failed to setup isolation: {e}")

    def execute_in_isolation(self, cmd: List[str], **kwargs):
        """在隔离环境中执行命令"""
        if self.isolated_env:
            return self.isolated_env.execute_command(cmd, **kwargs)
        else:
            # 回退到原始方法
            return execute_command(cmd, cwd=self.path, **kwargs)

    def install_package(self, package: str, version: Optional[str] = None) -> bool:
        """安装包到隔离环境"""
        if self.isolated_env:
            return self.isolated_env.install_package(package, version)
        else:
            get_logger(__name__).warning(
                "Package management requires isolation support"
            )
            return False

    def get_installed_packages(self) -> Dict[str, str]:
        """获取已安装的包"""
        if self.isolated_env:
            return self.isolated_env.get_installed_packages()
        return {}

    def allocate_port(self) -> int:
        """分配端口"""
        if self.isolated_env:
            return self.isolated_env.allocate_port()
        else:
            # 简单的端口分配回退
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                return s.getsockname()[1]

    def cleanup_isolation(self):
        """清理隔离环境"""
        if self.isolated_env and self.framework:
            try:
                self.framework.isolation_manager.cleanup_environment(
                    self.isolated_env.env_id
                )
                self.isolated_env = None
            except Exception as e:
                get_logger(__name__).error(f"Failed to cleanup isolation: {e}")

    def add_object(self, obj_type: str, name: str, **kwargs) -> "ManagedObject":
        """
        添加被测对象到当前环境

        Args:
            obj_type: 对象类型 ("mysql", "postgresql", "web", "service", "database_server", "database_client")
            name: 对象名称
            **kwargs: 对象配置参数

        Returns:
            ManagedObject: 被管理的对象实例
        """
        params = kwargs
        if obj_type in ["mysql", "postgresql"] and "version" in kwargs:
            params = {"version": kwargs["version"]}

        self.obj_manager.install(obj_type, name, params)
        return ManagedObject(name, self.obj_manager)

    def add_case(self, case_id: str, case_data: Dict[str, Any]) -> "TestCase":
        """
        添加测试用例到当前环境

        Args:
            case_id: 测试用例ID
            case_data: 测试用例数据

        Returns:
            TestCase: 测试用例对象
        """
        self.case_manager.add_case(case_id, case_data)
        return TestCase(case_id, self.case_manager)

    def run_case(self, case_id: str) -> "TestResult":
        """
        运行单个测试用例

        Args:
            case_id: 测试用例ID

        Returns:
            TestResult: 测试结果
        """
        result = self.case_manager.run_case(case_id)
        return TestResult(result, case_id, self.case_manager.results[case_id])

    def run_all_cases(self) -> List["TestResult"]:
        """
        运行所有测试用例

        Returns:
            List[TestResult]: 测试结果列表
        """
        self.case_manager.run_all_cases()
        results = []
        for case_id in self.case_manager.cases:
            if case_id in self.case_manager.results:
                result = TestResult(
                    f"Test case '{case_id}' completed",
                    case_id,
                    self.case_manager.results[case_id],
                )
                results.append(result)
        return results

    def generate_report(self, format_type: str = "html") -> str:
        """
        生成测试报告

        Args:
            format_type: 报告格式 ("html", "json")

        Returns:
            str: 报告文件路径
        """
        return self.report_generator.generate_report(format_type)

    def get_status(self) -> Dict[str, Any]:
        """获取环境状态"""
        status = self.env_manager.get_env_status()
        if isinstance(status, str):
            return {"status": "error", "message": status}
        return status


class ManagedObject:
    """被管理对象类 - 提供对象操作接口"""

    def __init__(self, name: str, obj_manager: ObjectManager):
        """
        初始化被管理对象

        Args:
            name: 对象名称
            obj_manager: 对象管理器实例
        """
        self.name = name
        self.obj_manager = obj_manager
        self._object = obj_manager.objects.get(name)

    def start(self) -> bool:
        """启动对象"""
        result = self.obj_manager.start(self.name)
        return "✓" in result

    def stop(self) -> bool:
        """停止对象"""
        result = self.obj_manager.stop(self.name)
        return "✓" in result

    def restart(self) -> bool:
        """重启对象"""
        result = self.obj_manager.restart(self.name)
        return "✓" in result

    def uninstall(self) -> bool:
        """卸载对象"""
        result = self.obj_manager.uninstall(self.name)
        return "✓" in result

    def get_status(self) -> Dict[str, Any]:
        """获取对象状态"""
        if self._object:
            return {
                "name": self.name,
                "type": getattr(self._object, "type_name", "unknown"),
                "status": getattr(self._object, "status", "unknown"),
                "installed": getattr(self._object, "installed", False),
            }
        return {"name": self.name, "status": "not_found"}

    def __enter__(self):
        """支持上下文管理器 - 启动对象"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器 - 停止对象"""
        self.stop()


class TestCase:
    """测试用例类 - 提供测试用例操作接口"""

    def __init__(self, case_id: str, case_manager: CaseManager):
        """
        初始化测试用例

        Args:
            case_id: 测试用例ID
            case_manager: 测试用例管理器实例
        """
        self.case_id = case_id
        self.case_manager = case_manager
        self._case_data = case_manager.cases.get(case_id, {})

    def run(self) -> "TestResult":
        """运行测试用例"""
        result = self.case_manager.run_case(self.case_id)
        return TestResult(result, self.case_id, self.case_manager.results[self.case_id])

    def remove(self) -> bool:
        """删除测试用例"""
        result = self.case_manager.remove_case(self.case_id)
        return "✓" in result

    def get_data(self) -> Dict[str, Any]:
        """获取测试用例数据"""
        return self._case_data.get("data", {})

    def get_status(self) -> Dict[str, Any]:
        """获取测试用例状态"""
        return {
            "id": self.case_id,
            "status": self._case_data.get("status", "unknown"),
            "created_at": self._case_data.get("created_at"),
            "last_run": self._case_data.get("last_run"),
        }


class TestResult:
    """测试结果类 - 封装测试执行结果"""

    def __init__(self, raw_result: str, case_id: str, result_obj=None):
        """
        初始化测试结果

        Args:
            raw_result: 原始执行结果
            case_id: 测试用例ID
            result_obj: 测试结果对象
        """
        self.raw_result = raw_result
        self.case_id = case_id
        self.result_obj = result_obj

        # 解析结果状态
        self.success = "✓" in raw_result
        self.status = "passed" if self.success else "failed"

        # 提取详细信息
        if result_obj:
            self.duration = getattr(result_obj, "duration", 0)
            self.error_message = getattr(result_obj, "error_message", "")
            self.start_time = getattr(result_obj, "start_time", None)
            self.end_time = getattr(result_obj, "end_time", None)
        else:
            self.duration = 0
            self.error_message = raw_result if not self.success else ""
            self.start_time = None
            self.end_time = None

    def is_passed(self) -> bool:
        """检查测试是否通过"""
        return self.success

    def is_failed(self) -> bool:
        """检查测试是否失败"""
        return not self.success

    def get_duration(self) -> float:
        """获取测试执行时间"""
        return self.duration

    def get_error(self) -> str:
        """获取错误信息"""
        return self.error_message

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "case_id": self.case_id,
            "status": self.status,
            "success": self.success,
            "duration": self.duration,
            "error_message": self.error_message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "raw_result": self.raw_result,
        }


class TestFramework:
    """
    ptest 测试框架主类
    提供完整的测试框架功能和编程接口
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化测试框架

        Args:
            config: 框架配置参数
        """
        self.config = config or {}
        self.environments: Dict[str, TestEnvironment] = {}
        self.default_environment: Optional[TestEnvironment] = None

        # 框架元信息
        self.version = "1.0.1"
        self.created_at = datetime.now()

        # 新增：隔离管理器
        self.isolation_manager = None
        if IsolationManager is not None:
            from .config import DEFAULT_CONFIG

            framework_config = DEFAULT_CONFIG.copy()
            framework_config.update(self.config)
            self.isolation_manager = IsolationManager(framework_config)
            get_logger(__name__).info("Initialized isolation manager")

    def create_environment(
        self, path: str, isolation: str = "basic"
    ) -> TestEnvironment:
        """
        创建测试环境

        Args:
            path: 测试环境路径
            isolation: 隔离级别 ("basic", "virtualenv", "docker")

        Returns:
            TestEnvironment: 测试环境实例
        """
        env_name = Path(path).name
        environment = TestEnvironment(path, isolation, self)
        self.environments[env_name] = environment

        # 设置为默认环境（如果是第一个）
        if self.default_environment is None:
            self.default_environment = environment

        return environment

    def get_environment(self, name_or_path: str) -> Optional[TestEnvironment]:
        """
        获取测试环境

        Args:
            name_or_path: 环境名称或路径

        Returns:
            TestEnvironment: 测试环境实例，如果不存在则返回None
        """
        # 尝试按名称查找
        if name_or_path in self.environments:
            return self.environments[name_or_path]

        # 尝试按路径查找
        for env in self.environments.values():
            if str(env.path) == str(Path(name_or_path).resolve()):
                return env

        return None

    def create_case(
        self,
        case_id: str,
        case_data: Dict[str, Any],
        environment: Optional[TestEnvironment] = None,
    ) -> TestCase:
        """
        创建测试用例

        Args:
            case_id: 测试用例ID
            case_data: 测试用例数据
            environment: 目标环境，默认使用默认环境

        Returns:
            TestCase: 测试用例实例
        """
        env = environment or self.default_environment
        if not env:
            raise ValueError(
                "No environment specified and no default environment available"
            )

        return env.add_case(case_id, case_data)

    def run_case(
        self, case_id: str, environment: Optional[TestEnvironment] = None
    ) -> TestResult:
        """
        运行测试用例

        Args:
            case_id: 测试用例ID
            environment: 目标环境，默认使用默认环境

        Returns:
            TestResult: 测试结果
        """
        env = environment or self.default_environment
        if not env:
            raise ValueError(
                "No environment specified and no default environment available"
            )

        return env.run_case(case_id)

    def generate_report(
        self, format_type: str = "html", environment: Optional[TestEnvironment] = None
    ) -> str:
        """
        生成测试报告

        Args:
            format_type: 报告格式 ("html", "json")
            environment: 目标环境，默认使用默认环境

        Returns:
            str: 报告文件路径
        """
        env = environment or self.default_environment
        if not env:
            raise ValueError(
                "No environment specified and no default environment available"
            )

        return env.generate_report(format_type)

    def get_status(self) -> Dict[str, Any]:
        """获取框架状态"""
        return {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "environments": len(self.environments),
            "default_environment": str(self.default_environment.path)
            if self.default_environment
            else None,
            "config": self.config,
        }

    def list_environments(self) -> List[Dict[str, Any]]:
        """列出所有环境"""
        result = []
        for name, env in self.environments.items():
            status = env.get_status()
            result.append(
                {
                    "name": name,
                    "path": str(env.path),
                    "isolation": env.isolation,
                    "status": status,
                }
            )
        return result

    def cleanup(self):
        """清理框架资源"""
        for env in self.environments.values():
            # 清理隔离环境
            if hasattr(env, "cleanup_isolation"):
                env.cleanup_isolation()

            # 停止所有运行中的对象
            if hasattr(env.obj_manager, "objects"):
                for obj_name in list(env.obj_manager.objects.keys()):
                    try:
                        env.obj_manager.stop(obj_name)
                    except:
                        pass

        # 清理隔离管理器
        if self.isolation_manager:
            try:
                self.isolation_manager.cleanup_all_environments(force=True)
            except Exception as e:
                get_logger(__name__).error(f"Failed to cleanup isolation manager: {e}")

        self.environments.clear()
        self.default_environment = None

    def get_isolation_status(self) -> Optional[Dict[str, Any]]:
        """获取隔离管理器状态"""
        if self.isolation_manager:
            return self.isolation_manager.get_manager_status()
        return None

    def list_available_isolation_engines(self) -> List[str]:
        """列出可用的隔离引擎"""
        if self.isolation_manager:
            return list(self.isolation_manager.engines.keys())
        return []

    def set_default_isolation_level(self, level: str):
        """设置默认隔离级别"""
        if self.isolation_manager:
            self.isolation_manager.set_default_isolation_level(level)
        else:
            raise RuntimeError("Isolation manager not available")

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器 - 自动清理"""
        self.cleanup()


# 便捷函数
def create_test_framework(config: Optional[Dict[str, Any]] = None) -> TestFramework:
    """
    创建测试框架实例的便捷函数

    Args:
        config: 框架配置参数

    Returns:
        TestFramework: 框架实例
    """
    return TestFramework(config)


def quick_test(
    test_case_data: Dict[str, Any], test_path: str = "./ptest_quick_test"
) -> TestResult:
    """
    快速执行单个测试用例的便捷函数

    Args:
        test_case_data: 测试用例数据
        test_path: 临时测试路径

    Returns:
        TestResult: 测试结果
    """
    with TestFramework() as framework:
        env = framework.create_environment(test_path)
        case = env.add_case("quick_test", test_case_data)
        return case.run()


# 向后兼容的别名
PTestFramework = TestFramework  # 为了与core.py保持一致
