"""
环境隔离模块

提供多层次的环境隔离功能，包括：
- 基础文件系统隔离
- Python虚拟环境隔离
- Docker容器隔离
- 进程和网络隔离

主要组件：
- IsolationEngine: 隔离引擎抽象基类
- IsolationManager: 隔离管理器
- VirtualenvIsolationEngine: Virtualenv隔离实现
- DockerIsolationEngine: Docker隔离实现
"""

from .base import IsolationEngine, IsolatedEnvironment, ProcessResult, EnvironmentStatus
from .enums import (
    EnvironmentStatus,
    ProcessStatus,
    NetworkStatus,
    IsolationEvent,
    ResourceType,
    SecurityLevel,
    CleanupPolicy,
    IsolationLevel,
)
from .manager import IsolationManager
from .virtualenv_engine import VirtualenvIsolationEngine, VirtualenvEnvironment
from .docker_engine import DockerIsolationEngine, DockerEnvironment
from .managers import ImageManager, NetworkManager, VolumeManager
from .engine_registry import (
    EngineRegistry,
    EngineCapabilities,
    EngineInfo,
    get_global_registry,
    register_default_engines,
)
from .environment_migration import (
    EnvironmentMigrator,
    SnapshotCrossEngineConverter,
    MigrationProgress,
    migrate_environment,
)

__all__ = [
    "IsolationEngine",
    "IsolatedEnvironment",
    "ProcessResult",
    "EnvironmentStatus",
    "ProcessStatus",
    "NetworkStatus",
    "IsolationEvent",
    "ResourceType",
    "SecurityLevel",
    "CleanupPolicy",
    "IsolationLevel",
    "IsolationManager",
    "VirtualenvIsolationEngine",
    "VirtualenvEnvironment",
    "DockerIsolationEngine",
    "DockerEnvironment",
    "ImageManager",
    "NetworkManager",
    "VolumeManager",
    "EngineRegistry",
    "EngineCapabilities",
    "EngineInfo",
    "get_global_registry",
    "register_default_engines",
    "EnvironmentMigrator",
    "SnapshotCrossEngineConverter",
    "MigrationProgress",
    "migrate_environment",
]
__version__ = "1.1.0"
