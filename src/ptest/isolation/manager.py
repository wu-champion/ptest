"""
隔离管理器

负责管理所有隔离引擎和环境，提供统一的隔离管理接口
使用统一的引擎注册表实现动态加载和插件化架构
"""

import uuid
import time
import threading
from typing import Dict, Any, Optional, List, Type, Union
from pathlib import Path

from .base import IsolationEngine, IsolatedEnvironment
from .enums import IsolationLevel, EnvironmentStatus, IsolationEvent
from ..core import get_logger
from .registry import get_engine_registry

# 使用框架的日志管理器
logger = get_logger("isolation_manager")


class IsolationManager:
    """隔离管理器

    使用统一的引擎注册表管理所有隔离引擎
    支持动态加载、依赖管理和插件化架构
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.engines: Dict[str, IsolationEngine] = {}
        self.active_environments: Dict[str, IsolatedEnvironment] = {}
        self.engine_classes: Dict[str, Type[IsolationEngine]] = {}
        self.snapshots: Dict[str, Dict[str, Any]] = {}  # 存储快照
        self.default_isolation_level = self.config.get(
            "default_isolation_level", IsolationLevel.BASIC.value
        )
        self.max_environments = self.config.get("max_environments", 100)
        self.cleanup_policy = self.config.get("cleanup_policy", "on_request")
        # 使用已有的logger，避免重复创建
        self.logger = logger

        # 使用统一的引擎注册表
        self.registry = get_engine_registry()

        # 初始化内置引擎
        self._initialize_engines()

    def _initialize_engines(self):
        """初始化隔离引擎"""
        # 通过注册表获取可用引擎
        engines_info = self.registry.list_engines()

        for engine_name in engines_info:
            try:
                engine_config = self.config.get(engine_name, {})
                engine = self.registry.create_engine(engine_name, engine_config)

                if engine:
                    self.engines[engine_name] = engine
                    self.logger.info(f"Initialized isolation engine: {engine_name}")
                else:
                    self.logger.error(
                        f"Failed to create isolation engine: {engine_name}"
                    )

            except Exception as e:
                self.logger.error(
                    f"Failed to initialize isolation engine {engine_name}: {e}"
                )

    def register_engine(
        self, level: str, engine_class: Type[IsolationEngine], **kwargs
    ):
        """注册自定义隔离引擎"""
        # 通过注册表注册引擎
        success = self.registry.register_engine(
            name=level, engine_class=engine_class, **kwargs
        )

        if success:
            # 如果配置存在，立即初始化
            if level in self.config:
                try:
                    engine_config = self.config.get(level, {})
                    engine = self.registry.create_engine(level, engine_config)

                    if engine:
                        self.engines[level] = engine
                        self.logger.info(
                            f"Registered and initialized custom isolation engine: {level}"
                        )
                    else:
                        self.logger.error(
                            f"Failed to create custom isolation engine: {level}"
                        )

                except Exception as e:
                    self.logger.error(
                        f"Failed to initialize custom isolation engine {level}: {e}"
                    )

        return success

    def create_environment(
        self, path: Path, isolation_level: str = None, env_config: Dict[str, Any] = None
    ) -> IsolatedEnvironment:
        """创建隔离环境"""

        # 使用默认隔离级别
        if isolation_level is None:
            isolation_level = self.default_isolation_level

        # 检查隔离级别是否支持
        if isolation_level not in self.engines:
            # 尝试通过注册表创建引擎
            engine = self.registry.create_engine(
                isolation_level, self.config.get(isolation_level, {})
            )
            if engine:
                self.engines[isolation_level] = engine
                self.logger.info(f"Created engine on-demand: {isolation_level}")
            else:
                available_engines = list(self.registry.list_engines().keys())
                raise ValueError(
                    f"Unsupported isolation level: {isolation_level}. "
                    f"Supported levels: {available_engines}"
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

            # 更新引擎的创建环境列表
            if not hasattr(engine, "created_environments"):
                engine.created_environments = {}
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
        # 使用注册表获取引擎信息
        return self.registry.list_engines(include_instances=True)

    def get_engine_info(self, isolation_level: str) -> Dict[str, Any]:
        """获取引擎信息"""
        # 使用注册表获取引擎信息
        engine_info = self.registry.get_engine_info(isolation_level)

        if not engine_info:
            return {"error": f"Engine {isolation_level} not found"}

        # 将EngineInfo对象转换为字典并添加实例信息
        result = {
            "name": engine_info.name,
            "description": engine_info.description,
            "version": engine_info.version,
            "author": engine_info.author,
            "supported_features": engine_info.supported_features,
            "dependencies": engine_info.dependencies,
        }

        if isolation_level in self.engines:
            result["active_instance"] = True
            result["environment_count"] = len(
                self.engines[isolation_level].created_environments
            )
        else:
            result["active_instance"] = False
            result["environment_count"] = 0

        return result

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

    def _get_isolation_level_from_engine(
        self, engine: IsolationEngine
    ) -> Optional[str]:
        for level, eng in self.engines.items():
            if eng == engine:
                return level
        return None

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

    def migrate_environment(
        self,
        env_id: str,
        target_level: str,
        copy_packages: bool = True,
        copy_files: bool = True,
    ) -> IsolatedEnvironment:
        """迁移环境到不同的隔离级别"""
        if env_id not in self.active_environments:
            raise ValueError(f"Environment {env_id} not found")

        source_env = self.active_environments[env_id]
        source_level = None

        # 找到源环境的隔离级别
        for level, engine in self.engines.items():
            if source_env.isolation_engine == engine:
                source_level = level
                break

        if not source_level:
            raise RuntimeError(
                f"Cannot determine isolation level for environment {env_id}"
            )

        if source_level == target_level:
            logger.info(f"Environment {env_id} already at target level {target_level}")
            return source_env

        # 验证目标级别支持
        if target_level not in self.engines:
            raise ValueError(f"Target isolation level {target_level} not supported")

        # 创建新环境
        new_path = source_env.path.parent / f"{env_id}_migrated_{int(time.time())}"
        new_env_id = f"{env_id}_migrated_{uuid.uuid4().hex[:8]}"

        logger.info(
            f"Migrating environment {env_id} from {source_level} to {target_level}"
        )

        try:
            # 创建目标环境
            new_env = self.create_environment(
                new_path,
                target_level,
                {
                    "migrated_from": source_level,
                    "original_env_id": env_id,
                },
            )

            # 如果源环境是Virtualenv，复制包列表
            if (
                copy_packages
                and source_level == "virtualenv"
                and hasattr(source_env, "get_installed_packages")
            ):
                if hasattr(new_env, "install_package"):
                    packages = source_env.get_installed_packages()
                    logger.info(
                        f"Copying {len(packages)} packages to migrated environment"
                    )

                    for package, version in packages.items():
                        try:
                            new_env.install_package(f"{package}=={version}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to copy package {package}=={version}: {e}"
                            )

            # 如果需要，复制文件
            if copy_files:
                import shutil

                try:
                    # 复制重要文件
                    important_files = [
                        "requirements.txt",
                        "setup.py",
                        "pyproject.toml",
                        "Pipfile",
                        "environment.yml",
                    ]

                    for file_name in important_files:
                        source_file = source_env.path / file_name
                        if source_file.exists():
                            target_file = new_env.path / file_name
                            shutil.copy2(source_file, target_file)
                            logger.info(f"Copied {file_name} to migrated environment")

                except Exception as e:
                    logger.warning(f"Failed to copy files: {e}")

            # 清理源环境
            if self.cleanup_environment(env_id, force=False):
                logger.info(f"Cleaned up source environment {env_id}")

            logger.info(f"Successfully migrated environment {env_id} to {target_level}")
            return new_env

        except Exception as e:
            logger.error(f"Failed to migrate environment {env_id}: {e}")
            # 清理失败的迁移
            try:
                self.cleanup_environment(new_env_id, force=True)
            except:
                pass
            raise

    def auto_select_isolation_level(self, requirements: Dict[str, Any]) -> str:
        """根据需求自动选择隔离级别"""

        # 解析需求
        needs_container = requirements.get("container_required", False)
        needs_network_isolation = requirements.get("network_isolation", False)
        needs_custom_image = requirements.get("custom_image", False)
        requires_docker = requirements.get("docker_required", False)
        needs_venv = requirements.get("python_isolation", False)
        resource_limits = requirements.get("resource_limits", {})

        # 安全级别要求
        security_level = requirements.get("security_level", "medium").lower()

        # 资源限制优先检查 - 如果有资源限制需求，优先使用Docker
        if resource_limits.get("memory") or resource_limits.get("cpu"):
            return IsolationLevel.DOCKER.value

        # 决策逻辑
        if requires_docker or needs_container or needs_custom_image:
            return IsolationLevel.DOCKER.value

        if needs_network_isolation or security_level == "high":
            return IsolationLevel.DOCKER.value

        if needs_venv or security_level == "medium":
            return IsolationLevel.VIRTUALENV.value

        # 默认使用Virtualenv
        return IsolationLevel.VIRTUALENV.value

    def create_environment_with_auto_selection(
        self,
        path: Path,
        requirements: Dict[str, Any] = None,
        env_config: Dict[str, Any] = None,
    ) -> IsolatedEnvironment:
        """创建环境并自动选择隔离级别"""

        requirements = requirements or {}

        # 自动选择隔离级别
        isolation_level = self.auto_select_isolation_level(requirements)

        # 将需求转换为环境配置
        final_env_config = env_config or {}
        final_env_config.update(
            {
                "auto_selected_level": isolation_level,
                "selection_requirements": requirements,
            }
        )

        # 添加特定级别的配置
        if "custom_image" in requirements:
            final_env_config["image"] = requirements["custom_image"]

        if "resource_limits" in requirements:
            final_env_config["resource_limits"] = requirements["resource_limits"]

        logger.info(
            f"Auto-selected isolation level: {isolation_level} for requirements: {requirements}"
        )

        # 创建环境
        return self.create_environment(path, isolation_level, final_env_config)

    def get_environment_recommendations(self, env_id: str) -> Dict[str, Any]:
        """获取环境优化建议"""
        if env_id not in self.active_environments:
            return {"error": "Environment not found"}

        env = self.active_environments[env_id]
        recommendations = {
            "current_level": None,
            "suggested_levels": [],
            "optimization_tips": [],
            "migration_options": [],
        }

        # 确定当前级别
        for level, engine in self.engines.items():
            if env.isolation_engine == engine:
                recommendations["current_level"] = level
                break

        # 基于当前状态提供建议
        current_level = recommendations["current_level"]

        if current_level == "basic":
            recommendations["suggested_levels"] = ["virtualenv", "docker"]
            recommendations["optimization_tips"] = [
                "Consider upgrading to virtualenv for better Python package isolation",
                "Use Docker for complete OS-level isolation if needed",
            ]
            recommendations["migration_options"] = ["virtualenv", "docker"]

        elif current_level == "virtualenv":
            recommendations["suggested_levels"] = ["docker"]
            recommendations["optimization_tips"] = [
                "Current level provides good Python isolation",
                "Upgrade to Docker for network isolation and custom images",
                "Consider resource limits for better control",
            ]
            recommendations["migration_options"] = ["docker"]

        elif current_level == "docker":
            recommendations["suggested_levels"] = []
            recommendations["optimization_tips"] = [
                "Already using the highest isolation level",
                "Consider optimizing resource usage",
                "Review container configuration for efficiency",
            ]
            recommendations["migration_options"] = []

        # 添加性能建议
        if hasattr(env, "resource_usage"):
            usage = env.resource_usage.to_dict()
            if usage.get("cpu_percent", 0) > 80:
                recommendations["optimization_tips"].append(
                    "High CPU usage detected, consider resource limits"
                )

            if usage.get("memory_mb", 0) > 500:
                recommendations["optimization_tips"].append(
                    "High memory usage, consider optimization"
                )

        return recommendations

    def benchmark_engines(
        self, test_scenarios: List[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """基准测试所有隔离引擎"""
        import tempfile

        test_scenarios = test_scenarios or [
            "creation",
            "activation",
            "package_install",
            "command_exec",
        ]
        results = {}

        for level, engine in self.engines.items():
            logger.info(f"Benchmarking isolation engine: {level}")

            results[level] = {
                "engine_name": engine.engine_name,
                "supported_features": engine.get_supported_features(),
                "benchmarks": {},
            }

            # 创建测试目录
            test_dir = Path(tempfile.mkdtemp())

            try:
                # 测试环境创建时间
                if "creation" in test_scenarios:
                    start_time = time.time()
                    env = self.create_environment(test_dir, level, {"benchmark": True})
                    creation_time = time.time() - start_time
                    results[level]["benchmarks"]["creation_time"] = creation_time

                    # 测试环境激活时间
                    if "activation" in test_scenarios and hasattr(env, "activate"):
                        start_time = time.time()
                        activation_success = env.activate()
                        activation_time = time.time() - start_time
                        results[level]["benchmarks"]["activation_time"] = (
                            activation_time
                        )
                        results[level]["benchmarks"]["activation_success"] = (
                            activation_success
                        )

                    # 测试包安装时间
                    if "package_install" in test_scenarios and hasattr(
                        env, "install_package"
                    ):
                        start_time = time.time()
                        install_success = env.install_package("requests==2.28.1")
                        install_time = time.time() - start_time
                        results[level]["benchmarks"]["package_install_time"] = (
                            install_time
                        )
                        results[level]["benchmarks"]["package_install_success"] = (
                            install_success
                        )

                    # 测试命令执行时间
                    if "command_exec" in test_scenarios and hasattr(
                        env, "execute_command"
                    ):
                        if env.status == EnvironmentStatus.ACTIVE:
                            start_time = time.time()
                            result = env.execute_command(["python", "--version"])
                            exec_time = time.time() - start_time
                            results[level]["benchmarks"]["command_exec_time"] = (
                                exec_time
                            )
                            results[level]["benchmarks"]["command_exec_success"] = (
                                result.returncode == 0
                            )

                    # 清理测试环境
                    self.cleanup_environment(env.env_id)

            except Exception as e:
                logger.error(f"Benchmark failed for {level}: {e}")
                results[level]["benchmarks"]["error"] = str(e)

            finally:
                # 清理测试目录
                import shutil

                shutil.rmtree(test_dir, ignore_errors=True)

        return results

    def get_engine_compatibility_matrix(self) -> Dict[str, Dict[str, Any]]:
        """获取引擎兼容性矩阵"""
        matrix = {}

        for level, engine in self.engines.items():
            matrix[level] = {
                "name": engine.engine_name,
                "features": engine.get_supported_features(),
                "can_migrate_from": [],
                "can_migrate_to": [],
                "resource_requirements": {
                    "memory": "low"
                    if level == "basic"
                    else ("medium" if level == "virtualenv" else "high"),
                    "disk": "low"
                    if level == "basic"
                    else ("medium" if level == "virtualenv" else "high"),
                    "cpu": "low" if level in ["basic", "virtualenv"] else "medium",
                },
                "isolation_strength": {
                    "filesystem": "none"
                    if level == "basic"
                    else ("partial" if level == "virtualenv" else "complete"),
                    "network": "none"
                    if level in ["basic", "virtualenv"]
                    else "complete",
                    "process": "none"
                    if level == "basic"
                    else ("partial" if level == "virtualenv" else "complete"),
                    "package": "none" if level == "basic" else "complete",
                },
            }

        # 设置迁移兼容性
        if "basic" in matrix:
            matrix["basic"]["can_migrate_to"] = ["virtualenv", "docker"]
        if "virtualenv" in matrix:
            matrix["virtualenv"]["can_migrate_from"] = ["basic"]
            matrix["virtualenv"]["can_migrate_to"] = ["docker"]
        if "docker" in matrix:
            matrix["docker"]["can_migrate_from"] = ["basic", "virtualenv"]

        return matrix

    # 快照管理功能
    def create_snapshot(self, env_id: str, snapshot_id: str = None) -> Dict[str, Any]:
        """创建环境快照"""
        if env_id not in self.active_environments:
            raise ValueError(f"Environment {env_id} not found")

        env = self.active_environments[env_id]

        try:
            # 触发快照创建事件
            self.logger.info(f"Creating snapshot for environment {env_id}")

            # 调用环境的快照方法
            snapshot = env.create_snapshot(snapshot_id)

            # 存储快照
            self.snapshots[snapshot["snapshot_id"]] = snapshot

            self.logger.info(
                f"Successfully created snapshot {snapshot['snapshot_id']} for environment {env_id}"
            )
            return snapshot

        except Exception as e:
            self.logger.error(
                f"Failed to create snapshot for environment {env_id}: {e}"
            )
            raise

    def restore_from_snapshot(self, snapshot_id: str) -> IsolatedEnvironment:
        """从快照恢复环境"""
        if snapshot_id not in self.snapshots:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        snapshot = self.snapshots[snapshot_id]
        env_id = snapshot.get("env_id")
        isolation_level = snapshot.get("isolation_level", "virtualenv")

        try:
            self.logger.info(
                f"Restoring environment {env_id} from snapshot {snapshot_id}"
            )

            # 如果原环境存在，先清理
            if env_id in self.active_environments:
                self.cleanup_environment(env_id, force=True)

            # 创建新环境路径
            original_path = Path(snapshot["path"])
            new_path = original_path.parent / f"{env_id}_restored_{int(time.time())}"
            new_path.mkdir(parents=True, exist_ok=True)

            # 创建新环境
            restored_env = self.create_environment(
                new_path, isolation_level, snapshot.get("config", {})
            )

            # 恢复快照
            if restored_env.restore_from_snapshot(snapshot):
                # 更新快照记录
                self.snapshots[snapshot_id]["restored_at"] = time.time()
                self.snapshots[snapshot_id]["restored_env_id"] = restored_env.env_id

                self.logger.info(
                    f"Successfully restored environment {restored_env.env_id} from snapshot {snapshot_id}"
                )
                return restored_env
            else:
                self.logger.error(
                    f"Failed to restore environment from snapshot {snapshot_id}"
                )
                raise RuntimeError(f"Snapshot restore failed for {snapshot_id}")

        except Exception as e:
            self.logger.error(f"Failed to restore from snapshot {snapshot_id}: {e}")
            raise

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照"""
        if snapshot_id not in self.snapshots:
            self.logger.warning(f"Snapshot {snapshot_id} not found for deletion")
            return False

        try:
            self.logger.info(f"Deleting snapshot {snapshot_id}")

            snapshot = self.snapshots[snapshot_id]
            env_id = snapshot.get("env_id")

            # 调用环境的删除快照方法
            if env_id and env_id in self.active_environments:
                env = self.active_environments[env_id]
                env.delete_snapshot(snapshot_id)

            # 从存储中删除
            del self.snapshots[snapshot_id]

            self.logger.info(f"Successfully deleted snapshot {snapshot_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False

    def list_snapshots(self, env_id: str = None) -> List[Dict[str, Any]]:
        """列出快照"""
        snapshots = list(self.snapshots.values())

        if env_id:
            snapshots = [s for s in snapshots if s.get("env_id") == env_id]

        # 按创建时间排序
        snapshots.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return snapshots

    def get_snapshot_info(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """获取快照信息"""
        return self.snapshots.get(snapshot_id)

    def export_snapshot(self, snapshot_id: str, export_path: Path) -> bool:
        """导出快照到文件"""
        if snapshot_id not in self.snapshots:
            self.logger.error(f"Snapshot {snapshot_id} not found for export")
            return False

        try:
            import json
            from datetime import datetime

            snapshot = self.snapshots[snapshot_id]

            # 添加导出信息
            export_data = snapshot.copy()
            export_data["exported_at"] = datetime.now().isoformat()
            export_data["exported_by"] = "IsolationManager"

            # 写入文件
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            self.logger.info(
                f"Successfully exported snapshot {snapshot_id} to {export_path}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to export snapshot {snapshot_id}: {e}")
            return False

    def import_snapshot(self, import_path: Path) -> Dict[str, Any]:
        """从文件导入快照"""
        try:
            import json

            self.logger.info(f"Importing snapshot from {import_path}")

            # 读取文件
            with open(import_path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)

            # 验证快照格式
            required_fields = ["snapshot_id", "env_id", "path", "created_at"]
            for field in required_fields:
                if field not in snapshot:
                    raise ValueError(f"Invalid snapshot format: missing {field}")

            # 检查是否已存在
            snapshot_id = snapshot["snapshot_id"]
            if snapshot_id in self.snapshots:
                raise ValueError(f"Snapshot {snapshot_id} already exists")

            # 存储快照
            self.snapshots[snapshot_id] = snapshot

            self.logger.info(
                f"Successfully imported snapshot {snapshot_id} from {import_path}"
            )
            return snapshot

        except Exception as e:
            self.logger.error(f"Failed to import snapshot from {import_path}: {e}")
            raise

    def cleanup_old_snapshots(self, days_old: int = 30) -> int:
        """清理旧快照"""
        import time
        from datetime import datetime, timedelta

        cutoff_time = datetime.now() - timedelta(days=days_old)
        cutoff_timestamp = cutoff_time.timestamp()

        old_snapshots = []

        for snapshot_id, snapshot in list(self.snapshots.items()):
            created_at = snapshot.get("created_at")
            if created_at:
                try:
                    created_time = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                    if created_time.timestamp() < cutoff_timestamp:
                        old_snapshots.append(snapshot_id)
                except:
                    pass

        # 删除旧快照
        deleted_count = 0
        for snapshot_id in old_snapshots:
            if self.delete_snapshot(snapshot_id):
                deleted_count += 1

        self.logger.info(
            f"Cleaned up {deleted_count} old snapshots (older than {days_old} days)"
        )
        return deleted_count

    # ========== P2级批量操作方法 (FRAMEWORK-001) ==========

    def create_environments_bulk(
        self,
        env_configs: List[Dict[str, Any]],
        path_template: str = "{env_id}",
        isolation_level: Optional[str] = None,
    ) -> Dict[str, IsolatedEnvironment]:
        """批量创建环境

        Args:
            env_configs: 环境配置列表
            path_template: 路径模板，支持{env_id}占位符
            isolation_level: 可选，指定隔离级别

        Returns:
            创建的环境字典 {env_id: environment}
        """
        from datetime import datetime

        environments = {}
        start_time = datetime.now()
        self.logger.info(f"Starting bulk creation of {len(env_configs)} environments")

        for i, config in enumerate(env_configs, 1):
            env_id = config.get("env_id", f"env_{uuid.uuid4().hex[:8]}")
            path = Path(path_template.format(env_id=env_id))

            try:
                if isolation_level:
                    env = self.create_environment(path, isolation_level, config)
                else:
                    env = self.create_environment(
                        path, config.get("isolation_level"), config
                    )
                environments[env_id] = env
                self.logger.info(
                    f"[{i}/{len(env_configs)}] Created environment {env_id}"
                )
            except Exception as e:
                self.logger.error(f"Failed to create environment {env_id}: {e}")
                # 继续创建其他环境，不中断整个批量操作

        elapsed = (datetime.now() - start_time).total_seconds()
        self.logger.info(
            f"Bulk creation completed: {len(environments)}/{len(env_configs)} "
            f"environments created in {elapsed:.2f}s"
        )

        return environments

    def cleanup_environments_bulk(
        self, env_ids: Optional[List[str]] = None, force: bool = False
    ) -> Dict[str, bool]:
        """批量清理环境

        Args:
            env_ids: 环境ID列表，如果为None则清理所有环境
            force: 是否强制清理

        Returns:
            清理结果 {env_id: success}
        """
        from datetime import datetime

        # 如果没有指定env_ids，则清理所有环境
        if env_ids is None:
            env_ids = list(self.active_environments.keys())

        if not env_ids:
            self.logger.warning("No environments to cleanup")
            return {}

        results = {}
        start_time = datetime.now()
        self.logger.info(f"Starting bulk cleanup of {len(env_ids)} environments")

        for i, env_id in enumerate(env_ids, 1):
            env = self.active_environments.get(env_id)
            if env:
                try:
                    success = self.cleanup_environment(env_id, force=force)
                    results[env_id] = success
                    status = "✓" if success else "✗"
                    self.logger.info(
                        f"[{i}/{len(env_ids)}] Cleaned environment {env_id}: {status}"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to cleanup environment {env_id}: {e}")
                    results[env_id] = False
            else:
                self.logger.warning(f"Environment {env_id} not found")
                results[env_id] = False

        elapsed = (datetime.now() - start_time).total_seconds()
        success_count = sum(1 for success in results.values() if success)
        self.logger.info(
            f"Bulk cleanup completed: {success_count}/{len(env_ids)} "
            f"environments cleaned in {elapsed:.2f}s"
        )

        return results

    def check_environments_health(
        self, env_ids: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """检查所有环境的健康状态

        Args:
            env_ids: 环境ID列表，如果为None则检查所有环境

        Returns:
            {env_id: {
                "status": "healthy" | "unhealthy" | "unknown",
                "last_check": ISO timestamp,
                "details": Dict[str, Any]
            }}
        """
        from datetime import datetime

        # 如果没有指定env_ids，则检查所有环境
        if env_ids is None:
            env_ids = list(self.active_environments.keys())

        if not env_ids:
            self.logger.warning("No environments to check health")
            return {}

        health_status = {}
        self.logger.info(f"Starting health check for {len(env_ids)} environments")

        for env_id in env_ids:
            env = self.active_environments.get(env_id)
            if env:
                try:
                    # 基础健康检查：环境路径是否存在
                    path_exists = env.path.exists()

                    # 特定引擎的健康检查
                    engine_health = env.isolation_engine.check_environment_health(env)

                    status = "healthy" if path_exists and engine_health else "unhealthy"

                    health_status[env_id] = {
                        "status": status,
                        "last_check": datetime.now().isoformat(),
                        "details": {
                            "path_exists": path_exists,
                            "engine_healthy": engine_health,
                            "env_type": env.__class__.__name__,
                            "isolation_level": self._get_isolation_level_from_engine(
                                env.isolation_engine
                            )
                            or "unknown",
                        },
                    }
                except Exception as e:
                    health_status[env_id] = {
                        "status": "unhealthy",
                        "last_check": datetime.now().isoformat(),
                        "details": {"error": str(e), "error_type": type(e).__name__},
                    }
            else:
                health_status[env_id] = {
                    "status": "unknown",
                    "last_check": datetime.now().isoformat(),
                    "details": {"error": f"Environment {env_id} not found"},
                }

        # 统计结果
        healthy_count = sum(
            1 for status in health_status.values() if status.get("status") == "healthy"
        )

        self.logger.info(
            f"Health check completed: {healthy_count}/{len(env_ids)} healthy"
        )

        return health_status

    def collect_environment_metrics(
        self, env_ids: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """收集环境指标

        Args:
            env_ids: 环境ID列表，如果为None则收集所有环境

        Returns:
            {env_id: {
                "resource_usage": {...},
                "performance": {...},
                "status": {...}
            }}
        """
        from datetime import datetime

        # 如果没有指定env_ids，则收集所有环境
        if env_ids is None:
            env_ids = list(self.active_environments.keys())

        if not env_ids:
            self.logger.warning("No environments to collect metrics")
            return {}

        metrics = {}
        self.logger.info(f"Starting metrics collection for {len(env_ids)} environments")

        for env_id in env_ids:
            env = self.active_environments.get(env_id)
            if env:
                try:
                    # 基础指标：磁盘使用
                    disk_usage = 0
                    if env.path.exists():
                        disk_usage = sum(
                            f.stat().st_size for f in env.path.rglob("*") if f.is_file()
                        )

                    # 引擎特定指标
                    engine_metrics = env.isolation_engine.get_environment_metrics(env)

                    metrics[env_id] = {
                        "resource_usage": {
                            "disk_bytes": disk_usage,
                            "disk_mb": disk_usage / (1024 * 1024),
                            "disk_gb": disk_usage / (1024 * 1024 * 1024),
                        },
                        "performance": engine_metrics.get("performance", {}),
                        "status": {
                            "state": env.status.value,
                            "env_type": env.__class__.__name__,
                            "isolation_level": self._get_isolation_level_from_engine(
                                env.isolation_engine
                            )
                            or "unknown",
                            "collected_at": datetime.now().isoformat(),
                        },
                    }
                except Exception as e:
                    metrics[env_id] = {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "collection_failed": True,
                        "collected_at": datetime.now().isoformat(),
                    }
            else:
                metrics[env_id] = {
                    "error": f"Environment {env_id} not found",
                    "collection_failed": True,
                    "collected_at": datetime.now().isoformat(),
                }

        self.logger.info(
            f"Metrics collection completed for {len(metrics)}/{len(env_ids)} environments"
        )

        return metrics
