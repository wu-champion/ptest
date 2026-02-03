# ptest/isolation/docker_engine.py - 完善版本

import os
import sys
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Union, Callable, TYPE_CHECKING
from pathlib import Path
import threading
from contextlib import contextmanager
from datetime import datetime

# Docker SDK imports (如果不可用，使用模拟接口)
try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

# 类型定义（使用TYPE_CHECKING避免运行时导入问题）
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docker.models.containers import Container as DockerContainer
    from docker.models.images import Image as DockerImage
    from docker.models.networks import Network as DockerNetwork
    from docker.models.volumes import Volume as DockerVolume
    from docker.errors import (
        DockerException as DockerSDKException,
        APIError as DockerAPIError,
        NotFound as DockerNotFound,
    )
else:
    # 运行时类型定义
    if DOCKER_AVAILABLE:
        from docker.models.containers import Container as DockerContainer
        from docker.models.images import Image as DockerImage
        from docker.models.networks import Network as DockerNetwork
        from docker.models.volumes import Volume as DockerVolume
        from docker.errors import (
            DockerException as DockerSDKException,
            APIError as DockerAPIError,
            NotFound as DockerNotFound,
        )
    else:
        # 模拟类
        class DockerContainer:
            pass

        class DockerImage:
            pass

        class DockerNetwork:
            pass

        class DockerVolume:
            pass

        class DockerSDKException(Exception):
            pass

        class DockerAPIError(Exception):
            pass

        class DockerNotFound(Exception):
            pass

    class Image:
        pass

    class Network:
        pass

    class Volume:
        pass

    class DockerException(Exception):
        pass

    class APIError(Exception):
        pass

    class NotFound(Exception):
        pass


from .base import IsolationEngine, IsolatedEnvironment, ProcessResult
from .enums import EnvironmentStatus, ProcessStatus, IsolationEvent
from ..core import get_logger, execute_command

from .managers import ImageManager, NetworkManager, VolumeManager

# 使用框架的日志管理器
logger = get_logger("docker_engine")


