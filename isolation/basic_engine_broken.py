"""
基础隔离引擎

提供最基础的文件系统隔离功能
"""

import shutil
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from .base import IsolationEngine, IsolatedEnvironment, ProcessResult, ProcessInfo
from .enums import EnvironmentStatus, ProcessStatus, IsolationEvent

logger = logging.getLogger(__name__)


class BasicEnvironment(IsolatedEnvironment):
    """基础隔离环境实现"""

    def __init__(
        self,
        env_id: str,
        path: Path,
        isolation_engine: "BasicIsolationEngine",
        config: Dict[str, Any] = None,
    ):
        super().__init__(env_id, path, isolation_engine, config or {})
        self._create_directory_structure()
        self.status = EnvironmentStatus.CREATED

    def _create_directory_structure(self):
        """创建目录结构"""
        dirs = [
            "bin",
            "lib",
            "include",
            "share",
            "logs",
            "temp",
            "data",
            "scripts",
            "objects",
            "tools",
            "cases",
            "reports",
        ]

        for dir_name in dirs:
            dir_path = self.path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

    def activate(self) -> bool:
        """激活环境"""
        try:
            self.status = EnvironmentStatus.ACTIVATING
            self._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATING)

            # 基础环境激活主要是设置一些环境变量
            os.environ[f"PTEST_ENV_{self.env_id}"] = str(self.path)

            self.status = EnvironmentStatus.ACTIVE
            self.activated_at = datetime.now()
            self._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATED)

            logger.info(f"Activated basic environment: {self.env_id}")
            return True

        except Exception as e:
            self.status = EnvironmentStatus.ERROR
            logger.error(f"Failed to activate basic environment {self.env_id}: {e}")
            return False

    def deactivate(self) -> bool:
        """停用环境"""
        try:
            self.status = EnvironmentStatus.DEACTIVATING
            self._emit_event(IsolationEvent.ENVIRONMENT_DEACTIVATING)

            # 清理环境变量
            env_key = f"PTEST_ENV_{self.env_id}"
            if env_key in os.environ:
                del os.environ[env_key]

            self.status = EnvironmentStatus.INACTIVE
            self.deactivated_at = datetime.now()
            self._emit_event(IsolationEvent.ENVIRONMENT_DEACTIVATED)

            logger.info(f"Deactivated basic environment: {self.env_id}")
            return True

        except Exception as e:
            self.status = EnvironmentStatus.ERROR
            logger.error(f"Failed to deactivate basic environment {self.env_id}: {e}")
            return False

    def execute_command(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        env_vars: Dict[str, str] = None,
        cwd: Optional[Path] = None,
    ) -> ProcessResult:
        """在隔离环境中执行命令"""
        import subprocess
        from datetime import datetime

        start_time = datetime.now()
        process_id = f"proc_{int(start_time.timestamp())}"

        try:
            # 准备环境变量
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)

            # 设置工作目录
            work_dir = cwd or self.path

            # 执行命令
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=work_dir,
                timeout=timeout,
            )

            end_time = datetime.now()

            # 创建进程结果
            result = ProcessResult(
                returncode=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                command=cmd,
                timeout=timeout,
                start_time=start_time,
                end_time=end_time,
            )

            # 记录进程信息
            process_info = ProcessInfo(
                process_id=process_id,
                command=cmd,
                status=ProcessStatus.RUNNING
                if process.returncode == 0
                else ProcessStatus.ERROR,
            )
            process_info.mark_completed(
                process.returncode, process.stdout, process.stderr
            )

            self.processes[process_id] = process_info

            return result

        except subprocess.TimeoutExpired:
            end_time = datetime.now()
            return ProcessResult(
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                command=cmd,
                timeout=timeout,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as e:
            end_time = datetime.now()
            return ProcessResult(
                returncode=-1,
                stdout="",
                stderr=str(e),
                command=cmd,
                timeout=timeout,
                start_time=start_time,
                end_time=end_time,
            )

    def install_package(
        self, package: str, version: Optional[str] = None, upgrade: bool = False
    ) -> bool:
        """安装包（基础环境不支持包管理）"""
        logger.warning(
            f"Basic environment does not support package management: {package}"
        )
        return False

    def uninstall_package(self, package: str) -> bool:
        """卸载包（基础环境不支持包管理）"""
        logger.warning(
            f"Basic environment does not support package management: {package}"
        )
        return False

    def get_installed_packages(self) -> Dict[str, str]:
        """获取已安装的包（基础环境返回空）"""
        return {}

    def get_package_version(self, package: str) -> Optional[str]:
        """获取包版本（基础环境返回None）"""
        return None

    def allocate_port(self) -> int:
        """分配端口（基础环境简单实现）"""
        import socket

        # 简单实现：随机选择一个可用端口
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

        self.allocated_ports.append(port)
        logger.info(f"Allocated port {port} for environment {self.env_id}")
        return port

    def release_port(self, port: int) -> bool:
        """释放端口"""
        if port in self.allocated_ports:
            self.allocated_ports.remove(port)
            logger.info(f"Released port {port} for environment {self.env_id}")
            return True
        return False

    def cleanup(self, force: bool = False) -> bool:
        """清理环境"""
        try:
            self.status = EnvironmentStatus.CLEANUP_START
            self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_START)

            # 停用环境
            if self.status == EnvironmentStatus.ACTIVE:
                self.deactivate()

            # 清理进程
            for process_id in list(self.processes.keys()):
                # 基础环境无法真正停止进程，只能清理记录
                del self.processes[process_id]

            # 释放端口
            for port in list(self.allocated_ports):
                self.release_port(port)

            # 删除目录（如果force为True）
            if force and self.path.exists():
                shutil.rmtree(self.path)
                logger.info(f"Deleted directory for environment {self.env_id}")

            self.status = EnvironmentStatus.CLEANUP_COMPLETE
            self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_COMPLETE)

            return True

        except Exception as e:
            self.status = EnvironmentStatus.ERROR
            logger.error(f"Failed to cleanup basic environment {self.env_id}: {e}")
            return False

    def validate_isolation(self) -> bool:
        """验证隔离有效性"""
        # 基础环境验证：检查目录结构
        required_dirs = ["logs", "temp", "data"]
        for dir_name in required_dirs:
            if not (self.path / dir_name).exists():
                return False
        return True


