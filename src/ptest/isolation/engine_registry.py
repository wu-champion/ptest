"""
引擎注册表

提供统一的引擎注册、发现和管理机制
"""

from typing import Dict, Any, List, Optional, Type, Callable
from pathlib import Path

from .base import IsolationEngine, IsolatedEnvironment
from .enums import IsolationLevel
from ..core import get_logger

logger = get_logger("engine_registry")


class EngineCapabilities:
    """引擎能力描述"""

    def __init__(
        self,
        supports_snapshots: bool = False,
        supports_containers: bool = False,
        supports_resource_limits: bool = False,
        supports_networking: bool = False,
        supports_volume_management: bool = False,
        max_concurrent_environments: int = 10,
    ):
        self.supports_snapshots = supports_snapshots
        self.supports_containers = supports_containers
        self.supports_resource_limits = supports_resource_limits
        self.supports_networking = supports_networking
        self.supports_volume_management = supports_volume_management
        self.max_concurrent_environments = max_concurrent_environments

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supports_snapshots": self.supports_snapshots,
            "supports_containers": self.supports_containers,
            "supports_resource_limits": self.supports_resource_limits,
            "supports_networking": self.supports_networking,
            "supports_volume_management": self.supports_volume_management,
            "max_concurrent_environments": self.max_concurrent_environments,
        }


class EngineInfo:
    """引擎信息"""

    def __init__(
        self,
        engine_type: str,
        engine_class: Type[IsolationEngine],
        name: str,
        version: str,
        capabilities: EngineCapabilities,
        enabled: bool = True,
        priority: int = 0,
    ):
        self.engine_type = engine_type
        self.engine_class = engine_class
        self.name = name
        self.version = version
        self.capabilities = capabilities
        self.enabled = enabled
        self.priority = priority

    def create_engine(self, config: Dict[str, Any]) -> IsolationEngine:
        """创建引擎实例"""
        return self.engine_class(config)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_type": self.engine_type,
            "name": self.name,
            "version": self.version,
            "capabilities": self.capabilities.to_dict(),
            "enabled": self.enabled,
            "priority": self.priority,
        }