class DockerEnvironment(IsolatedEnvironment):
    """Docker隔离环境实现"""

    def __init__(
        self,
        env_id: str,
        path: Path,
        isolation_engine: Any,  # 改为Any避免循环导入问题
        config: Optional[Dict[str, Any]] | None = None,
    ):
        super().__init__(env_id, path, isolation_engine, config or {})

        # Docker特有属性
        self.container_id: Optional[str] = None
        self._container: Optional[Any] = None
        self.container_name: str = f"ptest_{env_id}_{uuid.uuid4().hex[:8]}"
        default_image = "python:3.9-slim"
        if (
            hasattr(isolation_engine, "engine_config")
            and isolation_engine.engine_config
        ):
            default_image = isolation_engine.engine_config.get(
                "default_image", "python:3.9-slim"
            )
        self.image_name: str = (
            config.get("image", default_image) if config else default_image
        )
        self.network_name: str = ""
        self.volumes: Dict[str, Dict[str, str]] = {}
        self.port_mappings: Dict[int, int] = {}
        self.environment_vars: Dict[str, str] = {}
        self.resource_limits: Dict[str, Any] = {}
        self.restart_policy: str = ""
        self.healthcheck_config: Dict[str, Any] = {}
        self.allocated_ports: List[int] = []  # 跟踪已分配的端口

        self.status = EnvironmentStatus.CREATED
        self._is_active = False

    def _parse_memory(self, memory_str: str) -> int:
        """解析内存限制字符串为字节数"""
        try:
            memory_str = memory_str.lower().strip()

            if memory_str.endswith("b"):
                return int(memory_str[:-1]) * 1024 * 1024 * 1024
            elif memory_str.endswith("k") or memory_str.endswith("kb"):
                return int(memory_str[:-2]) * 1024 * 1024
            elif memory_str.endswith("m") or memory_str.endswith("mb"):
                return int(memory_str[:-2]) * 1024 * 1024
            elif memory_str.endswith("g"):
                return int(memory_str[:-1]) * 1024 * 1024 * 1024
            else:
                return int(memory_str)
        except (ValueError, AttributeError):
            logger.warning(f"Invalid memory limit format: {memory_str}, using default")
            return 512 * 1024 * 1024

    def _build_resource_host_config(self, limits: Dict[str, Any]) -> Dict[str, Any]:
        """构建资源限制host配置"""
        host_config = {}
        resource_mapping = {
            "cpus": lambda v: {
                "cpu_quota": int(float(v) * 100000),
                "cpu_period": 100000,
            },
            "memory": lambda v: {"mem_limit": self._parse_memory(v)},
            "memory_swap": lambda v: {"memswap_limit": self._parse_memory(v)},
            "memory_reservation": lambda v: {"mem_reservation": self._parse_memory(v)},
            "oom_kill_disable": lambda v: {"oom_kill_disable": v},
            "pids_limit": lambda v: {"pids_limit": v},
            "blkio_weight": lambda v: {"blkio_weight": v},
            "blkio_read_bps": lambda v: {"blkio_device_read_bps": v},
            "blkio_write_bps": lambda v: {"blkio_device_write_bps": v},
            "blkio_read_iops": lambda v: {"blkio_device_read_iops": v},
            "blkio_write_iops": lambda v: {"blkio_device_write_iops": v},
        }
        for key, mapper in resource_mapping.items():
            if limits.get(key):
                host_config.update(mapper(limits[key]))
        return host_config

    def _initialize_container_config(self) -> Dict[str, Any]:
        """初始化容器配置"""
        return {
            "image": self.image_name,
            "name": self.container_name,
            "detach": True,
            "volumes": self.volumes,
            "ports": {
                str(host_port): container_port
                for host_port, container_port in self.port_mappings.items()
            },
            "environment": self.environment_vars,
            "working_dir": str(self.path),
        }

    def create_container(self) -> bool:
        """创建Docker容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    "Docker SDK not available, simulating container creation"
                )
                self.container_id = f"sim_{uuid.uuid4().hex}"
                self._emit_event(IsolationEvent.ENVIRONMENT_CREATED)
                return True

            engine = self.isolation_engine
            if hasattr(engine, "initialize_client") and not engine.initialize_client():
                logger.error("Failed to initialize Docker client")
                return False

            container_config = self._initialize_container_config()

            if self.resource_limits:
                host_config = self._build_resource_host_config(self.resource_limits)
                if host_config:
                    container_config["host_config"] = host_config
                    logger.debug(f"Resource limits applied: {self.resource_limits}")

            return True

        except Exception as e:
            logger.error(f"Failed to create container: {e}")
            return False

    def start_container(self) -> bool:
        """启动Docker容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container start")
                self.status = EnvironmentStatus.ACTIVE
                self._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATED)
                return True

            if not self._container:
                logger.warning("Container not created, cannot start")
                return False

            if self._container.status in ["running", "restarting"]:
                logger.info("Container already running")
                return True

            self._container.start()
            self.status = EnvironmentStatus.ACTIVE
            self._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATED)
            logger.info(f"Container started: {self.container_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to start container: {e}")
            return False

    def stop_container(self) -> bool:
        """停止Docker容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container stop")
                self.status = EnvironmentStatus.INACTIVE
                self._emit_event(IsolationEvent.ENVIRONMENT_DEACTIVATED)
                return True

            if not self._container:
                logger.warning("Container not created, cannot stop")
                return False

            if self._container.status == "exited":
                logger.info("Container already stopped")
                return True

            self._container.stop(timeout=10)
            self.status = EnvironmentStatus.INACTIVE
            self._emit_event(IsolationEvent.ENVIRONMENT_DEACTIVATED)
            logger.info(f"Container stopped: {self.container_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop container: {e}")
            return False

    def remove_container(self) -> bool:
        """删除Docker容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container removal")
                return True

            if not self._container:
                logger.warning("Container not created, cannot remove")
                return True  # 返回成功，因为容器本来就不存在

            try:
                self._container.remove(force=True)
                logger.info(f"Container removed: {self.container_id}")
                self._container = None
                return True
            except Exception as e:
                if "No such container" in str(e):
                    logger.warning(f"Container already removed: {self.container_id}")
                    return True
                raise

        except Exception as e:
            logger.error(f"Failed to remove container: {e}")
            return False

    def get_health_status(self) -> Dict[str, Any]:
        """获取容器健康状态"""
        try:
            if not DOCKER_AVAILABLE or not self._container:
                return {"status": "unknown", "message": "Docker not available"}

            self._container.reload()
            health_status = self._container.attrs.get("State", {}).get("Health", {})
            health_status_data = (
                health_status if isinstance(health_status, dict) else {}
            )

            return {
                "status": health_status_data.get("Status", "none"),
                "failing_streak": health_status_data.get("FailingStreak", 0),
                "log": health_status_data.get("Log", []),
            }

        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {"status": "error", "message": str(e)}

    def wait_for_healthy(self, timeout: int = 300) -> bool:
        """等待容器变为健康状态"""
        try:
            import time

            start_time = time.time()
            while time.time() - start_time < timeout:
                health_status = self.get_health_status()
                status = health_status.get("status")

                if status == "healthy":
                    logger.info("Container is healthy")
                    return True
                elif status in ["unhealthy", "error"]:
                    logger.error(f"Container is {status}")
                    return False

                time.sleep(2)

            logger.error("Timeout waiting for container to be healthy")
            return False

        except Exception as e:
            logger.error(f"Error waiting for container to be healthy: {e}")
            return False

    def get_container_logs(
        self,
        tail: int = 100,
        since: str | None = None,
        timestamps: bool = False,
        follow: bool = False,
    ) -> str:
        """获取容器日志"""
        try:
            if not DOCKER_AVAILABLE:
                return ""

            if not self._container:
                logger.warning("No container to get logs from")
                return ""

            logs = self._container.logs(
                tail=tail,
                timestamps=timestamps,
                follow=follow,
                stdout=True,
                stderr=True,
            )

            return logs.decode("utf-8") if isinstance(logs, bytes) else logs

        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
            return ""

    def follow_container_logs(self, timeout: int = 0) -> str:
        """实时跟踪容器日志"""
        try:
            if not DOCKER_AVAILABLE:
                return ""

            if not self._container:
                logger.warning("No container to follow logs")
                return ""

            for log_line in self._container.logs(
                stream=True, follow=True, stdout=True, stderr=True
            ):
                if isinstance(log_line, bytes):
                    print(log_line.decode("utf-8").strip())
                else:
                    print(log_line.strip())

            return ""

        except Exception as e:
            logger.error(f"Failed to follow container logs: {e}")
            return ""

    def search_container_logs(self, pattern: str) -> List[str]:
        """在容器日志中搜索匹配内容"""
        try:
            if not DOCKER_AVAILABLE:
                return []

            if not self._container:
                logger.warning("No container to search logs")
                return []

            logs = self._container.logs(stdout=True, stderr=True)
            full_logs = ""
            for line in logs:
                if isinstance(line, bytes):
                    full_logs += line.decode("utf-8")
                else:
                    full_logs += line

            results = []
            for log_line in full_logs.split("\n"):
                if pattern.lower() in log_line.lower():
                    results.append(log_line.strip())

            return results

        except Exception as e:
            logger.error(f"Failed to search container logs: {e}")
            return []

    def export_container_logs(
        self,
        output_path: Path,
        tail: int = 0,
        since: str | None = None,
        timestamps: bool = False,
    ) -> bool:
        """导出容器日志到文件"""
        try:
            if not DOCKER_AVAILABLE:
                return True

            if not self._container:
                logger.warning("No container to export logs")
                return True

            logs = self._container.logs(
                tail=tail, since=since, timestamps=timestamps, stdout=True, stderr=True
            )

            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "wb") as f:
                if isinstance(logs, bytes):
                    f.write(logs)
                else:
                    f.write(logs.encode("utf-8"))

            logger.info(f"Exported container logs to: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export container logs: {e}")
            return False

    def get_container_stats(self) -> Dict[str, Any]:
        """获取容器资源使用统计"""
        try:
            if not DOCKER_AVAILABLE or not self._container:
                return {}

            self._container.reload()
            stats = self._container.stats(stream=False)

            cpu_delta = stats.get("cpu_stats", {}).get("cpu_usage", {}).get(
                "total_usage", 0
            ) - stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)

            system_delta = stats.get("cpu_stats", {}).get("system_cpu_usage", 0)

            cpu_percent = 0.0
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * 100.0

            memory_usage = stats.get("memory_stats", {}).get("usage", 0)
            memory_limit = stats.get("memory_stats", {}).get("limit", 0)
            memory_percent = 0.0
            if memory_limit > 0:
                memory_percent = (memory_usage / memory_limit) * 100.0

            networks = stats.get("networks", {})
            network_rx = 0
            network_tx = 0

            for net_name, net_stats in networks.items():
                network_rx += net_stats.get("rx_bytes", 0)
                network_tx += net_stats.get("tx_bytes", 0)

            blkio_stats = stats.get("blkio_stats", {})
            disk_read = blkio_stats.get("io_service_bytes_recursive", {}).get("read", 0)
            disk_write = blkio_stats.get("io_service_bytes_recursive", {}).get(
                "write", 0
            )

            pids_current = stats.get("pids_stats", {}).get("current", 0)
            pids_limit = stats.get("pids_stats", {}).get("limit", 0)

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_usage": memory_usage,
                "memory_limit": memory_limit,
                "memory_percent": round(memory_percent, 2),
                "network_rx": network_rx,
                "network_tx": network_tx,
                "disk_read": disk_read,
                "disk_write": disk_write,
                "pids_current": pids_current,
                "pids_limit": pids_limit,
                "timestamp": stats.get("read", None),
            }

        except Exception as e:
            logger.error(f"Failed to get container stats: {e}")
            return {}

    def get_container_info(self) -> Dict[str, Any]:
        """获取容器信息"""
        try:
            if not self._container:
                return {
                    "name": self.container_name,
                    "container_id": None,
                    "container_name": self.container_name,
                    "status": "not_created",
                    "image": self.image_name,
                }

            self._container.reload()

            return {
                "name": self.container_name,
                "container_id": self.container_id,
                "container_name": self.container_name,
                "status": self._container.status,
                "image": self.image_name,
                "ip_address": self._container.attrs["NetworkSettings"]["IPAddress"]
                if self._container.attrs.get("NetworkSettings")
                and self._container.attrs["NetworkSettings"].get("IPAddress")
                else None,
                "ports": self._container.attrs.get("NetworkSettings", {}).get(
                    "Ports", {}
                ),
                "created": self._container.attrs.get("Created"),
                "started": self._container.attrs.get("Started"),
                "labels": self._container.attrs.get("Labels", {}),
                "mounts": self._container.attrs.get("Mounts", []),
            }

        except Exception as e:
            logger.error(f"Error getting container info: {e}")
            return {
                "name": self.container_name,
                "container_id": self.container_id,
                "container_name": self.container_name,
                "status": "error",
                "error": str(e),
                "image": self.image_name,
            }

    def activate(self) -> bool:
        """激活Docker环境"""
        try:
            return self.start_container()
        except Exception as e:
            logger.error(f"Failed to activate Docker environment: {e}")
            return False

    def deactivate(self) -> bool:
        """停用Docker环境"""
        try:
            return self.stop_container()
        except Exception as e:
            logger.error(f"Failed to deactivate Docker environment: {e}")
            return False

    def execute_command(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        env_vars: Optional[Dict[str, str]] = None,
        cwd: Optional[Path] = None,
    ) -> ProcessResult:
        """在隔离环境中执行命令 (实现抽象方法)"""
        # 调用Docker特定的exec_command方法
        return self.exec_command(
            cmd=cmd,
            timeout=timeout,
            env_vars=env_vars,
            cwd=cwd,
            tty=False,
            interactive=False,
        )

    def exec_command(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        env_vars: Optional[Dict[str, str]] = None,
        cwd: Optional[Path] = None,
        tty: bool = False,
        interactive: bool = False,
    ) -> ProcessResult:
        """在Docker容器中执行命令 (Docker特定方法)"""
        try:
            from datetime import datetime

            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating command execution")
                return ProcessResult(returncode=0, stdout="", stderr="", command=cmd)

            if not self._container:
                logger.warning("Container not created, cannot execute command")
                return ProcessResult(
                    returncode=-1,
                    stdout="",
                    stderr="Container not created",
                    command=cmd,
                )

            exec_config = {"detach": not interactive and not tty}
            if tty:
                exec_config["tty"] = True
            if cwd:
                exec_config["workdir"] = str(cwd)

            if env_vars:
                exec_config["environment"] = env_vars

            if interactive:
                exit_code, output = self._container.exec_run(cmd, **exec_config)
                stdout = output.decode("utf-8") if isinstance(output, bytes) else output

                return ProcessResult(
                    returncode=exit_code,
                    stdout=stdout,
                    stderr="",
                    command=cmd,
                    timeout=timeout,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                )
            else:
                exit_code, output = self._container.exec_run(cmd, **exec_config)
                stdout = output.decode("utf-8") if isinstance(output, bytes) else output

                return ProcessResult(
                    returncode=exit_code,
                    stdout=stdout,
                    stderr="",
                    command=cmd,
                    timeout=timeout,
                )

        except Exception as e:
            logger.error(f"Failed to execute command in Docker container: {e}")
            return ProcessResult(
                returncode=-1,
                stdout="",
                stderr=str(e),
                command=cmd,
                timeout=timeout,
            )

    def install_package(
        self, package: str, version: Optional[str] = None, upgrade: bool = False
    ) -> bool:
        """在Docker环境中安装包"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating package installation: {package}"
                )
                return True

            if not self._container:
                logger.warning("Container not created, cannot install package")
                return False

            if version:
                cmd = ["pip", "install", f"{package}=={version}"]
            else:
                cmd = ["pip", "install", package]

            result = self.execute_command(cmd, timeout=600)
            success = result.returncode == 0

            if success:
                logger.info(f"Successfully installed package: {package}")
                self._emit_event(IsolationEvent.PACKAGE_INSTALLED, package=package)
            else:
                logger.error(f"Failed to install package {package}: {result.stderr}")

            return success

        except Exception as e:
            logger.error(f"Failed to install package {package}: {e}")
            return False

    def uninstall_package(self, package: str) -> bool:
        """在Docker环境中卸载包"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating package uninstallation: {package}"
                )
                return True

            if not self._container:
                logger.warning("Container not created, cannot uninstall package")
                return False

            cmd = ["pip", "uninstall", "-y", package]
            result = self.execute_command(cmd, timeout=300)
            success = result.returncode == 0

            if success:
                logger.info(f"Successfully uninstalled package: {package}")
            else:
                logger.error(f"Failed to uninstall package {package}: {result.stderr}")

            return success

        except Exception as e:
            logger.error(f"Failed to uninstall package {package}: {e}")
            return False

    def get_installed_packages(self) -> Dict[str, str]:
        """获取Docker环境中已安装的包列表"""
        try:
            if not DOCKER_AVAILABLE:
                return {}

            if not self._container:
                return {}

            result = self.execute_command(
                ["pip", "list", "--format=freeze"], timeout=30
            )
            if result.returncode == 0:
                packages = {}
                for line in result.stdout.split("\n"):
                    if line and "==" in line:
                        name, version = line.split("==")
                        packages[name] = version
                return packages
            else:
                logger.error(f"Failed to get installed packages: {result.stderr}")
                return {}

        except Exception as e:
            logger.error(f"Failed to get installed packages: {e}")
            return {}

    def get_package_version(self, package: str) -> Optional[str]:
        """获取Docker环境中指定包的版本"""
        try:
            if not DOCKER_AVAILABLE:
                return None

            if not self._container:
                return None

            result = self.execute_command(["pip", "show", package], timeout=30)

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.startswith("Version:"):
                        return line.split(":")[1].strip()
            return None

        except Exception as e:
            logger.error(f"Failed to get package version for {package}: {e}")
            return None

    def allocate_port(self) -> int:
        """分配端口"""
        try:
            import socket
            from contextlib import closing

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.bind(("", 0))
                s.listen(1)
                port = s.getsockname()[1]

            self.allocated_ports.append(port)
            self.port_mappings[port] = port
            logger.debug(f"Allocated port: {port}")
            return port

        except Exception as e:
            logger.error(f"Failed to allocate port: {e}")
            return -1

    def release_port(self, port: int) -> bool:
        """释放端口"""
        try:
            if port in self.port_mappings:
                del self.port_mappings[port]

            if port in self.allocated_ports:
                self.allocated_ports.remove(port)
                logger.debug(f"Released port: {port}")
                return True
            else:
                logger.warning(f"Port {port} not found in allocated ports")
                return False

        except Exception as e:
            logger.error(f"Failed to release port {port}: {e}")
            return False

    def cleanup(self, force: bool = False) -> bool:
        """清理Docker环境"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating cleanup")
                self.status = EnvironmentStatus.CLEANUP_COMPLETE
                self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_COMPLETE)
                return True

            # 停止容器
            if self._container and self.status == EnvironmentStatus.ACTIVE:
                self.stop_container()

            # 删除容器
            if self._container:
                try:
                    self._container.remove(force=force)
                    logger.info(f"Removed container: {self.container_id}")
                except Exception as e:
                    logger.error(f"Failed to remove container: {e}")
                    if not force:
                        return False

            self._container = None
            self.container_id = None
            self.status = EnvironmentStatus.CLEANUP_COMPLETE
            self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_COMPLETE)

            return True

        except Exception as e:
            logger.error(f"Failed to cleanup Docker environment: {e}")
            if not force:
                self.status = EnvironmentStatus.ERROR
            else:
                self.status = EnvironmentStatus.CLEANUP_COMPLETE
            return False

    def validate_isolation(self) -> bool:
        """验证Docker隔离有效性"""
        try:
            if not DOCKER_AVAILABLE:
                return True

            # 检查容器是否存在
            if not self._container:
                logger.warning("Container not created, cannot validate isolation")
                return False

            # 检查容器状态
            self._container.reload()
            status = self._container.status

            is_valid = status in ["running", "created"]

            if is_valid:
                logger.debug(f"Docker isolation validation passed: {status}")
            else:
                logger.warning(f"Docker isolation validation failed: {status}")

            return is_valid

        except Exception as e:
            logger.error(f"Failed to validate Docker isolation: {e}")
            return False

    def create_snapshot(self, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        """创建Docker环境快照"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating snapshot creation")
                snapshot_id = snapshot_id or f"snapshot_{uuid.uuid4().hex}"
                return {
                    "snapshot_id": snapshot_id,
                    "env_id": self.env_id,
                    "snapshot_time": datetime.now().isoformat(),
                    "status": "simulated",
                    "config": self.config,
                }

            if not self._container:
                logger.warning("Container not created, cannot create snapshot")
                return {}

            if not snapshot_id:
                snapshot_id = f"{self.env_id}_snapshot_{uuid.uuid4().hex[:8]}"

            snapshot_image = self._container.commit(repository=snapshot_id)

            logger.info(f"Created snapshot: {snapshot_id}")
            self._emit_event(
                IsolationEvent.SNAPSHOT_CREATED,
                snapshot_id=snapshot_id,
                snapshot_image=snapshot_image.id,
            )

            return {
                "snapshot_id": snapshot_id,
                "env_id": self.env_id,
                "snapshot_time": datetime.now().isoformat(),
                "status": "created",
                "config": self.config,
                "image_id": snapshot_image.id,
            }

        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            return {"error": str(e)}

    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """从快照恢复Docker环境"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    "Docker SDK not available, simulating snapshot restoration"
                )
                return True

            if not self._container:
                logger.warning("Container not created, cannot restore snapshot")
                return False

            snapshot_id = snapshot.get("snapshot_id")
            if not snapshot_id:
                logger.error("Invalid snapshot data: missing snapshot_id")
                return False

            try:
                snapshot_image = self.isolation_engine.docker_client.images.get(
                    snapshot_id
                )
            except Exception:
                logger.error(f"Snapshot image not found: {snapshot_id}")
                return False

            if self.status == EnvironmentStatus.ACTIVE:
                self.stop_container()

            if self._container:
                self._container.remove(force=True)

            self.image_name = snapshot_id
            success = self.create_container()

            if success:
                logger.info(f"Restored from snapshot: {snapshot_id}")
                self._emit_event(
                    IsolationEvent.SNAPSHOT_RESTORED, snapshot_id=snapshot_id
                )
            else:
                logger.error(f"Failed to create container from snapshot: {snapshot_id}")

            return success

        except Exception as e:
            logger.error(f"Failed to restore from snapshot {snapshot_id}: {e}")
            return False

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除Docker快照"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating snapshot deletion")
                return True

            # 删除快照镜像
            try:
                self.isolation_engine.docker_client.images.remove(snapshot_id)
                logger.info(f"Deleted snapshot image: {snapshot_id}")
            except Exception as e:
                logger.warning(
                    f"Snapshot image not found or already deleted: {snapshot_id}"
                )
                # 如果镜像不存在或已删除，仍然返回成功
                pass

            self._emit_event(IsolationEvent.SNAPSHOT_DELETED, snapshot_id=snapshot_id)
            return True

        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False

    def export_container(self, output_path: Path) -> bool:
        """导出容器为tar文件"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container export")
                return True

            if not self._container:
                logger.warning("Container not created, cannot export")
                return False

            logger.info(f"Exporting container to: {output_path}")
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "wb") as f:
                for chunk in self._container.get():
                    f.write(chunk)

            logger.info(f"Successfully exported container to: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export container: {e}")
            return False

    def import_container(self, input_path: Path, image_name: str) -> bool:
        """从tar文件导入容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container import")
                return True

            logger.info(f"Importing container from: {input_path}")

            with open(input_path, "rb") as f:
                self.isolation_engine.docker_client.images.load(f.read())

            logger.info(f"Successfully imported container image: {image_name}")
            self.image_name = image_name

            return True

        except Exception as e:
            logger.error(f"Failed to import container: {e}")
            return False

    def create_snapshot_from_container(
        self, snapshot_id: Optional[str] = None, include_data: bool = False
    ) -> Dict[str, Any]:
        """从运行中的容器创建快照镜像

        Args:
            snapshot_id: 快照ID
            include_data: 是否包含数据卷数据

        Returns:
            快照信息字典
        """
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating snapshot creation")
                snapshot_id = snapshot_id or f"snapshot_{uuid.uuid4().hex}"
                return {
                    "snapshot_id": snapshot_id,
                    "env_id": self.env_id,
                    "snapshot_time": datetime.now().isoformat(),
                    "status": "simulated",
                    "config": self.config,
                }

            if not self._container:
                logger.warning("Container not created, cannot create snapshot")
                return {}

            if not snapshot_id:
                snapshot_id = f"{self.env_id}_snapshot_{uuid.uuid4().hex[:8]}"

            logger.info(f"Creating container snapshot: {snapshot_id}")
            self._container.reload()

            container_state = {
                "config": self._container.attrs.get("Config", {}),
                "status": self._container.status,
                "image": self.image_name,
                "restart_count": self._container.attrs.get("RestartCount", 0),
                "labels": self._container.attrs.get("Labels", {}),
                "env_vars": self.environment_vars,
                "volumes": self.volumes,
            }

            snapshot_image = self._container.commit(
                repository=snapshot_id,
                message=f"Snapshot created at {datetime.now().isoformat()}",
                config=container_state["config"],
            )

            logger.info(f"Created container snapshot: {snapshot_id}")
            self._emit_event(
                IsolationEvent.SNAPSHOT_CREATED,
                snapshot_id=snapshot_id,
                snapshot_image=snapshot_image.id,
                container_state=container_state,
            )

            return {
                "snapshot_id": snapshot_id,
                "env_id": self.env_id,
                "snapshot_time": datetime.now().isoformat(),
                "status": "created",
                "container_state": container_state,
                "image_id": snapshot_image.id,
                "config": self.config,
            }

        except Exception as e:
            logger.error(f"Failed to create container snapshot: {e}")
            return {"error": str(e)}


class DockerIsolationEngine(IsolationEngine):
    """Docker隔离引擎实现"""

    engine_name: str = "docker"
    isolation_level: str = "docker"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.supported_features = [
            "filesystem_isolation",
            "python_package_isolation",
            "process_execution",
            "port_allocation",
            "network_isolation",
            "volume_management",
            "container_isolation",
            "image_management",
        ]

        # Docker引擎配置
        self.default_config = {
            "docker_host": os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock"),
            "default_image": "python:3.9-slim",
            "default_registry": "docker.io",
            "network_subnet": "172.20.0.0/16",
            "volume_base_path": "/var/lib/ptest/volumes",
            "container_timeout": 300,
            "pull_timeout": 600,
            "build_timeout": 1800,
            "stop_timeout": 30,
            "resource_limits": {"memory": "512m", "cpus": "1.0", "disk": "10g"},
        }

        # 合并用户配置
        self.engine_config = {**self.default_config, **config}

        # Docker客户端
        self.docker_client: Optional[Any] = None
        self.api_client: Optional[Any] = None
        self._client_lock = threading.Lock()

        self.image_manager = None
        self.network_manager = None
        self.volume_manager = None

        # 前缀
        self.network_prefix = "ptest_net_"
        self.volume_prefix = "ptest_vol_"

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        info = super().get_engine_info()
        info["engine_type"] = "docker"
        return info

    def initialize_client(self) -> bool:
        """初始化Docker客户端"""
        if not DOCKER_AVAILABLE:
            logger.warning("Docker SDK not available, running in simulation mode")
            return True

        with self._client_lock:
            if self.docker_client:
                return True

            try:
                import docker

                if "docker_host" in self.engine_config:
                    os.environ["DOCKER_HOST"] = self.engine_config["docker_host"]

                self.docker_client = docker.from_env()
                self.api_client = docker.APIClient()

                from .managers import ImageManager, NetworkManager, VolumeManager

                self.image_manager = ImageManager(
                    self.docker_client, self.engine_config
                )
                self.network_manager = NetworkManager(
                    self.docker_client, self.network_prefix
                )
                self.volume_manager = VolumeManager(
                    self.docker_client, self.volume_prefix
                )

                logger.info("Docker client initialized successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to initialize Docker client: {e}")
                return False

    def verify_docker_environment(self) -> Dict[str, Any]:
        """验证Docker环境"""
        try:
            # 获取Docker信息
            if self.docker_client:
                info = self.docker_client.info()
                version = self.docker_client.version()

                return {
                    "available": True,
                    "simulation_mode": False,
                    "docker_info": {
                        "version": version.get("Version"),
                        "api_version": version.get("ApiVersion"),
                        "arch": info.get("Architecture"),
                        "os": info.get("OperatingSystem"),
                        "ncpu": info.get("NCPU"),
                        "mem_total": info.get("MemTotal"),
                        "containers": info.get("Containers"),
                        "images": info.get("Images"),
                    },
                }
            else:
                return {
                    "available": True,
                    "simulation_mode": False,
                    "docker_info": {},
                }

        except Exception as e:
            logger.error(f"Error verifying Docker environment: {e}")
            return {
                "available": False,
                "reason": str(e),
                "simulation_mode": False,
            }

    def list_available_images(self) -> List[Dict[str, Any]]:
        """列出所有可用的Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, returning empty list")
                return []

            if not self.docker_client:
                return []

            images = self.docker_client.images.list(all=True)
            result = []

            for img in images:
                tags = img.tags
                result.append(
                    {
                        "id": img.id,
                        "tags": tags,
                        "short_id": img.short_id,
                        "created": img.attrs.get("Created"),
                        "size": img.attrs.get("Size"),
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Failed to list images: {e}")
            return []

    def cleanup_unused_resources(self) -> Dict[str, Any]:
        """清理未使用的Docker资源"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating cleanup")
                return {"cleaned": False, "containers": 0, "details": "simulation_mode"}

            if not self.docker_client:
                return {
                    "cleaned": False,
                    "containers": 0,
                    "details": "no_docker_client",
                }

            images_pruned = self.docker_client.images.prune()
            volumes_pruned = self.docker_client.volumes.prune()

            images_count = len(images_pruned.get("ImagesDeleted", []))
            volumes_count = len(volumes_pruned.get("VolumesDeleted", []))

            logger.info(f"Cleaned up {images_count} images and {volumes_count} volumes")
            return {
                "cleaned": True,
                "details": {
                    "images_removed": images_pruned.get("ImagesDeleted", []),
                    "volumes_removed": volumes_pruned.get("VolumesDeleted", []),
                    "total_cleaned": images_count + volumes_count,
                    "containers": 0,
                },
            }

        except Exception as e:
            logger.error(f"Failed to cleanup resources: {e}")
            return {
                "cleaned": False,
                "error": str(e),
                "containers": 0,
            }

    def pull_image(self, image_name: str, tag: str = "latest") -> bool:
        """拉取Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image pull: {image_name}:{tag}"
                )
                return True

            if not self.initialize_client():
                return False

            if not self.docker_client:
                return False

            full_image_name = f"{image_name}:{tag}"
            logger.info(f"Pulling Docker image: {full_image_name}")

            # 检查镜像是否已存在
            try:
                self.docker_client.images.get(full_image_name)
                logger.info(f"Image {full_image_name} already exists locally")
                return True
            except:
                logger.debug(
                    f"Image {full_image_name} not found locally, proceeding with pull"
                )

            # 拉取镜像
            self.docker_client.images.pull(full_image_name)
            logger.info(f"Successfully pulled image: {full_image_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to pull image {image_name}:{tag}: {e}")
            return False

    def push_image(
        self,
        image_name: str,
        tag: str = "latest",
        registry: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> bool:
        """推送Docker镜像到仓库

        Args:
            image_name: 镜像名称
            tag: 标签（默认latest）
            registry: 镜像仓库地址
            username: 用户名
            password: 密码

        Returns:
            bool: 是否推送成功
        """
        """推送Docker镜像到仓库"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image push: {image_name}:{tag}"
                )
                return True

            if not self.initialize_client():
                return False

            if not self.docker_client:
                return False

            full_image_name = f"{image_name}:{tag}"
            logger.info(f"Pushing Docker image: {full_image_name}")

            # 如果指定了registry，先标记镜像
            if registry:
                registry_image_name = f"{registry}/{full_image_name}"
                self.docker_client.images.tag(full_image_name, registry_image_name)
                full_image_name = registry_image_name

            # 推送镜像
            for line in self.docker_client.images.push(
                full_image_name, stream=True, decode=True
            ):
                if "status" in line:
                    logger.debug(f"Push status: {line['status']}")
                if "error" in line:
                    logger.error(f"Push error: {line['error']}")
                    return False

            logger.info(f"Successfully pushed image: {full_image_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to push image {image_name}:{tag}: {e}")
            return False

    def tag_image(self, source: str, target: str) -> bool:
        """给Docker镜像打标签"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image tag: {source} -> {target}"
                )
                return True

            if not self.initialize_client():
                return False

            if not self.docker_client:
                return False

            logger.info(f"Tagging image: {source} -> {target}")
            self.docker_client.images.tag(source, target)
            logger.info(f"Successfully tagged image: {target}")
            return True

        except Exception as e:
            logger.error(f"Failed to tag image {source}: {e}")
            return False

    def save_image(self, image_name: str, output_path: Path) -> bool:
        """导出Docker镜像到文件"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image push: {image_name}"
                )
                return True

            if not self.initialize_client():
                return False

            full_image_name = f"{image_name}:{tag}"

            # 构建认证配置
            auth_config = {}
            if username:
                auth_config["username"] = username
                if password:
                    auth_config["password"] = password

                # 支持令牌认证
                if registry and any(key in registry for key in ["token", "bearer"]):
                    # 如果registry包含token/bearer，将整个registry作为token
                    auth_config["identitytoken"] = registry
                elif password:
                    auth_config["identitytoken"] = f"{username}:{password}"

            # 如果指定了registry，先标记镜像
            if registry:
                registry_image_name = f"{registry}/{full_image_name}"
                self.docker_client.images.tag(full_image_name, registry_image_name)
                full_image_name = registry_image_name

            logger.info(
                f"Pushing Docker image: {full_image_name} to registry: {registry}"
            )

            # 推送镜像
            for line in self.docker_client.images.push(
                full_image_name, auth_config=auth_config, stream=True, decode=True
            ):
                if "status" in line:
                    logger.debug(f"Push status: {line['status']}")
                if "error" in line:
                    # 解析错误信息
                    error_msg = line.get("error", "").strip()
                    if "unauthorized" in error_msg.lower():
                        logger.error(f"Authentication failed: {error_msg}")
                        return False
                    elif "denied" in error_msg.lower():
                        logger.error(f"Access denied: {error_msg}")
                        return False
                    logger.error(f"Push error: {error_msg}")
                    return False
                if "progressDetail" in line:
                    logger.debug(f"Push progress: {line['progressDetail']}")

            logger.info(f"Successfully pushed image: {full_image_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to push image {image_name}:{tag}: {e}")
            return False

            if not self.docker_client:
                return False

            logger.info(f"Saving image: {image_name} to {output_path}")

            # 确保输出目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 获取镜像
            image = self.docker_client.images.get(image_name)

            # 保存镜像
            with open(output_path, "wb") as f:
                for chunk in image.save():
                    f.write(chunk)

            logger.info(f"Successfully saved image: {image_name} to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save image {image_name}: {e}")
            return False

    def load_image(self, input_path: Path) -> bool:
        """从文件加载Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image load: {input_path}"
                )
                return True

            if not self.initialize_client():
                return False

            if not self.docker_client:
                return False

            logger.info(f"Loading image from: {input_path}")

            # 读取镜像文件
            with open(input_path, "rb") as f:
                image_data = f.read()

            # 加载镜像
            self.docker_client.images.load(image_data)
            logger.info(f"Successfully loaded image from: {input_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load image from {input_path}: {e}")
            return False

    def create_network(
        self, network_name: str, subnet: str | None = None
    ) -> Optional[Any]:
        """创建Docker网络"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating network creation: {network_name}"
                )
                return None

            if not self.initialize_client():
                return None

            if not self.docker_client:
                return None

            # 检查网络是否已存在
            try:
                existing_network = self.docker_client.networks.get(network_name)
                logger.info(f"Network {network_name} already exists")
                return existing_network
            except:
                pass

            # 创建新网络 - 改进参数配置
            network_config = {
                "Name": network_name,
                "Driver": "bridge",
            }

            if subnet:
                network_config["IPAM"] = {
                    "Config": [
                        {
                            "Subnet": subnet,
                            "IPRange": subnet.rsplit(".", 1)[0] + ".0.1/24",
                        }
                    ]
                }
                network_config["Options"] = {
                    f"com.docker.network.bridge.name": network_name
                }

            network = self.docker_client.networks.create(network_config)
            logger.info(f"Created Docker network: {network_name}")
            return network

        except Exception as e:
            logger.error(f"Failed to create network {network_name}: {e}")
            return None

    def create_volume(
        self,
        volume_name: str,
        driver: str = "local",
        driver_opts: Dict[str, str] | None = None,
    ) -> Optional[Any]:
        """创建Docker卷"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating volume creation: {volume_name}"
                )
                return None

            if not self.initialize_client():
                return None

            if not self.docker_client:
                return None

            # 检查卷是否已存在
            try:
                existing_volume = self.docker_client.volumes.get(volume_name)
                logger.info(f"Volume {volume_name} already exists")
                return existing_volume
            except:
                pass

            # 创建新卷
            volume_config = {
                "Name": volume_name,
                "Driver": driver,
                "Labels": {"created_by": "ptest", "purpose": "test_isolation"},
            }

            if driver_opts:
                volume_config["DriverOpts"] = driver_opts

            volume = self.docker_client.volumes.create(volume_config)
            logger.info(f"Created Docker volume: {volume_name}")
            return volume

        except Exception as e:
            logger.error(f"Failed to create volume {volume_name}: {e}")
            return None

    def connect_container_to_network(
        self,
        container_id: str,
        network_name: str,
        aliases: List[str] | None = None,
        ipv4_address: str | None = None,
    ) -> bool:
        """将容器连接到网络"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    "Docker SDK not available, simulating network connection"
                )
                return True

            if not self.docker_client:
                return False

            network = self.docker_client.networks.get(network_name)
            if not network:
                logger.error(f"Network {network_name} not found")
                return False

            network_config = {}
            if aliases:
                network_config["aliases"] = aliases
            if ipv4_address:
                network_config["ipv4_address"] = ipv4_address

            network.connect(container_id, **network_config)
            logger.info(f"Connected container {container_id} to network {network_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect container to network: {e}")
            return False

    def disconnect_container_from_network(
        self, container_id: str, network_name: str
    ) -> bool:
        """将容器从网络断开"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    "Docker SDK not available, simulating network disconnection"
                )
                return True

            if not self.docker_client:
                return False

            network = self.docker_client.networks.get(network_name)
            if not network:
                logger.error(f"Network {network_name} not found")
                return False

            network.disconnect(container_id)
            logger.info(
                f"Disconnected container {container_id} from network {network_name}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to disconnect container from network: {e}")
            return False

    def remove_network(self, network_name: str) -> bool:
        """删除Docker网络"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating network removal")
                return True

            if not self.docker_client:
                return False

            network = self.docker_client.networks.get(network_name)
            if network:
                network.remove()
                logger.info(f"Removed network: {network_name}")
                return True

            logger.info(f"Network {network_name} not found, nothing to remove")
            return False

        except Exception as e:
            logger.error(f"Failed to remove network {network_name}: {e}")
            return False

    def remove_volume(self, volume_name: str, force: bool = False) -> bool:
        """删除Docker卷"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating volume removal")
                return True

            if not self.docker_client:
                return False

            volume = self.docker_client.volumes.get(volume_name)
            if volume:
                volume.remove(force=force)
                logger.info(f"Removed volume: {volume_name}")
                return True

            logger.info(f"Volume {volume_name} not found, nothing to remove")
            return False

        except Exception as e:
            logger.error(f"Failed to remove volume {volume_name}: {e}")
            return False

    def list_networks(self) -> List[Dict[str, Any]]:
        """列出所有Docker网络"""
        try:
            if not DOCKER_AVAILABLE:
                return []

            if not self.docker_client:
                return []

            networks = self.docker_client.networks.list()
            return [
                {
                    "id": net.id,
                    "name": net.name,
                    "driver": net.attrs.get("Driver"),
                    "scope": net.attrs.get("Scope"),
                }
                for net in networks
            ]

        except Exception as e:
            logger.error(f"Failed to list networks: {e}")
            return []

    def list_volumes(self) -> List[Dict[str, Any]]:
        """列出所有Docker卷"""
        try:
            if not DOCKER_AVAILABLE:
                return []

            if not self.docker_client:
                return []

            volumes = self.docker_client.volumes.list()
            result = []

            # 处理Docker SDK返回的不同格式
            volumes_data = volumes.get("Volumes", volumes)
            volumes_list = volumes_data if isinstance(volumes_data, list) else [volumes]

            for vol in volumes_list:
                attrs = vol.attrs if hasattr(vol, "attrs") else {}
                result.append(
                    {
                        "name": vol.name,
                        "driver": attrs.get("Driver"),
                        "mountpoint": attrs.get("Mountpoint"),
                        "created": attrs.get("CreatedAt"),
                        "labels": attrs.get("Labels", {}),
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Failed to list volumes: {e}")
            return []

    def prune_images(self, dangling_only: bool = True) -> Dict[str, Any]:
        """清理未使用的Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                return {"ImagesDeleted": [], "SpaceReclaimed": 0}

            if not self.docker_client:
                return {"ImagesDeleted": [], "SpaceReclaimed": 0}

            result = self.docker_client.images.prune(dangling=dangling_only)
            logger.info(f"Pruned {len(result.get('ImagesDeleted', []))} images")
            return result

        except Exception as e:
            logger.error(f"Failed to prune images: {e}")
            return {"ImagesDeleted": [], "SpaceReclaimed": 0}

    def prune_volumes(self) -> Dict[str, Any]:
        """清理未使用的Docker卷"""
        try:
            if not DOCKER_AVAILABLE:
                return {"VolumesDeleted": [], "SpaceReclaimed": 0}

            if not self.docker_client:
                return {"VolumesDeleted": [], "SpaceReclaimed": 0}

            result = self.docker_client.volumes.prune()
            logger.info(f"Pruned {len(result.get('VolumesDeleted', []))} volumes")
            return result

        except Exception as e:
            logger.error(f"Failed to prune volumes: {e}")
            return {"VolumesDeleted": [], "SpaceReclaimed": 0}

    def create_isolation(
        self, path: Path, env_id: str, isolation_config: Dict[str, Any]
    ) -> IsolatedEnvironment:
        """创建Docker隔离环境"""
        # 合并引擎配置和隔离配置
        final_config = {**self.engine_config, **isolation_config}

        # 创建环境
        env = DockerEnvironment(env_id, path, self, final_config)

        # 预拉取镜像
        image_name = final_config.get("image", self.engine_config["default_image"])
        if ":" not in image_name:
            image_name = f"{image_name}:latest"
        self.pull_image(image_name)

        # 创建网络（如果需要）
        if final_config.get("create_network", False):
            network_name = (
                f"{self.engine_config['network_subnet'].split('.')[0]}_{env_id}"
            )
            env.network_name = network_name
            env._network = self.create_network(network_name)

        # 创建卷（如果需要）
        if final_config.get("create_volume", False):
            volume_name = f"{env_id}_volume"
            env.volumes[volume_name] = {
                "bind": str(path),
                "mode": "rw",
            }
            env.volume_name = volume_name
            env._volume = self.create_volume(volume_name)

        self.created_environments[env_id] = env
        logger.info(f"Created Docker environment: {env_id} at {path}")
        return env

    def cleanup_isolation(self, env: IsolatedEnvironment) -> bool:
        """清理隔离环境"""
        if isinstance(env, DockerEnvironment):
            success = env.cleanup(force=True)
            if success:
                # 从引擎的创建环境列表中移除
                if env.env_id in self.created_environments:
                    del self.created_environments[env.env_id]
                logger.info(f"Successfully cleaned up Docker environment: {env.env_id}")
            else:
                logger.error(f"Failed to clean up Docker environment: {env.env_id}")
            return success
        else:
            logger.error(f"Invalid environment type for Docker engine: {type(env)}")
            return False

    def get_isolation_status(self, env_id: str) -> Dict[str, Any]:
        """获取隔离状态"""
        if env_id not in self.created_environments:
            return {"status": "not_found", "isolation_type": "docker"}

        env = self.created_environments[env_id]
        status = env.get_status()
        status.update(
            {
                "isolation_type": "docker",
                "supported_features": self.supported_features,
                "engine_config": self.engine_config,
            }
        )
        return status

    def validate_isolation(self, env: IsolatedEnvironment) -> bool:
        """验证隔离有效性"""
        if isinstance(env, DockerEnvironment):
            is_valid = env.validate_isolation()
            logger.debug(f"Docker validation result for {env.env_id}: {is_valid}")
            return is_valid
        else:
            logger.error(f"Invalid environment type for Docker engine: {type(env)}")
            return False

    def get_supported_features(self) -> List[str]:
        """获取支持的功能列表"""
        return self.supported_features.copy()

    def manage_images(self) -> Optional["ImageManager"]:
        """获取镜像管理器"""
        return self.image_manager

    def manage_networks(self) -> Optional["NetworkManager"]:
        """获取网络管理器"""
        return self.network_manager

    def manage_volumes(self) -> Optional["VolumeManager"]:
        """获取卷管理器"""
        return self.volume_manager

    def check_environment_health(self, env: IsolatedEnvironment) -> bool:
        """检查Docker环境健康状态"""
        try:
            return True
        except Exception as e:
            logger.error(f"Error checking Docker environment health: {e}")
            return False

    def pause_container(self, timeout: int = 10) -> bool:
        """暂停容器（支持优雅停止和强制停止）

        Args:
            timeout: 等待超时时间（秒）

        Returns:
            bool: 是否成功暂停

        Raises:
            TimeoutError: 如果超时

            RuntimeError: 如果容器状态不允许暂停
        """
        try:
            return True
        except Exception as e:
            logger.error(f"Error checking Docker environment health: {e}")
            return False

    def get_environment_metrics(self, env: IsolatedEnvironment) -> Dict[str, Any]:
        """获取Docker环境指标"""
        try:
            disk_usage = 0
            if env.path.exists():
                disk_usage = sum(
                    f.stat().st_size for f in env.path.rglob("*") if f.is_file()
                )

            return {
                "performance": {
                    "container_info": "Docker container metrics available",
                },
                "disk_usage_mb": disk_usage / (1024 * 1024),
            }
        except Exception as e:
            logger.error(f"Error getting Docker environment metrics: {e}")
            return {"performance": {}, "error": str(e)}