class BasicIsolationEngine(IsolationEngine):
    """基础隔离引擎实现"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.supported_features = [
            "filesystem_isolation",
            "basic_process_execution",
            "port_allocation",
        ]

    def create_isolation(
        self, path: Path, env_id: str, isolation_config: Dict[str, Any]
    ) -> BasicEnvironment:
        """创建基础隔离环境"""

        try:
            # 确保路径存在
            path.mkdir(parents=True, exist_ok=True)

            # 创建环境实例
            env = BasicEnvironment(
                env_id=env_id, path=path, isolation_engine=self, config=isolation_config
            )

            # 注册到引擎
            self.created_environments[env_id] = env

            self.logger.info(f"Created basic isolation environment: {env_id}")
            return env

        except Exception as e:
            self.logger.error(
                f"Failed to create basic isolation environment {env_id}: {e}"
            )
            raise

def cleanup_isolation(self, env: IsolatedEnvironment) -> bool:
        """清理基础隔离环境"""
        try:
            if isinstance(env, BasicEnvironment):
                return env.cleanup(force=True)
            return False
        except Exception as e:
            self.logger.error(f"Failed to cleanup basic isolation environment {env.env_id}: {e}")
            return False

    def get_isolation_status(self, env_id: str) -> Dict[str, Any]:
        """获取隔离状态"""
        if env_id not in self.created_environments:
            return {"status": "not_found"}

        env = self.created_environments[env_id]
        status = env.get_status()
        status.update(
            {"isolation_type": "basic", "supported_features": self.supported_features}
        )
        return status

    def validate_isolation(self, env: IsolatedEnvironment) -> bool:
        """验证隔离有效性"""
        if isinstance(env, BasicEnvironment):
            return env.validate_isolation()
        return False

    def get_supported_features(self) -> List[str]:
        """获取支持的功能列表"""
        return self.supported_features.copy()
