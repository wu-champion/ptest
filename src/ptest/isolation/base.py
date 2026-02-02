"""
隔离引擎抽象基类

定义了隔离引擎和隔离环境的抽象接口
所有具体的隔离实现都需要继承这些基类
"""

from abc import ABC, abstractmethod
from datetime import datetime
import time
from typing import Dict, Any, Optional, List, Union, Callable, TYPE_CHECKING, TypedDict
from pathlib import Path
from .enums import (
    EnvironmentStatus,
    ProcessStatus,
    NetworkStatus,
    IsolationEvent,
    ResourceType,
    SecurityLevel,
    CleanupPolicy,
)
from ..core import get_logger

logger = get_logger("isolation.base")


# 定义一些辅助类型
class ProcessResult(TypedDict):
    """进程执行结果"""

    returncode: int
    stdout: str
    stderr: str
    command: List[str]
    timeout: Optional[float]
    start_time: datetime
    end_time: Optional[datetime]


class EnvironmentSnapshot(TypedDict):
    """环境快照数据结构"""

    snapshot_id: str
    env_id: str
    created_at: datetime
    metadata: Dict[str, Any]
    data: Dict[str, Any]
    snapshot_type: str


# 前向引用，避免循环导入
if TYPE_CHECKING:
    from .basic_engine import BasicIsolationEngine
    from .virtualenv_engine import VirtualenvIsolationEngine
    from .docker_engine import DockerIsolationEngine


