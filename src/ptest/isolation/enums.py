"""
隔离模块枚举类型定义

定义了隔离级别、状态、事件类型等枚举值
"""

from enum import Enum


class IsolationLevel(Enum):
    """隔离级别枚举"""

    BASIC = "basic"  # 基础文件系统隔离
    VIRTUALENV = "virtualenv"  # Python虚拟环境隔离
    DOCKER = "docker"  # Docker容器隔离
    KUBERNETES = "kubernetes"  # Kubernetes集群隔离


class EnvironmentStatus(Enum):
    """环境状态枚举"""

    INITIALIZING = "initializing"  # 初始化中
    CREATED = "created"  # 已创建
    ACTIVATING = "activating"  # 激活中
    ACTIVE = "active"  # 已激活
    DEACTIVATING = "deactivating"  # 停用中
    INACTIVE = "inactive"  # 已停用
    CLEANUP_START = "cleanup_start"  # 清理开始
    CLEANING = "cleaning"  # 清理中
    CLEANUP_COMPLETE = "cleanup_complete"  # 清理完成
    ERROR = "error"  # 错误状态


class ProcessStatus(Enum):
    """进程状态枚举"""

    STARTING = "starting"  # 启动中
    RUNNING = "running"  # 运行中
    STOPPING = "stopping"  # 停止中
    STOPPED = "stopped"  # 已停止
    ERROR = "error"  # 错误状态
    TIMEOUT = "timeout"  # 超时状态


class NetworkStatus(Enum):
    """网络状态枚举"""

    INITIALIZING = "initializing"  # 初始化中
    READY = "ready"  # 就绪
    CONNECTED = "connected"  # 已连接
    DISCONNECTED = "disconnected"  # 已断开
    ERROR = "error"  # 错误状态


class IsolationEvent(Enum):
    """隔离事件类型枚举"""

    ENVIRONMENT_CREATING = "environment_creating"
    ENVIRONMENT_CREATED = "environment_created"
    ENVIRONMENT_ACTIVATING = "environment_activating"
    ENVIRONMENT_ACTIVATED = "environment_activated"
    ENVIRONMENT_DEACTIVATING = "environment_deactivating"
    ENVIRONMENT_DEACTIVATED = "environment_deactivated"
    ENVIRONMENT_CLEANUP_START = "environment_cleanup_start"
    ENVIRONMENT_CLEANUP_COMPLETE = "environment_cleanup_complete"
    PROCESS_STARTING = "process_starting"
    PROCESS_STARTED = "process_started"
    PROCESS_STOPPING = "process_stopping"
    PROCESS_STOPPED = "process_stopped"
    NETWORK_ALLOCATING = "network_allocating"
    NETWORK_ALLOCATED = "network_allocated"
    NETWORK_RELEASING = "network_releasing"
    NETWORK_RELEASED = "network_released"
    PACKAGE_INSTALLING = "package_installing"
    PACKAGE_INSTALLED = "package_installed"
    SNAPSHOT_CREATING = "snapshot_creating"
    SNAPSHOT_CREATED = "snapshot_created"
    SNAPSHOT_RESTORING = "snapshot_restoring"
    SNAPSHOT_RESTORED = "snapshot_restored"
    SNAPSHOT_DELETING = "snapshot_deleting"
    SNAPSHOT_DELETED = "snapshot_deleted"
    ERROR_OCCURRED = "error_occurred"


class ResourceType(Enum):
    """资源类型枚举"""

    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    PORT = "port"


class SecurityLevel(Enum):
    """安全级别枚举"""

    LOW = "low"  # 低安全级别（较少限制）
    MEDIUM = "medium"  # 中等安全级别
    HIGH = "high"  # 高安全级别（严格限制）
    STRICT = "strict"  # 严格安全级别（最大限制）


class CleanupPolicy(Enum):
    """清理策略枚举"""

    IMMEDIATE = "immediate"  # 立即清理
    ON_REQUEST = "on_request"  # 请求时清理
    ON_SHUTDOWN = "on_shutdown"  # 关闭时清理
    SCHEDULED = "scheduled"  # 定时清理
    NEVER = "never"  # 从不清理（手动清理）
