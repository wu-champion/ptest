"""
Docker隔离引擎实现

提供Docker容器隔离功能，支持容器创建、管理、网络配置等
"""

import os
import sys
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Union, Callable, TYPE_CHECKING
from pathlib import Path
import logging
from datetime import datetime
import threading
from contextlib import contextmanager

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
from core import get_logger, execute_command

# 使用框架的日志管理器
logger = get_logger("docker_engine")


class DockerEnvironment(IsolatedEnvironment):
    """Docker隔离环境实现"""

    def __init__(
        self,
        env_id: str,
        path: Path,
        isolation_engine: Any,  # 改为Any避免循环导入问题
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(env_id, path, isolation_engine, config or {})

        # Docker特有属性
        self.container_id: Optional[str] = None
        self.container_name: str = f"ptest_{env_id}_{uuid.uuid4().hex[:8]}"
        self.image_name: str = config.get(
            "image",
            isolation_engine.engine_config["default_image"]
            if hasattr(isolation_engine, "engine_config")
            else "python:3.9-slim",
        )
        self.network_name: str = ""
        self.volumes: Dict[str, Dict[str, str]] = {}
        self.port_mappings: Dict[int, int] = {}
        self.environment_vars: Dict[str, str] = {}
        self.resource_limits: Dict[str, Any] = {}

        # 状态跟踪
        self.status = EnvironmentStatus.CREATED
        self._container: Optional[DockerContainer] = None
        self._network: Optional[DockerNetwork] = None

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

            # 简化的容器配置（避免复杂的API调用）
            container_config = {
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

            # 创建容器
            if hasattr(engine, "docker_client") and engine.docker_client:
                self._container = engine.docker_client.containers.create(
                    **container_config
                )
            self.container_id = self._container.id if self._container else None

            logger.info(f"Created Docker container: {self.container_id}")
            self._emit_event(IsolationEvent.ENVIRONMENT_CREATED)
            return True

        except DockerSDKException as e:
            logger.error(f"Failed to create container: {e}")
            self.status = EnvironmentStatus.ERROR
            self._emit_event(IsolationEvent.ERROR_OCCURRED, error=str(e))
            return False

    def start_container(self) -> bool:
        """启动Docker容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container start")
                self.status = EnvironmentStatus.ACTIVE
                self.activated_at = datetime.now()
                self._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATED)
                return True

            if not self._container:
                if not self.create_container():
                    return False

            # 启动容器
            if self._container:
                self._container.start()

                # 等待容器就绪
                self._container.reload()
                if self._container.status != "running":
                    logger.error(f"Container failed to start: {self._container.status}")
                    return False

            self.status = EnvironmentStatus.ACTIVE
            self.activated_at = datetime.now()
            logger.info(f"Started Docker container: {self.container_id}")
            self._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATED)
            return True

        except DockerSDKException as e:
            logger.error(f"Failed to start container: {e}")
            self.status = EnvironmentStatus.ERROR
            self._emit_event(IsolationEvent.ERROR_OCCURRED, error=str(e))
            return False

    def stop_container(self) -> bool:
        """停止Docker容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container stop")
                self.status = EnvironmentStatus.INACTIVE
                self.deactivated_at = datetime.now()
                self._emit_event(IsolationEvent.ENVIRONMENT_DEACTIVATED)
                return True

            if not self._container:
                return True

            # 停止容器
            self._container.stop(timeout=self.config.get("stop_timeout", 30))

            self.status = EnvironmentStatus.INACTIVE
            self.deactivated_at = datetime.now()
            logger.info(f"Stopped Docker container: {self.container_id}")
            self._emit_event(IsolationEvent.ENVIRONMENT_DEACTIVATED)
            return True

        except DockerSDKException as e:
            logger.error(f"Failed to stop container: {e}")
            self._emit_event(IsolationEvent.ERROR_OCCURRED, error=str(e))
            return False

    def remove_container(self) -> bool:
        """删除Docker容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container removal")
                return True

            if not self._container:
                return True

            # 强制删除容器
            self._container.remove(force=True)
            self._container = None
            self.container_id = None

            logger.info(f"Removed Docker container: {self.container_name}")
            return True

        except DockerSDKException as e:
            logger.error(f"Failed to remove container: {e}")
            return False

    def activate(self) -> bool:
        """激活环境（启动容器）"""
        return self.start_container()

    def deactivate(self) -> bool:
        """停用环境（停止容器）"""
        return self.stop_container()

    def execute_command(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        env_vars: Optional[Dict[str, str]] = None,
        cwd: Optional[Path] = None,
    ) -> ProcessResult:
        """在Docker容器中执行命令"""
        start_time = datetime.now()

        try:
            if not DOCKER_AVAILABLE:
                # 模拟命令执行
                return ProcessResult(
                    returncode=0,
                    stdout="Docker simulation: command would be executed",
                    command=cmd,
                    start_time=start_time,
                    end_time=datetime.now(),
                )

            if not self._container or self.status != EnvironmentStatus.ACTIVE:
                return ProcessResult(
                    returncode=1,
                    stderr="Container is not running",
                    command=cmd,
                    start_time=start_time,
                    end_time=datetime.now(),
                )

            # 准备执行环境
            exec_env = self.environment_vars.copy()
            if env_vars:
                exec_env.update(env_vars)

            # 正确处理命令格式
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
            else:
                cmd_str = str(cmd)

            # 执行命令 - 使用正确的API
            if (
                self._container
                and hasattr(self._container, "client")
                and self._container.client
            ):
                exec_result = self._container.exec_run(
                    cmd_str,
                    environment=exec_env,
                    workdir=str(cwd or self.path),
                )

                exit_code = exec_result.exit_code
                stdout = (
                    exec_result.output.decode("utf-8") if exec_result.output else ""
                )
                stderr = ""  # exec_run combines output, for simplicity
            else:
                raise Exception("Container client not available")

            return ProcessResult(
                returncode=exit_code,
                stdout=stdout,
                stderr=stderr,
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
        """在容器中安装包"""
        try:
            package_spec = package
            if version:
                package_spec = f"{package}=={version}"

            # 构建pip命令
            cmd = ["pip", "install"]
            if upgrade:
                cmd.append("--upgrade")
            cmd.append(package_spec)

            # 执行安装
            result = self.execute_command(
                cmd, timeout=self.config.get("pip_timeout", 300)
            )

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
        """卸载容器中的包"""
        try:
            cmd = ["pip", "uninstall", "-y", package]

            result = self.execute_command(
                cmd, timeout=self.config.get("pip_timeout", 300)
            )

            if result.success:
                logger.info(f"Successfully uninstalled package: {package}")
                self._emit_event(
                    IsolationEvent.PACKAGE_INSTALLED, package=f"uninstalled:{package}"
                )
                return True
            else:
                logger.error(f"Failed to uninstall package {package}: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error uninstalling package {package}: {e}")
            return False

    def get_installed_packages(self) -> Dict[str, str]:
        """获取容器中已安装的包"""
        try:
            cmd = ["pip", "list", "--format=json"]
            result = self.execute_command(cmd, timeout=30)

            if result.success:
                packages = json.loads(result.stdout)
                return {pkg["name"].lower(): pkg["version"] for pkg in packages}
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
        """分配端口（映射到主机）"""
        import socket
        from contextlib import closing

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(("", 0))
            s.listen(1)
            host_port = s.getsockname()[1]

        # 映射到容器的标准端口（通常相同）
        container_port = host_port
        self.port_mappings[host_port] = container_port
        self.allocated_ports.append(host_port)

        logger.debug(f"Allocated port mapping: {host_port} -> {container_port}")
        return host_port

    def release_port(self, port: int) -> bool:
        """释放端口映射"""
        if port in self.allocated_ports:
            self.allocated_ports.remove(port)
            if port in self.port_mappings:
                del self.port_mappings[port]
            logger.debug(f"Released port mapping: {port}")
            return True
        return False

    def cleanup(self, force: bool = False) -> bool:
        """清理环境（删除容器和相关资源）"""
        try:
            # 停止容器
            if self.status == EnvironmentStatus.ACTIVE:
                self.stop_container()

            # 删除容器
            self.remove_container()

            # 清理网络和卷（如果有的话）
            if self._network:
                self._network.remove()
                self._network = None

            self.status = EnvironmentStatus.CLEANUP_COMPLETE
            self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_COMPLETE)
            return True

        except Exception as e:
            logger.error(f"Error cleaning up environment: {e}")
            if not force:
                self.status = EnvironmentStatus.ERROR
                return False
            return True

    def validate_isolation(self) -> bool:
        """验证Docker隔离有效性"""
        try:
            if not DOCKER_AVAILABLE:
                return True  # 模拟模式下总是有效

            if not self._container:
                return False

            # 检查容器状态
            self._container.reload()
            return self._container.status == "running"

        except Exception as e:
            logger.error(f"Error validating Docker isolation: {e}")
            return False

    def create_snapshot(self, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        """创建Docker环境快照"""
        from .base import IsolationStatus  # 避免循环导入

        if snapshot_id is None:
            snapshot_id = f"docker_snapshot_{int(self.created_at.timestamp())}"

        try:
            self.logger.info(
                f"Creating Docker snapshot {snapshot_id} for environment {self.env_id}"
            )

            # 基础快照信息
            snapshot = {
                "snapshot_id": snapshot_id,
                "env_id": self.env_id,
                "path": str(self.path),
                "status": self.status.value,
                "created_at": self.created_at.isoformat(),
                "config": self.config.copy(),
                "resource_usage": self.resource_usage.to_dict(),
                "allocated_ports": self.allocated_ports.copy(),
            }

            # Docker特有信息
            docker_info = {
                "container_name": self.container_name,
                "image_name": self.image_name,
                "container_id": self.container_id,
                "network_name": self.network_name,
                "volumes": self.volumes.copy(),
                "port_mappings": self.port_mappings.copy(),
                "environment_vars": self.environment_vars.copy(),
                "resource_limits": self.resource_limits.copy(),
            }

            # 如果容器运行，获取更多信息
            if (
                DOCKER_AVAILABLE
                and self._container
                and self.status == IsolationStatus.ACTIVE
            ):
                try:
                    self._container.reload()
                    container_state = self._container.attrs.get("State", {})

                    docker_info.update(
                        {
                            "container_state": {
                                "status": self._container.status,
                                "started_at": container_state.get("StartedAt"),
                                "finished_at": container_state.get("FinishedAt"),
                                "exit_code": container_state.get("ExitCode"),
                                "error": container_state.get("Error"),
                            },
                            "container_config": self._container.attrs.get("Config", {}),
                            "host_config": self._container.attrs.get("HostConfig", {}),
                            "network_settings": self._container.attrs.get(
                                "NetworkSettings", {}
                            ),
                        }
                    )

                    # 获取容器内的包列表（如果可能）
                    if hasattr(self, "get_installed_packages"):
                        try:
                            docker_info["installed_packages"] = (
                                self.get_installed_packages()
                            )
                        except:
                            pass

                except Exception as e:
                    self.logger.warning(f"Failed to get detailed container info: {e}")

            snapshot["docker_info"] = docker_info

            # 创建镜像快照（如果需要）
            if DOCKER_AVAILABLE and self.engine.docker_client:
                try:
                    # 提交容器为镜像
                    if self._container and self.status == IsolationStatus.ACTIVE:
                        snapshot_image_name = (
                            f"{self.container_name}_snapshot_{snapshot_id}"
                        )
                        image = self.engine.docker_client.images.create_from_container(
                            self.container_id,
                            {
                                "tag": snapshot_image_name,
                                "labels": {"snapshot_id": snapshot_id},
                            },
                        )
                        docker_info["snapshot_image"] = snapshot_image_name
                        docker_info["snapshot_image_id"] = image.id

                except Exception as e:
                    self.logger.warning(
                        f"Failed to create container image snapshot: {e}"
                    )

            self.logger.info(f"Successfully created Docker snapshot {snapshot_id}")
            return snapshot

        except Exception as e:
            self.logger.error(f"Failed to create Docker snapshot: {e}")
            raise

    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """从快照恢复Docker环境"""
        from .base import IsolationStatus

        snapshot_id = snapshot.get("snapshot_id")
        docker_info = snapshot.get("docker_info", {})

        try:
            self.logger.info(
                f"Restoring Docker environment {self.env_id} from snapshot {snapshot_id}"
            )

            # 清理现有环境
            if self.status != IsolationStatus.CREATED:
                self.cleanup()

            # 恢复基础配置
            self.config = snapshot.get("config", {})
            self.allocated_ports = snapshot.get("allocated_ports", [])

            # 恢复Docker特有配置
            if docker_info:
                self.container_name = docker_info.get(
                    "container_name", self.container_name
                )
                self.image_name = docker_info.get("image_name", self.image_name)
                self.network_name = docker_info.get("network_name", self.network_name)
                self.volumes = docker_info.get("volumes", {})
                self.port_mappings = docker_info.get("port_mappings", {})
                self.environment_vars = docker_info.get("environment_vars", {})
                self.resource_limits = docker_info.get("resource_limits", {})

            # 重新创建容器
            if self.create_container():
                # 激活环境
                if self.activate():
                    # 恢复包（如果有快照镜像）
                    snapshot_image = docker_info.get("snapshot_image")
                    if (
                        snapshot_image
                        and DOCKER_AVAILABLE
                        and self.engine.docker_client
                    ):
                        try:
                            self.logger.info(f"Using snapshot image: {snapshot_image}")
                            # 可以选择使用快照镜像而不是原镜像
                            pass
                        except Exception as e:
                            self.logger.warning(f"Failed to use snapshot image: {e}")

                    # 恢复包列表（如果存在）
                    if "installed_packages" in docker_info:
                        packages = docker_info["installed_packages"]
                        self.logger.info(
                            f"Restoring {len(packages)} packages from snapshot"
                        )

                        for package, version in packages.items():
                            try:
                                if not self.install_package(f"{package}=={version}"):
                                    self.logger.warning(
                                        f"Failed to restore package {package}=={version}"
                                    )
                            except Exception as e:
                                self.logger.warning(
                                    f"Failed to restore package {package}: {e}"
                                )

                    self.logger.info(
                        f"Successfully restored Docker environment from snapshot {snapshot_id}"
                    )
                    return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to restore from Docker snapshot: {e}")
            return False

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除Docker快照"""
        try:
            self.logger.info(f"Deleting Docker snapshot {snapshot_id}")

            # 清理快照镜像
            if DOCKER_AVAILABLE and self.engine.docker_client:
                try:
                    # 查找并删除快照镜像
                    images = self.engine.docker_client.images.list(
                        filters={"label": f"snapshot_id={snapshot_id}"}
                    )

                    for image in images:
                        self.logger.info(f"Deleting snapshot image: {image.id}")
                        self.engine.docker_client.images.remove(image.id, force=True)

                except Exception as e:
                    self.logger.warning(f"Failed to cleanup snapshot images: {e}")

            self.logger.info(f"Successfully deleted Docker snapshot {snapshot_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete Docker snapshot {snapshot_id}: {e}")
            return False

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """列出所有Docker快照"""
        snapshots = []

        try:
            # 查找所有快照镜像
            if DOCKER_AVAILABLE and self.engine.docker_client:
                images = self.engine.docker_client.images.list(
                    filters={"label": "snapshot_id"}
                )

                for image in images:
                    labels = image.labels or {}
                    snapshot_id = labels.get("snapshot_id")

                    if snapshot_id:
                        snapshot_info = {
                            "snapshot_id": snapshot_id,
                            "image_id": image.id,
                            "tags": image.tags,
                            "created": image.attrs.get("Created"),
                            "size": image.attrs.get("Size", 0),
                        }
                        snapshots.append(snapshot_info)

            return snapshots

        except Exception as e:
            self.logger.error(f"Failed to list Docker snapshots: {e}")
            return []

    def export_snapshot_data(self) -> Dict[str, Any]:
        """导出Docker环境数据"""
        try:
            return {
                "env_id": self.env_id,
                "env_type": "docker",
                "container_name": self.container_name,
                "image_name": self.image_name,
                "container_id": self.container_id,
                "network_name": self.network_name,
                "volumes": self.volumes,
                "port_mappings": self.port_mappings,
                "environment_vars": self.environment_vars,
                "resource_limits": self.resource_limits,
                "config": self.config,
                "allocated_ports": self.allocated_ports,
                "status": self.status.value,
                "created_at": self.created_at.isoformat(),
            }
        except Exception as e:
            self.logger.error(f"Failed to export snapshot data: {e}")
            return {}

            # 检查容器状态
            self._container.reload()

            # 如果容器应该是活跃的，检查它是否真的在运行
            if self.status == EnvironmentStatus.ACTIVE:
                return self._container.status == "running"

            return True

        except Exception as e:
            logger.error(f"Error validating isolation: {e}")
            return False

    def get_container_info(self) -> Dict[str, Any]:
        """获取容器详细信息"""
        if not DOCKER_AVAILABLE or not self._container:
            return {
                "container_id": self.container_id,
                "name": self.container_name,
                "image": self.image_name,
                "status": "simulated" if not DOCKER_AVAILABLE else "unknown",
            }

        self._container.reload()
        return {
            "container_id": self.container_id,
            "name": self.container_name,
            "image": self.image_name,
            "status": self._container.status,
            "created": self._container.attrs.get("Created"),
            "started": self._container.attrs.get("State", {}).get("StartedAt"),
            "ports": self._container.ports,
            "networks": list(
                self._container.attrs.get("NetworkSettings", {})
                .get("Networks", {})
                .keys()
            ),
        }


class DockerIsolationEngine(IsolationEngine):
    """Docker隔离引擎实现"""

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

    def initialize_client(self) -> bool:
        """初始化Docker客户端"""
        if not DOCKER_AVAILABLE:
            logger.warning("Docker SDK not available, running in simulation mode")
            return True

        with self._client_lock:
            if self.docker_client:
                return True

        try:
            # 初始化Docker客户端 - 修复参数问题
            import docker

            # 使用环境变量设置
            if "docker_host" in self.engine_config:
                os.environ["DOCKER_HOST"] = self.engine_config["docker_host"]

            self.docker_client = docker.from_env()
            self.api_client = docker.APIClient()

            # 验证连接
            if self.docker_client:
                self.docker_client.ping()
            logger.info("Docker client initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            return False

    def verify_docker_environment(self) -> Dict[str, Any]:
        """验证Docker环境"""
        if not DOCKER_AVAILABLE:
            return {
                "available": False,
                "reason": "Docker SDK not installed",
                "simulation_mode": True,
            }

        if not self.initialize_client():
            return {
                "available": False,
                "reason": "Failed to connect to Docker daemon",
                "simulation_mode": False,
            }

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
                    "available": False,
                    "reason": "Docker client not initialized",
                    "simulation_mode": False,
                }
        except DockerSDKException as e:
            return {"available": False, "reason": str(e), "simulation_mode": False}

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

            # 拉取镜像
            self.docker_client.images.pull(full_image_name)
            logger.info(f"Successfully pulled image: {full_image_name}")
            return True

        except DockerSDKException as e:
            logger.error(f"Failed to pull image {image_name}:{tag}: {e}")
            return False

    def create_network(self, network_name: str, subnet: str = None) -> Optional[Any]:
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
                if network_name:  # 确保network_name不为None
                    existing_network = self.docker_client.networks.get(network_name)
                    logger.info(f"Network {network_name} already exists")
                    return existing_network
            except:
                pass

            # 创建新网络 - 简化参数
            if network_name:  # 确保network_name不为None
                network = self.docker_client.networks.create(
                    network_name, driver="bridge"
                )
            else:
                return None

            logger.info(f"Created Docker network: {network_name}")
            return network

        except Exception as e:
            logger.error(f"Failed to create network {network_name}: {e}")
            return None

    def create_volume(self, volume_name: str) -> Optional[Any]:
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
                if volume_name:  # 确保volume_name不为None
                    existing_volume = self.docker_client.volumes.get(volume_name)
                    logger.info(f"Volume {volume_name} already exists")
                    return existing_volume
            except:
                pass

            # 创建新卷
            if volume_name:  # 确保volume_name不为None
                volume = self.docker_client.volumes.create(
                    name=volume_name, driver="local"
                )
            else:
                return None

            logger.info(f"Created Docker volume: {volume_name}")
            return volume

        except Exception as e:
            logger.error(f"Failed to create volume {volume_name}: {e}")
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

            # 创建新网络 - 简化参数
            if subnet:
                network = self.docker_client.networks.create(
                    network_name, driver="bridge"
                )
            else:
                network = self.docker_client.networks.create(
                    network_name, driver="bridge"
                )

            logger.info(f"Created Docker network: {network_name}")
            return network

        except DockerSDKException as e:
            logger.error(f"Failed to create network {network_name}: {e}")
            return None

    def create_volume(self, volume_name: str) -> Optional[Any]:
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
            volume = self.docker_client.volumes.create(name=volume_name, driver="local")

            logger.info(f"Created Docker volume: {volume_name}")
            return volume

        except Exception as e:
            logger.error(f"Failed to create volume {volume_name}: {e}")
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
            volume = self.docker_client.volumes.create(name=volume_name, driver="local")

            logger.info(f"Created Docker volume: {volume_name}")
            return volume

        except DockerSDKException as e:
            logger.error(f"Failed to create volume {volume_name}: {e}")
            return None

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
                "docker_environment": DOCKER_AVAILABLE,
            }
        )

        # 添加Docker特定属性
        if isinstance(env, DockerEnvironment):
            status.update(
                {
                    "container_name": env.container_name,
                    "image_name": env.image_name,
                    "network_name": env.network_name,
                    "container_info": env.get_container_info(),
                }
            )

        return status

    def validate_isolation(self, env: IsolatedEnvironment) -> bool:
        """验证隔离有效性"""
        if isinstance(env, DockerEnvironment):
            is_valid = env.validate_isolation()
            logger.debug(f"Validation result for {env.env_id}: {is_valid}")
            return is_valid
        else:
            logger.error(f"Invalid environment type for Docker engine: {type(env)}")
            return False

    def get_supported_features(self) -> List[str]:
        """获取支持的功能列表"""
        return self.supported_features.copy()

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        info = super().get_engine_info()
        info.update(
            {
                "engine_type": "docker",
                "docker_available": DOCKER_AVAILABLE,
                "docker_environment": self.verify_docker_environment(),
                "engine_config": self.engine_config,
            }
        )
        return info

    def list_available_images(self) -> List[str]:
        """列出可用的Docker镜像"""
        if not DOCKER_AVAILABLE:
            return ["python:3.9-slim (simulated)"]

        if not self.initialize_client():
            return []

        try:
            if self.docker_client:
                images = self.docker_client.images.list()
                image_names = []
                for image in images:
                    if hasattr(image, "tags") and image.tags:
                        image_names.extend(image.tags)
                return image_names
            else:
                return []
        except DockerSDKException as e:
            logger.error(f"Failed to list images: {e}")
            return []

    def cleanup_unused_resources(self) -> Dict[str, int]:
        """清理未使用的Docker资源"""
        if not DOCKER_AVAILABLE:
            logger.warning("Docker SDK not available, simulating resource cleanup")
            return {"containers": 0, "images": 0, "volumes": 0, "networks": 0}

        if not self.initialize_client():
            return {"containers": 0, "images": 0, "volumes": 0, "networks": 0}

        cleanup_counts = {"containers": 0, "images": 0, "volumes": 0, "networks": 0}

        try:
            if not self.docker_client:
                return cleanup_counts

            # 清理停止的容器
            stopped_containers = self.docker_client.containers.list(
                all=True, filters={"status": "exited"}
            )
            for container in stopped_containers:
                if hasattr(container, "name") and container.name.startswith("ptest_"):
                    container.remove()
                    cleanup_counts["containers"] += 1

            # 清理悬空镜像
            dangling_images = self.docker_client.images.list(filters={"dangling": True})
            for image in dangling_images:
                if hasattr(image, "id"):
                    self.docker_client.images.remove(image.id, force=True)
                    cleanup_counts["images"] += 1

            # 清理未使用的卷
            unused_volumes = self.docker_client.volumes.list(filters={"dangling": True})
            for volume in unused_volumes:
                if hasattr(volume, "name") and volume.name.startswith("ptest_"):
                    volume.remove()
                    cleanup_counts["volumes"] += 1

            # 清理未使用的网络
            unused_networks = self.docker_client.networks.list()
            for network in unused_networks:
                if (
                    hasattr(network, "name")
                    and hasattr(network, "containers")
                    and network.name.startswith("ptest_")
                    and len(network.containers) == 0
                ):
                    network.remove()
                    cleanup_counts["networks"] += 1

            logger.info(f"Cleaned up Docker resources: {cleanup_counts}")
            return cleanup_counts

        except DockerSDKException as e:
            logger.error(f"Failed to cleanup Docker resources: {e}")
            return cleanup_counts
