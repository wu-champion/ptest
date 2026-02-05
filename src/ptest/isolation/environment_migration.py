"""
引擎间环境迁移

提供 Virtualenv 到 Docker 和 Docker 到 Virtualenv 的环境迁移功能
"""

from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

from .base import (
    IsolationEngine,
    IsolatedEnvironment,
    EnvironmentSnapshot,
)
from ..core import get_logger

logger = get_logger("environment_migration")


class MigrationProgress:
    """迁移进度追踪"""

    def __init__(self):
        self._current_step = ""
        self._total_steps = 0
        self._completed_steps = 0
        self._start_time = None

    def start(self, total_steps: int):
        """开始迁移"""
        import time

        self._total_steps = total_steps
        self._completed_steps = 0
        self._start_time = time.time()
        logger.info(f"Starting migration with {total_steps} steps")

    def update_step(self, step: str):
        """更新当前步骤"""
        self._current_step = step
        logger.debug(f"Migration step: {step}")

    def complete_step(self):
        """完成一个步骤"""
        self._completed_steps += 1
        progress = (self._completed_steps / self._total_steps) * 100
        logger.info(
            f"Migration progress: {progress:.1f}% ({self._completed_steps}/{self._total_steps})"
        )

    def finish(self, success: bool = True):
        """完成迁移"""
        import time

        elapsed = time.time() - self._start_time if self._start_time else 0
        status = "succeeded" if success else "failed"
        logger.info(f"Migration {status} in {elapsed:.2f}s")
        return elapsed


