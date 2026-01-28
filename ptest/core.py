# ptest/core.py
"""
ptest 框架核心配置和工具模块

提供框架的基础配置、常量定义、工具函数和核心抽象类。
这个文件不包含具体的API实现，而是作为整个框架的基础支撑。
"""

import os
import sys
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime
from collections import defaultdict
from enum import Enum
from dataclasses import dataclass, field


# 框架版本和元信息
__version__ = "1.0.1"
__author__ = "ptest team"
__email__ = "ptest@example.com"
__description__ = "A comprehensive testing framework"


class PtestError(Exception):
    """ptest框架基础异常类"""

    pass


class EnvironmentError(PtestError):
    """环境相关异常"""

    pass


class ObjectError(PtestError):
    """对象相关异常"""

    pass


class TestExecutionError(PtestError):
    """测试执行相关异常"""

    pass


class ConfigurationError(PtestError):
    """配置相关异常"""

    pass


# 枚举类型定义
class ObjectStatus(Enum):
    """对象状态枚举"""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    UNKNOWN = "unknown"


class TestStatus(Enum):
    """测试状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class IsolationLevel(Enum):
    """隔离级别枚举"""

    BASIC = "basic"
    VIRTUALENV = "virtualenv"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"


class ReportFormat(Enum):
    """报告格式枚举"""

    HTML = "html"
    JSON = "json"
    XML = "xml"
    PDF = "pdf"


@dataclass
class PtestConfig:
    """ptest框架配置类"""

    # 基础配置
    version: str = __version__
    log_level: str = "INFO"
    max_concurrent_tests: int = 5
    timeout_seconds: int = 300

    # 环境配置
    isolation_level: IsolationLevel = IsolationLevel.BASIC
    cleanup_on_exit: bool = True
    auto_create_dirs: bool = True

    # 数据库默认配置
    default_db_user: str = "root"
    default_db_password: str = ""
    default_db_host: str = "localhost"
    default_db_port: int = 3306

    # 报告配置
    default_report_format: ReportFormat = ReportFormat.HTML
    include_timestamps: bool = True
    include_execution_logs: bool = True

    # 日志配置
    log_file_prefix: str = "ptest"
    log_rotation: bool = True
    max_log_files: int = 10

    # 扩展配置
    plugin_directories: List[str] = field(default_factory=lambda: ["plugins"])
    custom_object_types: Dict[str, str] = field(default_factory=dict)
    hooks: Dict[str, List[Callable]] = field(default_factory=lambda: defaultdict(list))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, (IsolationLevel, ReportFormat)):
                result[key] = value.value
            elif isinstance(value, Enum):
                result[key] = str(value)
            elif callable(value):
                continue  # 跳过函数类型
            else:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PtestConfig":
        """从字典创建配置对象"""
        # 处理枚举类型
        if "isolation_level" in data:
            data["isolation_level"] = IsolationLevel(data["isolation_level"])
        if "default_report_format" in data:
            data["default_report_format"] = ReportFormat(data["default_report_format"])

        return cls(**data)


@dataclass
class TestEnvironment:
    """测试环境数据类"""

    path: Path
    isolation_level: IsolationLevel
    created_at: datetime = field(default_factory=datetime.now)
    last_modified: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)


@dataclass
class ObjectInfo:
    """被测对象信息"""

    name: str
    type_name: str
    status: ObjectStatus
    created_at: datetime = field(default_factory=datetime.now)
    last_started: Optional[datetime] = None
    config: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = ObjectStatus(self.status)


@dataclass
class TestExecution:
    """测试执行记录"""

    case_id: str
    status: TestStatus
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration: float = 0.0
    error_message: str = ""
    output: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self, status: TestStatus, error_message: str = "", output: Any = None):
        """完成测试执行"""
        self.end_time = datetime.now()
        self.duration = (self.end_time - self.start_time).total_seconds()
        self.status = status
        self.error_message = error_message
        self.output = output


class LoggerManager:
    """日志管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._loggers = {}
            self._initialized = True

    def get_logger(
        self, name: str, log_dir: Optional[Path] = None, level: str = "INFO"
    ) -> logging.Logger:
        """获取或创建日志器"""
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(f"ptest.{name}")
        logger.setLevel(getattr(logging, level.upper()))

        # 清除现有处理器
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # 文件处理器
        if log_dir and log_dir.exists():
            log_file = (
                log_dir / f"ptest_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            )
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        self._loggers[name] = logger
        return logger

    def remove_logger(self, name: str):
        """移除日志器"""
        if name in self._loggers:
            logger = self._loggers[name]
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
            del self._loggers[name]


class CommandExecutor:
    """命令执行器"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def execute(
        self,
        command: Union[str, List[str]],
        cwd: Optional[Path] = None,
        timeout: int = 30,
        capture_output: bool = True,
        shell: bool = False,
    ) -> Dict[str, Any]:
        """
        执行命令

        Args:
            command: 要执行的命令
            cwd: 工作目录
            timeout: 超时时间（秒）
            capture_output: 是否捕获输出
            shell: 是否使用shell执行

        Returns:
            Dict: 执行结果
        """
        if isinstance(command, str) and not shell:
            command = command.split()
        elif isinstance(command, list) and shell:
            command = " ".join(command)

        self.logger.debug(f"Executing command: {command}")

        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                timeout=timeout,
                capture_output=capture_output,
                text=True,
                shell=shell,
            )

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout if capture_output else "",
                "stderr": result.stderr if capture_output else "",
                "command": command,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "command": command,
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "command": command,
            }


class ConfigManager:
    """配置管理器"""

    DEFAULT_CONFIG = PtestConfig()

    @staticmethod
    def load_config(config_path: Path) -> PtestConfig:
        """加载配置文件"""
        if not config_path.exists():
            return ConfigManager.DEFAULT_CONFIG

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PtestConfig.from_dict(data)
        except (json.JSONDecodeError, TypeError) as e:
            raise ConfigurationError(f"Invalid config file {config_path}: {e}")

    @staticmethod
    def save_config(config: PtestConfig, config_path: Path):
        """保存配置文件"""
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(
                    config.to_dict(), f, indent=2, ensure_ascii=False, default=str
                )
        except Exception as e:
            raise ConfigurationError(f"Failed to save config to {config_path}: {e}")

    @staticmethod
    def create_default_config(config_path: Path):
        """创建默认配置文件"""
        ConfigManager.save_config(ConfigManager.DEFAULT_CONFIG, config_path)


class PathManager:
    """路径管理器"""

    @staticmethod
    def ensure_directory(
        path: Path, parents: bool = True, exist_ok: bool = True
    ) -> Path:
        """确保目录存在"""
        if not path.exists():
            path.mkdir(parents=parents, exist_ok=exist_ok)
        return path

    @staticmethod
    def create_test_environment_structure(base_path: Path) -> Dict[str, Path]:
        """创建测试环境目录结构"""
        directories = {
            "objects": base_path / "objects",
            "tools": base_path / "tools",
            "cases": base_path / "cases",
            "logs": base_path / "logs",
            "reports": base_path / "reports",
            "data": base_path / "data",
            "scripts": base_path / "scripts",
            "temp": base_path / "temp",
        }

        for name, path in directories.items():
            PathManager.ensure_directory(path)

        return directories


class HookManager:
    """钩子管理器"""

    def __init__(self):
        self.hooks: Dict[str, List[Callable]] = defaultdict(list)

    def register_hook(self, hook_name: str, callback: Callable):
        """注册钩子"""
        self.hooks[hook_name].append(callback)

    def unregister_hook(self, hook_name: str, callback: Callable):
        """取消注册钩子"""
        if callback in self.hooks[hook_name]:
            self.hooks[hook_name].remove(callback)

    def execute_hooks(self, hook_name: str, *args, **kwargs):
        """执行钩子"""
        results = []
        for callback in self.hooks[hook_name]:
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                # 记录错误但不中断其他钩子的执行
                logging.getLogger(__name__).error(f"Hook {hook_name} failed: {e}")
        return results


# 全局实例
logger_manager = LoggerManager()
hook_manager = HookManager()


# 便捷函数
def get_logger(
    name: str, log_dir: Optional[Path] = None, level: str = "INFO"
) -> logging.Logger:
    """获取日志器的便捷函数"""
    return logger_manager.get_logger(name, log_dir, level)


def execute_command(command: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
    """执行命令的便捷函数"""
    executor = CommandExecutor()
    return executor.execute(command, **kwargs)


def get_default_config() -> PtestConfig:
    """获取默认配置的便捷函数"""
    return ConfigManager.DEFAULT_CONFIG


# 框架信息
FRAMEWORK_INFO = {
    "name": "ptest",
    "version": __version__,
    "author": __author__,
    "email": __email__,
    "description": __description__,
    "python_requires": ">=3.8",
    "license": "MIT",
}


# 常量定义
DEFAULT_TEST_DIRECTORIES = [
    "objects",
    "tools",
    "cases",
    "logs",
    "reports",
    "data",
    "scripts",
    "temp",
]
SUPPORTED_DATABASE_TYPES = ["mysql", "postgresql", "sqlite", "oracle", "mongodb"]
SUPPORTED_TEST_TYPES = ["api", "database", "web", "service", "ui"]
SUPPORTED_REPORT_FORMATS = [fmt.value for fmt in ReportFormat]
SUPPORTED_ISOLATION_LEVELS = [level.value for level in IsolationLevel]

# 颜色输出常量
COLOR_CODES = {
    "reset": "\033[0m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "white": "\033[97m",
    "bold": "\033[1m",
}


def get_colored_text(text: str, color_code: int) -> str:
    """获取彩色文本"""
    color_map = {
        91: COLOR_CODES["red"],
        92: COLOR_CODES["green"],
        93: COLOR_CODES["yellow"],
        94: COLOR_CODES["blue"],
        95: COLOR_CODES["magenta"],
        96: COLOR_CODES["cyan"],
        97: COLOR_CODES["white"],
    }
    color = color_map.get(color_code, COLOR_CODES["white"])
    return f"{color}{text}{COLOR_CODES['reset']}"


def print_colored(text: str, color_code: int):
    """打印彩色文本"""
    print(get_colored_text(text, color_code))


# 向后兼容的别名（保持与旧代码的兼容性）
PTestError = PtestError
BaseManagedObject = object  # 空的基类，向后兼容
