"""
引擎注册表

提供统一的隔离引擎注册、发现和初始化机制
支持动态加载和插件化架构
"""

import importlib
import inspect
from typing import Dict, Any, Optional, List, Type, Callable
from dataclasses import dataclass

from .base import IsolationEngine
from .enums import IsolationLevel
from ..core import get_logger

logger = get_logger("engine_registry")


@dataclass
class EngineInfo:
    """引擎信息"""

    name: str
    engine_class: Type[IsolationEngine]
    description: str
    version: str = "1.0.0"
    author: str = "Unknown"
    supported_features: List[str] | None = None
    dependencies: List[str] | None = None
    config_schema: Dict[str, Any] | None = None
    priority: int = 100  # 优先级，数字越小优先级越高

    def __post_init__(self):
        if self.supported_features is None:
            self.supported_features = []
        if self.dependencies is None:
            self.dependencies = []
        if self.config_schema is None:
            self.config_schema = {}


class EngineRegistry:
    """引擎注册表

    提供统一的引擎管理接口，支持：
    - 动态注册和发现
    - 依赖检查和解析
    - 优先级管理
    - 插件化加载
    """

    def __init__(self):
        self._engines: Dict[str, EngineInfo] = {}
        self._engine_instances: Dict[str, IsolationEngine] = {}
        self._loaders: List[Callable] = []
        self.logger = logger

        # 注册默认加载器
        self._register_default_loaders()

    def _register_default_loaders(self):
        """注册默认的引擎加载器"""
        self._loaders.append(self._load_builtin_engines)
        self._loaders.append(self._load_plugin_engines)

    def register_engine(
        self,
        name: str,
        engine_class: Type[IsolationEngine],
        description: str = "",
        version: str = "1.0.0",
        author: str = "Unknown",
        supported_features: List[str] = None,
        dependencies: List[str] = None,
        config_schema: Dict[str, Any] = None,
        priority: int = 100,
        replace: bool = False,
    ) -> bool:
        """注册引擎

        Args:
            name: 引擎名称
            engine_class: 引擎类
            description: 描述
            version: 版本
            author: 作者
            supported_features: 支持的功能
            dependencies: 依赖的其他引擎
            config_schema: 配置模式
            priority: 优先级
            replace: 是否替换已存在的引擎

        Returns:
            bool: 是否注册成功
        """
        if name in self._engines and not replace:
            self.logger.warning(
                f"Engine '{name}' already registered, use replace=True to override"
            )
            return False

        # 验证引擎类
        if not self._validate_engine_class(engine_class):
            self.logger.error(f"Invalid engine class for '{name}'")
            return False

        # 检查依赖
        if dependencies and not self._check_dependencies(dependencies):
            self.logger.error(
                f"Dependencies not satisfied for engine '{name}': {dependencies}"
            )
            return False

        engine_info = EngineInfo(
            name=name,
            engine_class=engine_class,
            description=description,
            version=version,
            author=author,
            supported_features=supported_features or [],
            dependencies=dependencies or [],
            config_schema=config_schema or {},
            priority=priority,
        )

        self._engines[name] = engine_info
        self.logger.info(f"Registered engine: {name} v{version} by {author}")

        return True

    def unregister_engine(self, name: str) -> bool:
        """注销引擎

        Args:
            name: 引擎名称

        Returns:
            bool: 是否注销成功
        """
        if name not in self._engines:
            self.logger.warning(f"Engine '{name}' not found")
            return False

        # 检查是否有其他引擎依赖此引擎
        dependent_engines = [
            engine_name
            for engine_name, info in self._engines.items()
            if name in info.dependencies
        ]

        if dependent_engines:
            self.logger.error(
                f"Cannot unregister engine '{name}', required by: {dependent_engines}"
            )
            return False

        # 清理实例
        if name in self._engine_instances:
            del self._engine_instances[name]

        del self._engines[name]
        self.logger.info(f"Unregistered engine: {name}")

        return True

    def get_engine_info(self, name: str) -> Optional[EngineInfo]:
        """获取引擎信息

        Args:
            name: 引擎名称

        Returns:
            EngineInfo: 引擎信息，如果不存在则返回None
        """
        return self._engines.get(name)

    def list_engines(
        self, include_instances: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """列出所有引擎

        Args:
            include_instances: 是否包含实例信息

        Returns:
            Dict: 引擎列表
        """
        result = {}

        # 按优先级排序
        sorted_engines = sorted(self._engines.items(), key=lambda x: x[1].priority)

        for name, info in sorted_engines:
            engine_data = {
                "name": info.name,
                "description": info.description,
                "version": info.version,
                "author": info.author,
                "supported_features": info.supported_features,
                "dependencies": info.dependencies,
                "priority": info.priority,
                "class_name": info.engine_class.__name__,
                "module": info.engine_class.__module__,
            }

            if include_instances and name in self._engine_instances:
                engine_data["instance"] = {"initialized": True, "status": "active"}
            else:
                engine_data["instance"] = {"initialized": False, "status": "inactive"}

            result[name] = engine_data

        return result

    def create_engine(
        self, name: str, config: Dict[str, Any] = None, force_recreate: bool = False
    ) -> Optional[IsolationEngine]:
        """创建引擎实例

        Args:
            name: 引擎名称
            config: 配置参数
            force_recreate: 是否强制重新创建

        Returns:
            IsolationEngine: 引擎实例，如果创建失败则返回None
        """
        if name not in self._engines:
            self.logger.error(f"Engine '{name}' not found")
            return None

        # 如果已存在且不强制重新创建
        if name in self._engine_instances and not force_recreate:
            self.logger.debug(f"Engine '{name}' already exists")
            return self._engine_instances[name]

        engine_info = self._engines[name]

        try:
            # 合并默认配置
            final_config = config or {}
            if engine_info.config_schema:
                final_config = self._merge_config(
                    final_config, engine_info.config_schema
                )

            # 创建实例
            engine = engine_info.engine_class(final_config)

            # 验证实例
            if not self._validate_engine_instance(engine):
                self.logger.error(f"Engine instance validation failed for '{name}'")
                return None

            self._engine_instances[name] = engine
            self.logger.info(f"Created engine instance: {name}")

            return engine

        except Exception as e:
            self.logger.error(f"Failed to create engine '{name}': {e}")
            return None

    def get_engine(self, name: str) -> Optional[IsolationEngine]:
        """获取引擎实例

        Args:
            name: 引擎名称

        Returns:
            IsolationEngine: 引擎实例，如果不存在则返回None
        """
        return self._engine_instances.get(name)

    def destroy_engine(self, name: str) -> bool:
        """销毁引擎实例

        Args:
            name: 引擎名称

        Returns:
            bool: 是否销毁成功
        """
        if name not in self._engine_instances:
            self.logger.warning(f"Engine instance '{name}' not found")
            return False

        try:
            engine = self._engine_instances[name]

            # 如果引擎有清理方法，调用它
            if hasattr(engine, "cleanup"):
                engine.cleanup()

            del self._engine_instances[name]
            self.logger.info(f"Destroyed engine instance: {name}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to destroy engine '{name}': {e}")
            return False

    def discover_engines(self, search_paths: List[str] = None) -> int:
        """发现并注册引擎

        Args:
            search_paths: 搜索路径列表

        Returns:
            int: 发现的引擎数量
        """
        discovered_count = 0

        # 使用默认搜索路径
        if not search_paths:
            search_paths = [
                "ptest.isolation.engines",
                "ptest_plugins.isolation",
                "ptest.engines",
            ]

        for loader in self._loaders:
            try:
                count = loader(search_paths)
                discovered_count += count
            except Exception as e:
                self.logger.error(f"Engine loader failed: {e}")

        self.logger.info(f"Discovered {discovered_count} new engines")
        return discovered_count

    def _load_builtin_engines(self, search_paths: List[str]) -> int:
        """加载内置引擎"""
        count = 0

        # 注册内置引擎
        try:
            from .basic_engine import BasicIsolationEngine
            from .virtualenv_engine import VirtualenvIsolationEngine
            from .docker_engine import DockerIsolationEngine

            # Basic 引擎
            self.register_engine(
                name=IsolationLevel.BASIC.value,
                engine_class=BasicIsolationEngine,
                description="基础文件系统隔离",
                version="1.0.0",
                author="ptest team",
                supported_features=["filesystem_isolation", "basic_process_execution"],
                priority=10,  # 最高优先级
            )
            count += 1

            # Virtualenv 引擎
            self.register_engine(
                name=IsolationLevel.VIRTUALENV.value,
                engine_class=VirtualenvIsolationEngine,
                description="Python虚拟环境隔离",
                version="1.0.0",
                author="ptest team",
                supported_features=["python_package_isolation", "process_execution"],
                dependencies=[IsolationLevel.BASIC.value],  # 依赖基础隔离
                priority=20,
            )
            count += 1

            # Docker 引擎
            self.register_engine(
                name=IsolationLevel.DOCKER.value,
                engine_class=DockerIsolationEngine,
                description="Docker容器隔离",
                version="1.0.0",
                author="ptest team",
                supported_features=[
                    "container_isolation",
                    "network_isolation",
                    "volume_management",
                    "image_management",
                ],
                dependencies=[IsolationLevel.BASIC.value],  # 依赖基础隔离
                priority=30,
            )
            count += 1

        except ImportError as e:
            self.logger.warning(f"Failed to import builtin engines: {e}")

        return count

    def _load_plugin_engines(self, search_paths: List[str]) -> int:
        """加载插件引擎"""
        count = 0

        for module_path in search_paths:
            try:
                # 尝试导入模块
                module = importlib.import_module(module_path)

                # 查找模块中的引擎类
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, IsolationEngine)
                        and obj != IsolationEngine
                        and hasattr(obj, "__engine_info__")
                    ):
                        # 使用引擎信息注册
                        engine_info = obj.__engine_info__
                        self.register_engine(
                            name=engine_info.get("name", name),
                            engine_class=obj,
                            description=engine_info.get("description", ""),
                            version=engine_info.get("version", "1.0.0"),
                            author=engine_info.get("author", "Unknown"),
                            supported_features=engine_info.get(
                                "supported_features", []
                            ),
                            dependencies=engine_info.get("dependencies", []),
                            config_schema=engine_info.get("config_schema", {}),
                            priority=engine_info.get("priority", 100),
                        )
                        count += 1

            except ImportError:
                # 模块不存在，跳过
                continue
            except Exception as e:
                self.logger.error(f"Failed to load plugin from {module_path}: {e}")

        return count

    def _validate_engine_class(self, engine_class: Type[IsolationEngine]) -> bool:
        """验证引擎类"""
        try:
            # 检查是否继承自 IsolationEngine
            if not issubclass(engine_class, IsolationEngine):
                return False

            # 检查必需的属性（不要求所有方法，因为有些可能是抽象的）
            required_attributes = ["engine_name", "isolation_level"]

            for attr in required_attributes:
                if not hasattr(engine_class, attr):
                    self.logger.error(
                        f"Engine class missing required attribute: {attr}"
                    )
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Engine class validation failed: {e}")
            return False

            # 检查必需的方法
            required_methods = [
                "create_isolation",
                "cleanup_isolation",
                "activate",
                "deactivate",
                "execute_command",
                "install_package",
                "uninstall_package",
            ]

            for method in required_methods:
                if not hasattr(engine_class, method):
                    self.logger.error(f"Engine class missing required method: {method}")
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Engine class validation failed: {e}")
            return False

    def _validate_engine_instance(self, engine: IsolationEngine) -> bool:
        """验证引擎实例"""
        try:
            # 基础属性检查
            if not hasattr(engine, "engine_name"):
                return False

            if not hasattr(engine, "isolation_level"):
                return False

            return True

        except Exception as e:
            self.logger.error(f"Engine instance validation failed: {e}")
            return False

    def _check_dependencies(self, dependencies: List[str]) -> bool:
        """检查依赖是否满足"""
        for dep in dependencies:
            if dep not in self._engines:
                return False
        return True

    def _merge_config(
        self, user_config: Dict[str, Any], schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """合并用户配置和模式"""
        merged = {}

        # 首先添加模式中的默认值
        for key, value in schema.items():
            if isinstance(value, dict) and "default" in value:
                merged[key] = value["default"]
            else:
                merged[key] = value

        # 然后覆盖用户配置
        merged.update(user_config)

        return merged

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """获取依赖图

        Returns:
            Dict: 依赖关系图 {engine: [dependencies]}
        """
        graph = {}

        for name, info in self._engines.items():
            graph[name] = info.dependencies.copy()

        return graph

    def get_load_order(self) -> List[str]:
        """获取引擎加载顺序（基于依赖关系）

        Returns:
            List[str]: 按依赖关系排序的引擎名称列表
        """
        # 拓扑排序
        graph = self.get_dependency_graph()
        in_degree = {engine: 0 for engine in graph}

        # 计算入度
        for engine in graph:
            for dep in graph[engine]:
                if dep in in_degree:
                    in_degree[engine] += 1

        # 拓扑排序
        queue = [engine for engine, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            # 更新依赖此引擎的其他引擎的入度
            for engine in graph:
                if current in graph[engine]:
                    in_degree[engine] -= 1
                    if in_degree[engine] == 0:
                        queue.append(engine)

        return result

    def cleanup(self):
        """清理所有引擎实例"""
        for name in list(self._engine_instances.keys()):
            self.destroy_engine(name)

        self.logger.info("Cleaned up all engine instances")


# 全局引擎注册表实例
_global_registry: Optional[EngineRegistry] = None


def get_engine_registry() -> EngineRegistry:
    """获取全局引擎注册表实例

    Returns:
        EngineRegistry: 全局注册表实例
    """
    global _global_registry

    if _global_registry is None:
        _global_registry = EngineRegistry()
        _global_registry.discover_engines()

    return _global_registry


def register_engine(**kwargs) -> bool:
    """便捷的引擎注册函数

    Returns:
        bool: 是否注册成功
    """
    registry = get_engine_registry()
    return registry.register_engine(**kwargs)


def create_engine(
    name: str, config: Dict[str, Any] = None
) -> Optional[IsolationEngine]:
    """便捷的引擎创建函数

    Args:
        name: 引擎名称
        config: 配置参数

    Returns:
        IsolationEngine: 引擎实例
    """
    registry = get_engine_registry()
    return registry.create_engine(name, config)


def list_available_engines() -> Dict[str, Dict[str, Any]]:
    """便捷的引擎列表函数

    Returns:
        Dict: 可用引擎列表
    """
    registry = get_engine_registry()
    return registry.list_engines()