class EnvironmentMigrator:
    """环境迁移器"""

    def __init__(
        self,
        source_engine: IsolationEngine,
        target_engine: IsolationEngine,
        progress_callback: Optional[Callable[[MigrationProgress], None]] = None,
    ):
        self.source_engine = source_engine
        self.target_engine = target_engine
        self.progress = progress_callback or MigrationProgress()

    def migrate_virtualenv_to_docker(
        self,
        source_env_id: str,
        target_env_id: str,
        include_packages: bool = True,
        include_data: bool = False,
    ) -> Dict[str, Any]:
        """迁移 Virtualenv 环境到 Docker

        Args:
            source_env_id: 源环境ID (Virtualenv)
            target_env_id: 目标环境ID (Docker)
            include_packages: 是否迁移已安装的包
            include_data: 是否迁移数据文件

        Returns:
            迁移结果字典
        """
        self.progress.start(6)

        try:
            self.progress.update_step("获取源环境信息")
            source_env = self.source_engine.environments.get(source_env_id)
            if not source_env:
                raise ValueError(f"Source environment {source_env_id} not found")

            self.progress.complete_step()

            self.progress.update_step("获取已安装的包列表")
            packages_info = {}
            if include_packages:
                result = source_env.isolation_engine.get_installed_packages(source_env)
                packages_info = {
                    "packages": result,
                    "requirements": self._generate_requirements_from_packages(result),
                }

            self.progress.complete_step()

            self.progress.update_step("创建 Docker 环境")
            target_config = {
                "image_name": "python:3.11-slim",
                "python_packages": list(packages_info.get("packages", {}).keys())
                if include_packages
                else [],
            }
            target_env = self.target_engine.create_environment(
                env_id=target_env_id,
                path=Path(f"/tmp/ptest_migrated_{target_env_id}"),
                config=target_config,
            )

            if not target_env:
                raise RuntimeError(f"Failed to create target Docker environment")

            self.progress.complete_step()

            self.progress.update_step("迁移已安装的包")
            if include_packages:
                success = self._migrate_packages(source_env, target_env, packages_info)
                if not success:
                    raise RuntimeError("Failed to migrate packages")

            self.progress.complete_step()

            self.progress.update_step("迁移数据文件")
            if include_data:
                success = self._migrate_data(source_env, target_env)
                if not success:
                    raise RuntimeError("Failed to migrate data files")

            self.progress.complete_step()

            self.progress.update_step("激活目标环境")
            activate_result = target_env.isolation_engine.activate_environment(
                target_env_id
            )
            if not activate_result:
                raise RuntimeError("Failed to activate target environment")

            self.progress.complete_step()

            elapsed = self.progress.finish()

            return {
                "success": True,
                "source_env_id": source_env_id,
                "target_env_id": target_env_id,
                "packages_migrated": len(packages_info.get("packages", {})),
                "data_migrated": include_data,
                "elapsed_time": elapsed,
            }

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.progress.finish(success=False)
            return {
                "success": False,
                "error": str(e),
                "source_env_id": source_env_id,
                "target_env_id": target_env_id,
            }

    def migrate_docker_to_virtualenv(
        self,
        source_env_id: str,
        target_env_id: str,
        include_packages: bool = True,
    ) -> Dict[str, Any]:
        """迁移 Docker 环境到 Virtualenv

        Args:
            source_env_id: 源环境ID (Docker)
            target_env_id: 目标环境ID (Virtualenv)
            include_packages: 是否迁移已安装的包

        Returns:
            迁移结果字典
        """
        self.progress.start(4)

        try:
            self.progress.update_step("获取源环境信息")
            source_env = self.source_engine.environments.get(source_env_id)
            if not source_env:
                raise ValueError(f"Source environment {source_env_id} not found")

            self.progress.complete_step()

            self.progress.update_step("创建 Virtualenv 环境")
            target_config = source_env.config.copy()
            target_env = self.target_engine.create_environment(
                env_id=target_env_id,
                path=Path(f"/tmp/ptest_migrated_{target_env_id}"),
                config=target_config,
            )

            if not target_env:
                raise RuntimeError(f"Failed to create target Virtualenv environment")

            self.progress.complete_step()

            self.progress.update_step("迁移已安装的包")
            packages_info = {}
            if include_packages:
                result = source_env.get_installed_packages()
                packages_info = {
                    "packages": result,
                    "requirements": self._generate_requirements_from_packages(result),
                }

                success = self._migrate_packages(source_env, target_env, packages_info)
                if not success:
                    raise RuntimeError("Failed to migrate packages")

            self.progress.complete_step()

            elapsed = self.progress.finish()

            return {
                "success": True,
                "source_env_id": source_env_id,
                "target_env_id": target_env_id,
                "packages_migrated": len(packages_info.get("packages", {})),
                "elapsed_time": elapsed,
            }

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.progress.finish(success=False)
            return {
                "success": False,
                "error": str(e),
                "source_env_id": source_env_id,
                "target_env_id": target_env_id,
            }

    def _migrate_packages(
        self,
        source_env: IsolatedEnvironment,
        target_env: IsolatedEnvironment,
        packages_info: Dict[str, Any],
    ) -> bool:
        """迁移包"""
        packages = packages_info.get("packages", {})

        for package_name, version in packages.items():
            try:
                logger.debug(f"Installing package: {package_name}=={version}")
                success = target_env.isolation_engine.install_package(
                    target_env,
                    package_name,
                    version=version,
                )
                if not success:
                    logger.warning(f"Failed to install {package_name}")
                    return False
            except Exception as e:
                logger.error(f"Error installing {package_name}: {e}")
                return False

        return True

    def _migrate_data(
        self,
        source_env: IsolatedEnvironment,
        target_env: IsolatedEnvironment,
    ) -> bool:
        """迁移数据文件"""
        try:
            data_files = self._find_data_files(source_env.path)
            if not data_files:
                logger.info("No data files to migrate")
                return True

            for data_file in data_files:
                logger.debug(f"Migrating data file: {data_file}")
                rel_path = data_file.relative_to(source_env.path)

                if not target_env.path.exists():
                    target_env.path.mkdir(parents=True, exist_ok=True)

                target_file = target_env.path / rel_path

                target_file.parent.mkdir(parents=True, exist_ok=True)

                if data_file.is_file():
                    target_file.write_bytes(data_file.read_bytes())
                elif data_file.is_dir():
                    import shutil

                    shutil.copytree(data_file, target_file)

            return True

        except Exception as e:
            logger.error(f"Failed to migrate data: {e}")
            return False

    def _find_data_files(self, env_path: Path) -> List[Path]:
        """查找数据文件"""
        data_files = []
        data_extensions = [".txt", ".json", ".csv", ".yml", ".yaml", ".md"]

        for item in env_path.iterdir():
            if item.is_file() and item.suffix in data_extensions:
                data_files.append(item)
            elif item.is_dir() and item.name not in ["venv", "bin", "lib", "include"]:
                data_files.append(item)

        return data_files

    def _generate_requirements_from_packages(self, packages: Dict[str, str]) -> str:
        """从包列表生成 requirements.txt"""
        lines = []
        for package_name, version in packages.items():
            lines.append(f"{package_name}=={version}")

        return "\n".join(lines)