class EngineRegistry:
    """引擎注册表"""

    def __init__(self):
        self._engines: Dict[str, EngineInfo] = {}
        self._default_engine: Optional[str] = None
        self._priority_order: List[str] = []

    def register_engine(
        self,
        engine_type: str,
        engine_class: Type[IsolationEngine],
        name: str,
        version: str = "1.0.0",
        capabilities: Optional[EngineCapabilities] = None,
        enabled: bool = True,
        priority: int = 0,
    ) -> None:
        """注册引擎"""
        if capabilities is None:
            capabilities = self._detect_capabilities(engine_class)

        engine_info = EngineInfo(
            engine_type=engine_type,
            engine_class=engine_class,
            name=name,
            version=version,
            capabilities=capabilities,
            enabled=enabled,
            priority=priority,
        )

        self._engines[engine_type] = engine_info

        if engine_type not in self._priority_order:
            self._priority_order.append(engine_type)

        self._priority_order.sort(
            key=lambda x: self._engines[x].priority,
            reverse=True,
        )

        logger.info(f"Registered engine: {name} ({engine_type})")

    def unregister_engine(self, engine_type: str) -> bool:
        """注销引擎"""
        if engine_type in self._engines:
            del self._engines[engine_type]
            if engine_type in self._priority_order:
                self._priority_order.remove(engine_type)
            logger.info(f"Unregistered engine: {engine_type}")
            return True
        return False

    def get_engine(self, engine_type: str) -> Optional[EngineInfo]:
        """获取引擎信息"""
        return self._engines.get(engine_type)

    def get_all_engines(self) -> Dict[str, EngineInfo]:
        """获取所有注册的引擎"""
        return self._engines.copy()

    def get_enabled_engines(self) -> Dict[str, EngineInfo]:
        """获取所有已启用的引擎"""
        return {k: v for k, v in self._engines.items() if v.enabled}

    def get_engine_by_priority(self) -> Optional[EngineInfo]:
        """按优先级获取最高优先级的引擎"""
        for engine_type in self._priority_order:
            engine = self._engines.get(engine_type)
            if engine and engine.enabled:
                return engine
        return None

    def get_best_engine_for_requirements(
        self, requirements: Dict[str, Any]
    ) -> Optional[EngineInfo]:
        """根据需求获取最佳引擎"""
        requires_container = requirements.get("container_required", False)
        requires_network_isolation = requirements.get("network_isolation", False)
        requires_snapshots = requirements.get("requires_snapshots", False)
        requires_resource_limits = requirements.get("requires_resource_limits", False)

        for engine_type in self._priority_order:
            engine = self._engines.get(engine_type)
            if not engine or not engine.enabled:
                continue

            capabilities = engine.capabilities

            if requires_container and not capabilities.supports_containers:
                continue

            if requires_network_isolation and not capabilities.supports_networking:
                continue

            if requires_snapshots and not capabilities.supports_snapshots:
                continue

            if requires_resource_limits and not capabilities.supports_resource_limits:
                continue

            return engine

        return None

    def set_default_engine(self, engine_type: str) -> None:
        """设置默认引擎"""
        if engine_type in self._engines:
            self._default_engine = engine_type
            logger.info(f"Set default engine: {engine_type}")
        else:
            logger.warning(f"Cannot set default engine: {engine_type} not found")

    def get_default_engine(self) -> Optional[EngineInfo]:
        """获取默认引擎"""
        if self._default_engine:
            return self._engines.get(self._default_engine)
        return self.get_engine_by_priority()

    def compare_engines(self, engine_type1: str, engine_type2: str) -> Dict[str, Any]:
        """比较两个引擎的能力"""
        engine1 = self._engines.get(engine_type1)
        engine2 = self._engines.get(engine_type2)

        if not engine1 or not engine2:
            return {"error": "One or both engines not found"}

        return {
            engine_type1: engine1.capabilities.to_dict(),
            engine_type2: engine2.capabilities.to_dict(),
            "comparison": {
                "snapshots": engine1.capabilities.supports_snapshots
                != engine2.capabilities.supports_snapshots,
                "containers": engine1.capabilities.supports_containers
                != engine2.capabilities.supports_containers,
                "networking": engine1.capabilities.supports_networking
                != engine2.capabilities.supports_networking,
                "resource_limits": engine1.capabilities.supports_resource_limits
                != engine2.capabilities.supports_resource_limits,
            },
        }

    def _detect_capabilities(
        self, engine_class: Type[IsolationEngine]
    ) -> EngineCapabilities:
        """自动检测引擎能力"""
        capabilities = EngineCapabilities()

        class_name = engine_class.__name__.lower()

        if "docker" in class_name:
            capabilities.supports_snapshots = True
            capabilities.supports_containers = True
            capabilities.supports_resource_limits = True
            capabilities.supports_networking = True
            capabilities.supports_volume_management = True
            capabilities.max_concurrent_environments = 50

        elif "virtualenv" in class_name:
            capabilities.supports_snapshots = True
            capabilities.supports_containers = False
            capabilities.supports_resource_limits = False
            capabilities.supports_networking = False
            capabilities.supports_volume_management = False
            capabilities.max_concurrent_environments = 100

        return capabilities

    def list_engine_types(self) -> List[str]:
        """列出所有已注册的引擎类型"""
        return list(self._engines.keys())

    def is_engine_enabled(self, engine_type: str) -> bool:
        """检查引擎是否已启用"""
        engine = self._engines.get(engine_type)
        return engine.enabled if engine else False

    def enable_engine(self, engine_type: str) -> bool:
        """启用引擎"""
        engine = self._engines.get(engine_type)
        if engine:
            engine.enabled = True
            logger.info(f"Enabled engine: {engine_type}")
            return True
        return False

    def disable_engine(self, engine_type: str) -> bool:
        """禁用引擎"""
        engine = self._engines.get(engine_type)
        if engine:
            engine.enabled = False
            logger.info(f"Disabled engine: {engine_type}")
            return True
        return False


_global_registry: Optional[EngineRegistry] = None


def get_global_registry() -> EngineRegistry:
    """获取全局引擎注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = EngineRegistry()
    return _global_registry


def register_default_engines() -> None:
    """注册默认引擎"""
    registry = get_global_registry()

    try:
        from .virtualenv_engine import VirtualenvIsolationEngine

        registry.register_engine(
            engine_type="virtualenv",
            engine_class=VirtualenvIsolationEngine,
            name="Virtualenv",
            version="1.0.0",
            priority=100,
        )
    except Exception as e:
        logger.error(f"Failed to register virtualenv engine: {e}")

    try:
        from .docker_engine import DockerIsolationEngine

        registry.register_engine(
            engine_type="docker",
            engine_class=DockerIsolationEngine,
            name="Docker",
            version="1.0.0",
            priority=50,
        )
    except Exception as e:
        logger.error(f"Failed to register docker engine: {e}")

    registry.set_default_engine("virtualenv")

    logger.info(f"Registered {len(registry.list_engine_types())} engines")
