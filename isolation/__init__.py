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

from .enums import IsolationLevel
from .base import IsolationEngine, IsolatedEnvironment
from .manager import IsolationManager

__version__ = "1.0.0"
__all__ = [
    "IsolationLevel",
    "IsolationEngine",
    "IsolatedEnvironment",
    "IsolationManager",
]