class SnapshotCrossEngineConverter:
    """快照跨引擎转换器"""

    def __init__(self, source_engine: IsolationEngine, target_engine: IsolationEngine):
        self.source_engine = source_engine
        self.target_engine = target_engine

    def convert_snapshot(
        self,
        source_snapshot: EnvironmentSnapshot,
        target_env_id: str,
    ) -> bool:
        """转换快照到目标引擎

        Args:
            source_snapshot: 源引擎的快照
            target_env_id: 目标环境ID

        Returns:
            是否转换成功
        """
        try:
            logger.info(
                f"Converting snapshot {source_snapshot['snapshot_id']} for target environment"
            )

            target_config = {
                "base_snapshot": source_snapshot,
                "source_engine_type": self.source_engine.engine_type,
            }

            target_env = self.target_engine.create_environment(
                env_id=target_env_id,
                path=Path(f"/tmp/ptest_snapshot_{target_env_id}"),
                config=target_config,
            )

            if not target_env:
                raise RuntimeError("Failed to create target environment")

            logger.info(f"Snapshot converted successfully for {target_env_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to convert snapshot: {e}")
            return False

    def validate_snapshot_compatibility(
        self,
        source_snapshot: EnvironmentSnapshot,
        target_engine_type: str,
    ) -> Dict[str, Any]:
        """验证快照兼容性"""
        compatibility = {
            "compatible": True,
            "warnings": [],
            "errors": [],
        }

        source_packages = source_snapshot.get("packages", {})

        for package_name in source_packages.keys():
            try:
                result = self.target_engine.check_package_compatibility(package_name)
                if not result.get("compatible", True):
                    compatibility["warnings"].append(
                        {
                            "package": package_name,
                            "message": result.get(
                                "message", "May have compatibility issues"
                            ),
                        }
                    )
            except Exception:
                pass

        return compatibility


def migrate_environment(
    source_engine: IsolationEngine,
    target_engine: IsolationEngine,
    source_env_id: str,
    target_env_id: str = None,
    progress_callback: Optional[Callable[[MigrationProgress], None]] = None,
) -> Dict[str, Any]:
    """便捷函数：迁移环境

    Args:
        source_engine: 源引擎
        target_engine: 目标引擎
        source_env_id: 源环境ID
        target_env_id: 目标环境ID（可选，自动生成）
        progress_callback: 进度回调

    Returns:
        迁移结果
    """
    migrator = EnvironmentMigrator(source_engine, target_engine, progress_callback)

    if target_env_id is None:
        target_env_id = f"migrated_{source_env_id}"

    source_type = source_engine.engine_type.lower()
    target_type = target_engine.engine_type.lower()

    if source_type == "virtualenv" and target_type == "docker":
        return migrator.migrate_virtualenv_to_docker(source_env_id, target_env_id)
    elif source_type == "docker" and target_type == "virtualenv":
        return migrator.migrate_docker_to_virtualenv(source_env_id, target_env_id)
    else:
        return {
            "success": False,
            "error": f"Unsupported migration: {source_type} to {target_type}",
            "source_env_id": source_env_id,
            "target_env_id": target_env_id,
        }
