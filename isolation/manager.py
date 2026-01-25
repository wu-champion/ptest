"""
隔离管理器

负责管理所有隔离引擎和环境，提供统一的隔离管理接口
"""

import uuid
import time
import logging
from typing import Dict, Any, Optional, List, Type
from pathlib import Path

from .base import IsolationEngine, IsolatedEnvironment
from .enums import IsolationLevel, EnvironmentStatus, IsolationEvent

logger = logging.getLogger(__name__)


class IsolationManager:
    """隔离管理器"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.engines: Dict[str, IsolationEngine] = {}
        self.active_environments: Dict[str, IsolatedEnvironment] = {}
        self.engine_classes: Dict[str, Type[IsolationEngine]] = {}
        self.default_isolation_level = self.config.get(
            "default_isolation_level", IsolationLevel.BASIC.value
        )
        self.max_environments = self.config.get("max_environments", 100)
        self.cleanup_policy = self.config.get("cleanup_policy", "on_request")
        self.logger = logging.getLogger(f"{__name__}.IsolationManager")

        # 注册内置引擎类
        self._register_builtin_engines()

        # 初始化引擎
        self._initialize_engines()

    def _register_builtin_engines(self):
        """注册内置引擎类"""
        # 这里先注册占位符，实际实现在后续文件中
        from .basic_engine import BasicIsolationEngine
        from .virtualenv_engine import VirtualenvIsolationEngine
        from .docker_engine import DockerIsolationEngine

        self.engine_classes[IsolationLevel.BASIC.value] = BasicIsolationEngine
        self.engine_classes[IsolationLevel.VIRTUALENV.value] = VirtualenvIsolationEngine
        self.engine_classes[IsolationLevel.DOCKER.value] = DockerIsolationEngine

    def _initialize_engines(self):
        """初始化隔离引擎"""
        for level, engine_class in self.engine_classes.items():
            try:
                engine_config = self.config.get(level, {})
                engine = engine_class(engine_config)
                self.engines[level] = engine
                self.logger.info(f"Initialized isolation engine: {level}")
            except Exception as e:
                self.logger.error(f"Failed to initialize isolation engine {level}: {e}")

    def register_engine(self, level: str, engine_class: Type[IsolationEngine]):
        """注册自定义隔离引擎"""
        self.engine_classes[level] = engine_class

        # 如果配置存在，立即初始化
        if level in self.config:
            try:
                engine_config = self.config.get(level, {})
                engine = engine_class(engine_config)
                self.engines[level] = engine
                self.logger.info(
                    f"Registered and initialized custom isolation engine: {level}"
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to initialize custom isolation engine {level}: {e}"
                )

    def create_environment(
        self, path: Path, isolation_level: str = None, env_config: Dict[str, Any] = None
    ) -> IsolatedEnvironment:
        """创建隔离环境"""

        # 使用默认隔离级别
        if isolation_level is None:
            isolation_level = self.default_isolation_level

        # 检查隔离级别是否支持
        if isolation_level not in self.engines:
            raise ValueError(
                f"Unsupported isolation level: {isolation_level}. "
                f"Supported levels: {list(self.engines.keys())}"
            )

        # 检查环境数量限制
        if len(self.active_environments) >= self.max_environments:
            raise RuntimeError(
                f"Maximum number of environments ({self.max_environments}) reached"
            )

        # 生成环境ID
        env_id = self._generate_env_id()

        # 确保路径存在
        path.mkdir(parents=True, exist_ok=True)

        # 获取隔离引擎
        engine = self.engines[isolation_level]

        # 合并配置
        isolation_config = env_config or {}
        isolation_config.update(self.config.get(isolation_level, {}))

        try:
            # 创建隔离环境
            env = engine.create_isolation(path, env_id, isolation_config)

            # 注册到管理器
            self.active_environments[env_id] = env
            engine.created_environments[env_id] = env

            self.logger.info(
                f"Created isolated environment: {env_id} ({isolation_level})"
            )
            return env

        except Exception as e:
            self.logger.error(f"Failed to create isolated environment {env_id}: {e}")
            raise

    def get_environment(self, env_id: str) -> Optional[IsolatedEnvironment]:
        """获取环境"""
        return self.active_environments.get(env_id)

    def cleanup_environment(self, env_id: str, force: bool = False) -> bool:
        """清理环境"""
        if env_id not in self.active_environments:
            self.logger.warning(f"Environment {env_id} not found for cleanup")
            return False

        env = self.active_environments[env_id]
        engine = env.isolation_engine

        try:
            # 清理环境
            success = engine.cleanup_isolation(env)

            if success or force:
                # 从注册表中移除
                del self.active_environments[env_id]
                if env_id in engine.created_environments:
                    del engine.created_environments[env_id]

                self.logger.info(f"Cleaned up environment: {env_id}")
                return True
            else:
                self.logger.warning(f"Failed to cleanup environment: {env_id}")
                return False

        except Exception as e:
            self.logger.error(f"Error during cleanup of environment {env_id}: {e}")
            if force:
                # 强制清理
                del self.active_environments[env_id]
                if env_id in engine.created_environments:
                    del engine.created_environments[env_id]
                return True
            return False

    def cleanup_all_environments(self, force: bool = False) -> int:
        """清理所有环境"""
        cleaned_count = 0

        for env_id in list(self.active_environments.keys()):
            if self.cleanup_environment(env_id, force):
                cleaned_count += 1

        self.logger.info(f"Cleaned up {cleaned_count} environments")
        return cleaned_count

    def get_environment_status(self, env_id: str) -> Dict[str, Any]:
        """获取环境状态"""
        if env_id not in self.active_environments:
            return {"status": "not_found"}

        env = self.active_environments[env_id]
        engine = env.isolation_engine

        if hasattr(engine, "get_isolation_status"):
            return engine.get_isolation_status(env_id)
        else:
            return env.get_status()

    def list_environments(self) -> Dict[str, Dict[str, Any]]:
        """列出所有环境"""
        status_dict = {}

        for env_id, env in self.active_environments.items():
            status_dict[env_id] = self.get_environment_status(env_id)

        return status_dict

    def validate_environment(self, env_id: str) -> bool:
        """验证环境"""
        if env_id not in self.active_environments:
            return False

        env = self.active_environments[env_id]
        engine = env.isolation_engine

        if hasattr(engine, "validate_isolation"):
            return engine.validate_isolation(env)
        else:
            return True  # 基础隔离始终视为有效

    def get_engine_info(self, isolation_level: str) -> Dict[str, Any]:
        """获取引擎信息"""
        if isolation_level not in self.engines:
            return {"error": f"Engine {isolation_level} not found"}

        engine = self.engines[isolation_level]
        return engine.get_engine_info()

    def list_available_engines(self) -> Dict[str, Dict[str, Any]]:
        """列出可用的隔离引擎"""
        engine_info = {}

        for level, engine in self.engines.items():
            engine_info[level] = {
                "name": engine.engine_name,
                "supported_features": engine.get_supported_features(),
                "environment_count": len(engine.created_environments),
            }

        return engine_info

    def get_manager_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        return {
            "total_environments": len(self.active_environments),
            "max_environments": self.max_environments,
            "available_engines": list(self.engines.keys()),
            "default_isolation_level": self.default_isolation_level,
            "cleanup_policy": self.cleanup_policy,
            "config": self.config,
            "environments_by_engine": self._get_environments_by_engine(),
        }

    def _get_environments_by_engine(self) -> Dict[str, int]:
        """按引擎统计环境数量"""
        count_by_engine = {}

        for env in self.active_environments.values():
            engine_name = env.isolation_engine.engine_name
            count_by_engine[engine_name] = count_by_engine.get(engine_name, 0) + 1

        return count_by_engine

    def _generate_env_id(self) -> str:
        """生成环境ID"""
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        return f"env_{timestamp}_{unique_id}"

    def set_default_isolation_level(self, level: str):
        """设置默认隔离级别"""
        if level not in self.engines:
            raise ValueError(f"Unsupported isolation level: {level}")

        self.default_isolation_level = level
        self.logger.info(f"Set default isolation level to: {level}")

    def update_config(self, new_config: Dict[str, Any]):
        """更新配置"""
        self.config.update(new_config)

        # 重新初始化受影响的引擎
        for level in new_config:
            if level in self.engine_classes and level in new_config:
                try:
                    engine_class = self.engine_classes[level]
                    engine_config = new_config[level]
                    engine = engine_class(engine_config)
                    self.engines[level] = engine
                    self.logger.info(f"Reinitialized isolation engine: {level}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to reinitialize isolation engine {level}: {e}"
                    )

    def find_environments_by_path(self, path: Path) -> List[str]:
        """根据路径查找环境"""
        path_str = str(path.resolve())
        found_envs = []

        for env_id, env in self.active_environments.items():
            if str(env.path.resolve()) == path_str:
                found_envs.append(env_id)

        return found_envs

    def get_environment_resource_usage(self, env_id: str) -> Optional[Dict[str, Any]]:
        """获取环境资源使用情况"""
        if env_id not in self.active_environments:
            return None

        env = self.active_environments[env_id]
        env.update_resource_usage()
        return env.resource_usage.to_dict()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        # 清理所有环境
        self.cleanup_all_environments(force=True)
        self.logger.info("IsolationManager context exited, all environments cleaned up")