class IsolatedEnvironment(ABC):
    """隔离环境抽象基类"""

    def __init__(
        self,
        env_id: str,
        path: Path,
        isolation_engine: "IsolationEngine",
        config: Optional[Dict[str, Any]] = None,
    ):
        self.env_id = env_id
        self.path = path
        self.isolation_engine = isolation_engine
        self.config = config or {}
        self.status = EnvironmentStatus.CREATED
        self.created_at = datetime.now()
        self.activated_at: Optional[datetime] = None
        self.deactivated_at: Optional[datetime] = None
        self.last_activity = datetime.now()
        self.processes: Dict[str, ProcessInfo] = {}
        self.allocated_ports: List[int] = []
        self.resource_usage = {
            "cpu": 0.0,
            "memory": 0,
            "disk": 0,
            "network": 0.0,
        }
        self._event_listeners: Dict[IsolationEvent, List[Callable]] = {}

    @abstractmethod
    def activate(self) -> bool:
        """激活环境"""
        pass

    @abstractmethod
    def deactivate(self) -> bool:
        """停用环境"""
        pass

    @abstractmethod
    def execute_command(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        env_vars: Optional[Dict[str, str]] = None,
        cwd: Optional[Path] = None,
    ) -> ProcessResult:
        """在隔离环境中执行命令"""
        pass

    @abstractmethod
    def install_package(
        self, package: str, version: Optional[str] = None, upgrade: bool = False
    ) -> bool:
        """安装包"""
        pass

    @abstractmethod
    def uninstall_package(self, package: str) -> bool:
        """卸载包"""
        pass

    @abstractmethod
    def get_installed_packages(self) -> Dict[str, str]:
        """获取已安装的包"""
        pass

    @abstractmethod
    def get_package_version(self, package: str) -> Optional[str]:
        """获取包版本"""
        pass

    @abstractmethod
    def allocate_port(self) -> int:
        """分配端口"""
        pass

    @abstractmethod
    def release_port(self, port: int) -> bool:
        """释放端口"""
        pass

    @abstractmethod
    def cleanup(self, force: bool = False) -> bool:
        """清理环境"""
        pass

    @abstractmethod
    def validate_isolation(self) -> bool:
        """验证隔离有效性"""
        pass

    # 快照功能作为抽象方法，由具体引擎实现

    @abstractmethod
    def create_snapshot(self, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        """创建环境快照 - 必须由子类实现"""
        raise NotImplementedError

    @abstractmethod
    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """从快照恢复环境 - 必须由子类实现"""
        raise NotImplementedError

    @abstractmethod
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照 - 必须由子类实现"""
        raise NotImplementedError

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """列出快照 - 由管理器处理"""
        return []

    def get_status(self) -> Dict[str, Any]:
        """获取环境状态"""
        return {
            "env_id": self.env_id,
            "path": str(self.path),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "activated_at": self.activated_at.isoformat()
            if self.activated_at
            else None,
            "deactivated_at": self.deactivated_at.isoformat()
            if self.deactivated_at
            else None,
            "last_activity": self.last_activity.isoformat(),
            "isolation_type": self.__class__.__name__,
            "process_count": len(self.processes),
            "allocated_ports": len(self.allocated_ports),
            "resource_usage": self.resource_usage,
            "config": self.config,
        }

    def add_event_listener(self, event: IsolationEvent, callback: Callable):
        """添加事件监听器"""
        if event not in self._event_listeners:
            self._event_listeners[event] = []
        self._event_listeners[event].append(callback)

    def remove_event_listener(self, event: IsolationEvent, callback: Callable):
        """移除事件监听器"""
        if event in self._event_listeners:
            try:
                self._event_listeners[event].remove(callback)
            except ValueError:
                pass

    def _emit_event(self, event: IsolationEvent, *args, **kwargs):
        """触发事件"""
        if event in self._event_listeners:
            for callback in self._event_listeners[event]:
                try:
                    callback(self, event, *args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in event listener for {event}: {e}")

    def update_resource_usage(self):
        """更新资源使用情况"""
        # 子类可以重写此方法来更新资源使用情况
        self.last_activity = datetime.now()


class IsolationEngine(ABC):
    """隔离引擎抽象基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.created_environments: Dict[str, IsolatedEnvironment] = {}
        self.engine_name = self.__class__.__name__
        self.supported_features: List[str] = []
        # 使用已有的logger，避免重复创建
        self.logger = logger
        self.engine_config = config  # 添加engine_config属性
        self.docker_client: Optional[Any] = None  # Docker客户端属性

    @abstractmethod
    def create_isolation(
        self, path: Path, env_id: str, isolation_config: Dict[str, Any]
    ) -> IsolatedEnvironment:
        """创建隔离环境"""
        pass

    @abstractmethod
    def cleanup_isolation(self, env: IsolatedEnvironment) -> bool:
        """清理隔离环境"""
        pass

    @abstractmethod
    def get_isolation_status(self, env_id: str) -> Dict[str, Any]:
        """获取隔离状态"""
        pass

    @abstractmethod
    def validate_isolation(self, env: IsolatedEnvironment) -> bool:
        """验证隔离有效性"""
        pass

    @abstractmethod
    def get_supported_features(self) -> List[str]:
        """获取支持的功能列表"""
        pass

    @abstractmethod
    def check_environment_health(self, env: IsolatedEnvironment) -> bool:
        """检查环境健康状态"""
        pass

    @abstractmethod
    def get_environment_metrics(self, env: IsolatedEnvironment) -> Dict[str, Any]:
        """获取环境指标"""
        pass

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "name": self.engine_name,
            "config": self.config,
            "supported_features": self.get_supported_features(),
            "environment_count": len(self.created_environments),
            "created_environments": list(self.created_environments.keys()),
        }

    def cleanup_all_environments(self) -> int:
        """清理所有环境"""
        cleaned_count = 0
        for env_id in list(self.created_environments.keys()):
            env = self.created_environments[env_id]
            if self.cleanup_isolation(env):
                cleaned_count += 1
            # 无论是否成功，都从列表中移除
            if env_id in self.created_environments:
                del self.created_environments[env_id]
        return cleaned_count

    def list_environments(self) -> Dict[str, Dict[str, Any]]:
        """列出所有环境"""
        status_dict = {}
        for env_id, env in self.created_environments.items():
            status_dict[env_id] = env.get_status()
        return status_dict

    def validate_config(self) -> bool:
        """验证配置有效性"""
        # 基础验证，子类可以重写
        return isinstance(self.config, dict)

    def initialize_client(self) -> bool:
        """初始化客户端（子类可以重写）"""
        return True


class ProcessInfo:
    """进程信息"""

    def __init__(
        self,
        process_id: str,
        command: List[str],
        pid: Optional[int] = None,
        status: ProcessStatus = ProcessStatus.STARTING,
    ):
        self.process_id = process_id
        self.command = command
        self.pid = pid
        self.status = status
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.exit_code: Optional[int] = None
        self.stdout: str = ""
        self.stderr: str = ""
        self.timeout: Optional[float] = None

    def mark_completed(self, exit_code: int, stdout: str = "", stderr: str = ""):
        """标记进程完成"""
        self.end_time = datetime.now()
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.status = ProcessStatus.STOPPED if exit_code == 0 else ProcessStatus.ERROR

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "process_id": self.process_id,
            "command": self.command,
            "pid": self.pid,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "exit_code": self.exit_code,
            "timeout": self.timeout,
            "duration": (self.end_time - self.start_time).total_seconds()
            if self.end_time
            else None,
        }
