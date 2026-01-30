"""
Virtualenv隔离引擎实现

提供Python虚拟环境隔离功能，包括虚拟环境创建、激活、包管理等
"""

import os
import sys
import venv
import shutil
import subprocess
import time
import uuid
from typing import Dict, Any, List, Optional, Union, TYPE_CHECKING
from pathlib import Path
import json
from datetime import datetime
import socket
from contextlib import closing

from .base import IsolationEngine, IsolatedEnvironment, ProcessResult
from .enums import EnvironmentStatus, ProcessStatus, IsolationEvent

# 使用框架的日志管理器
from ptest.core import get_logger, execute_command

# 使用框架的日志管理器
logger = get_logger("virtualenv_engine")


class VirtualenvEnvironment(IsolatedEnvironment):
    """Virtualenv隔离环境实现"""

    def __init__(
        self,
        env_id: str,
        path: Path,
        isolation_engine: "VirtualenvIsolationEngine",
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(env_id, path, isolation_engine, config or {})
        self.venv_path = path / "venv"
        self.python_path = self.venv_path / "bin" / "python"
        self.pip_path = self.venv_path / "bin" / "pip"
        self.activate_script = self.venv_path / "bin" / "activate"
        self.status = EnvironmentStatus.CREATED
        self._is_active = False

    def create_virtualenv(self) -> bool:
        """创建虚拟环境"""
        try:
            # 确保父目录存在
            self.path.mkdir(parents=True, exist_ok=True)

            # 获取Python解释器路径
            python_exe = self.config.get("python_path", sys.executable)

            # 创建虚拟环境
            builder = venv.EnvBuilder(
                system_site_packages=self.config.get("system_site_packages", False),
                clear=self.config.get("clear", False),
                symlinks=self.config.get("symlinks", True),
                upgrade=self.config.get("upgrade", False),
                with_pip=True,
            )

            logger.info(f"Creating virtual environment at {self.venv_path}")
            builder.create(str(self.venv_path))

            # 验证创建结果
            if not self.python_path.exists():
                raise RuntimeError(f"Python executable not found at {self.python_path}")

            if not self.pip_path.exists():
                raise RuntimeError(f"Pip executable not found at {self.pip_path}")

            self.status = EnvironmentStatus.CREATED
            self._emit_event(IsolationEvent.ENVIRONMENT_CREATED)
            return True

        except Exception as e:
            logger.error(f"Failed to create virtual environment: {e}")
            self.status = EnvironmentStatus.ERROR
            return False

    def validate_isolation(self) -> bool:
        try:
            if not self.venv_path.exists():
                return False
            if not self.python_path.exists():
                return False
            if not self._is_active:
                return False
            return True
        except Exception as e:
            logger.error(f"Error validating isolation: {e}")
            return False

    def activate(self) -> bool:
        """激活虚拟环境"""
        try:
            # 设置环境变量
            env = os.environ.copy()
            env["PATH"] = f"{self.venv_path / 'bin'}:{env.get('PATH', '')}"
            env["VIRTUAL_ENV"] = str(self.venv_path)
            env["PYTHONPATH"] = ""

            # 验证激活
            result = subprocess.run(
                [str(self.python_path), "-c", "import sys; print(sys.prefix)"],
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )

            if result.returncode == 0 and str(self.venv_path) in result.stdout.strip():
                self._is_active = True
                self.status = EnvironmentStatus.ACTIVE
                self.activated_at = datetime.now()
                self._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATED)
                return True
            else:
                logger.error("Virtual environment activation verification failed")
                return False

        except Exception as e:
            logger.error(f"Failed to activate virtual environment: {e}")
            self.status = EnvironmentStatus.ERROR
            return False

    def deactivate(self) -> bool:
        """停用虚拟环境"""
        self._is_active = False
        self.status = EnvironmentStatus.INACTIVE
        self.deactivated_at = datetime.now()
        self._emit_event(IsolationEvent.ENVIRONMENT_DEACTIVATED)
        return True

    def execute_command(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        env_vars: Optional[Dict[str, str]] = None,
        cwd: Optional[Path] = None,
    ) -> ProcessResult:
        """在虚拟环境中执行命令"""
        start_time = datetime.now()

        try:
            if not self._is_active:
                if not self.activate():
                    return ProcessResult(
                        returncode=1,
                        stderr="Virtual environment not active",
                        command=cmd,
                        start_time=start_time,
                    )

            # 设置环境变量
            env = os.environ.copy()
            env["PATH"] = f"{self.venv_path / 'bin'}:{env.get('PATH', '')}"
            env["VIRTUAL_ENV"] = str(self.venv_path)
            env["PYTHONPATH"] = ""

            # 添加自定义环境变量
            if env_vars:
                env.update(env_vars)

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=cwd or self.path,
                timeout=timeout or self.config.get("command_timeout", 300),
            )

            return ProcessResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                command=cmd,
                timeout=timeout,
                start_time=start_time,
                end_time=datetime.now(),
            )

        except subprocess.TimeoutExpired:
            return ProcessResult(
                returncode=-1,
                stderr=f"Command timed out after {timeout} seconds",
                command=cmd,
                timeout=timeout,
                start_time=start_time,
                end_time=datetime.now(),
            )
        except Exception as e:
            return ProcessResult(
                returncode=1,
                stderr=str(e),
                command=cmd,
                timeout=timeout,
                start_time=start_time,
                end_time=datetime.now(),
            )

    def install_package(
        self, package: str, version: Optional[str] = None, upgrade: bool = False
    ) -> bool:
        """安装Python包"""
        try:
            package_spec = package
            if version:
                package_spec = f"{package}=={version}"

            cmd = [str(self.pip_path), "install"]
            if upgrade:
                cmd.append("--upgrade")
            cmd.append(package_spec)

            # 设置超时
            timeout = self.config.get("pip_timeout", 300)

            result = self.execute_command(cmd, timeout=timeout)

            if result.success:
                logger.info(f"Successfully installed package: {package_spec}")
                self._emit_event(IsolationEvent.PACKAGE_INSTALLED, package=package_spec)
                return True
            else:
                logger.error(
                    f"Failed to install package {package_spec}: {result.stderr}"
                )
                return False

        except Exception as e:
            logger.error(f"Error installing package {package}: {e}")
            return False

    def uninstall_package(self, package: str) -> bool:
        """卸载Python包"""
        try:
            cmd = [str(self.pip_path), "uninstall", "-y", package]

            result = self.execute_command(
                cmd, timeout=self.config.get("pip_timeout", 300)
            )

            if result.success:
                logger.info(f"Successfully uninstalled package: {package}")
                self._emit_event(IsolationEvent.PACKAGE_INSTALLED, package=package)
                return True
            else:
                logger.error(f"Failed to uninstall package {package}: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error uninstalling package {package}: {e}")
            return False

    def get_installed_packages(self) -> Dict[str, str]:
        """获取已安装的包列表"""
        try:
            cmd = [str(self.pip_path), "list", "--format=json"]
            result = self.execute_command(cmd, timeout=30)

            if result.success:
                packages = json.loads(result.stdout)
                return {pkg["name"]: pkg["version"] for pkg in packages}
            else:
                logger.error(f"Failed to get package list: {result.stderr}")
                return {}

        except Exception as e:
            logger.error(f"Error getting package list: {e}")
            return {}

    def get_package_version(self, package: str) -> Optional[str]:
        """获取特定包的版本"""
        packages = self.get_installed_packages()
        return packages.get(package.lower())

    def allocate_port(self) -> int:
        """分配端口"""
        return self._find_free_port()

    def release_port(self, port: int) -> bool:
        """释放端口"""
        if port in self.allocated_ports:
            self.allocated_ports.remove(port)
            return True
        return False

    def _find_free_port(self) -> int:
        """查找可用端口"""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(("", 0))
            s.listen(1)
            port = s.getsockname()[1]
        self.allocated_ports.append(port)
        return port

    def cleanup(self, force: bool = False) -> bool:
        """清理虚拟环境"""
        try:
            # 先停用环境
            if self._is_active:
                self.deactivate()

            # 删除虚拟环境目录
            if self.venv_path.exists():
                shutil.rmtree(str(self.venv_path), ignore_errors=force)

            # 删除整个环境目录（如果为空）
            if force and self.path.exists() and not any(self.path.iterdir()):
                self.path.rmdir()

            self.status = EnvironmentStatus.CLEANUP_COMPLETE
            self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_COMPLETE)
            return True

        except Exception as e:
            logger.error(f"Error cleaning up environment: {e}")
            if not force:
                self.status = EnvironmentStatus.ERROR
                return False
            return True  # 强制清理时即使出错也返回True

    def create_snapshot(self, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        """创建Virtualenv环境快照"""
        try:
            if snapshot_id is None:
                timestamp = int(time.time())
                snapshot_id = f"snapshot_{timestamp}"

            # 获取已安装的包列表
            packages = self.get_installed_packages()

            # 备份自定义脚本（如果有）
            custom_scripts = {}
            scripts_path = self.path / "scripts"
            if scripts_path.exists():
                for script_file in scripts_path.glob("*.py"):
                    with open(script_file, "r") as f:
                        custom_scripts[script_file.name] = f.read()

            return {
                "snapshot_id": snapshot_id,
                "env_id": self.env_id,
                "created_at": datetime.now().isoformat(),
                "env_type": self.__class__.__name__,
                "status": self.status.value,
                "config": self.config,
                "packages": packages,
                "custom_scripts": custom_scripts,
                "venv_path": str(self.venv_path),
            }
        except Exception as e:
            logger.error(f"Failed to create snapshot {snapshot_id}: {e}")
            raise

    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """从快照恢复Virtualenv环境"""
        try:
            logger.info(
                f"Restoring environment {self.env_id} from snapshot {snapshot.get('snapshot_id')}"
            )

            # 重新创建虚拟环境
            if self.venv_path.exists():
                shutil.rmtree(str(self.venv_path))

            builder = venv.EnvBuilder(
                system_site_packages=self.config.get("system_site_packages", False),
                symlinks=True,
                with_pip=True,
            )
            builder.create(str(self.venv_path))

            # 恢复包
            packages = snapshot.get("packages", {})
            for package, version in packages.items():
                version_str = f"=={version}" if version else ""
                self.install_package(package, version)

            # 恢复自定义脚本
            custom_scripts = snapshot.get("custom_scripts", {})
            scripts_path = self.path / "scripts"
            scripts_path.mkdir(parents=True, exist_ok=True)
            for script_name, script_content in custom_scripts.items():
                with open(scripts_path / script_name, "w") as f:
                    f.write(script_content)

            logger.info(
                f"Successfully restored from snapshot {snapshot.get('snapshot_id')}"
            )
            self._emit_event(
                IsolationEvent.SNAPSHOT_RESTORED,
                snapshot_id=snapshot.get("snapshot_id"),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to restore from snapshot: {e}")
            return False

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照（Virtualenv没有持久化快照，此方法为接口兼容）"""
        try:
            logger.info(f"Deleting snapshot {snapshot_id}")
            logger.warning("Virtualenv snapshots are not persisted by default")
            self._emit_event(IsolationEvent.SNAPSHOT_DELETED, snapshot_id=snapshot_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False


class VirtualenvIsolationEngine(IsolationEngine):
    """Virtualenv隔离引擎实现"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.supported_features = [
            "filesystem_isolation",
            "python_package_isolation",
            "process_execution",
            "port_allocation",
        ]

        self.default_config = {
            "python_path": sys.executable,
            "system_site_packages": False,
            "clear": False,
            "symlinks": True,
            "upgrade": False,
        }
        self.engine_config = {**self.default_config, **config}

    def create_isolation(
        self, path: Path, env_id: str, isolation_config: Dict[str, Any]
    ) -> IsolatedEnvironment:
        final_config = {**self.engine_config, **isolation_config}
        env = VirtualenvEnvironment(env_id, path, self, final_config)
        if not env.create_virtualenv():
            raise RuntimeError(f"Virtual environment creation failed for {env_id}")
        self.created_environments[env_id] = env
        logger.info(f"Created virtual environment: {env_id} at {path}")
        return env

    def cleanup_isolation(self, env: IsolatedEnvironment) -> bool:
        if isinstance(env, VirtualenvEnvironment):
            success = env.cleanup(force=True)
            if success and env.env_id in self.created_environments:
                del self.created_environments[env.env_id]
            return success
        else:
            logger.error(f"Invalid environment type for Virtualenv engine: {type(env)}")
            return False

    def get_isolation_status(self, env_id: str) -> Dict[str, Any]:
        if env_id not in self.created_environments:
            return {"status": "not_found", "isolation_type": "virtualenv"}
        env = self.created_environments[env_id]
        status = env.get_status()
        status.update(
            {
                "isolation_type": "virtualenv",
                "supported_features": self.supported_features,
                "engine_config": self.engine_config,
            }
        )
        return status

    def validate_isolation(self, env: IsolatedEnvironment) -> bool:
        if isinstance(env, VirtualenvEnvironment):
            return env.validate_isolation()
        else:
            logger.error(f"Invalid environment type for Virtualenv engine: {type(env)}")
            return False

    def get_supported_features(self) -> List[str]:
        return self.supported_features.copy()

    def get_engine_info(self) -> Dict[str, Any]:
        info = super().get_engine_info()
        info.update(
            {
                "engine_type": "virtualenv",
                "python_version": sys.version,
                "python_executable": sys.executable,
                "engine_config": self.engine_config,
                "venv_module_available": hasattr(venv, "EnvBuilder"),
            }
        )
        return info

    def check_environment_health(self, env: IsolatedEnvironment) -> bool:
        """检查Virtualenv环境健康状态"""
        try:
            if not env.path.exists():
                return False
            return True
        except Exception as e:
            logger.error(f"Error checking environment health: {e}")
            return False

    def get_environment_metrics(self, env: IsolatedEnvironment) -> Dict[str, Any]:
        """获取Virtualenv环境指标"""
        try:
            disk_usage = 0
            if env.path.exists():
                disk_usage = sum(
                    f.stat().st_size for f in env.path.rglob("*") if f.is_file()
                )

            return {
                "performance": {
                    "packages_count": len(env.get_installed_packages()),
                },
                "disk_usage_mb": disk_usage / (1024 * 1024),
            }
        except Exception as e:
            logger.error(f"Error getting environment metrics: {e}")
            return {"performance": {}, "error": str(e)}
