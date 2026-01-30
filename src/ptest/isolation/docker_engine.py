# ptest/isolation/docker_engine.py - 完善版本

import os
import sys
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Union, Callable, TYPE_CHECKING
from pathlib import Path
import logging
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

        except Exception as e:
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
            self._container.start()

            # 等待容器就绪
            self._container.reload()

            logger.info(f"Started Docker container: {self.container_id}")
            self.status = EnvironmentStatus.ACTIVE
            self.activated_at = datetime.now()
            self._emit_event(IsolationEvent.ENVIRONMENT_ACTIVATED)
            return True

        except Exception as e:
            logger.error(f"Failed to start container: {e}")
            self.status = EnvironmentStatus.ERROR
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
                logger.warning("No container to stop")
                return False

            # 停止容器
            self._container.stop()
            self._container.reload()

            logger.info(f"Stopped Docker container: {self.container_id}")
            self.status = EnvironmentStatus.INACTIVE
            self.deactivated_at = datetime.now()
            self._emit_event(IsolationEvent.ENVIRONMENT_DEACTIVATED)
            return True

        except Exception as e:
            logger.error(f"Failed to stop container: {e}")
            self.status = EnvironmentStatus.ERROR
            return False

    def remove_container(self) -> bool:
        """删除Docker容器"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning("Docker SDK not available, simulating container removal")
                self.status = EnvironmentStatus.CLEANUP_COMPLETE
                self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_COMPLETE)
                return True

            if not self._container:
                logger.warning("No container to remove")
                return False

            # 删除容器
            self._container.remove(force=True)
            self._container = None

            logger.info(f"Removed Docker container: {self.container_id}")
            self.status = EnvironmentStatus.CLEANUP_COMPLETE
            self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_COMPLETE)
            return True

        except Exception as e:
            logger.error(f"Failed to remove container: {e}")
            self.status = EnvironmentStatus.ERROR
            return False

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
                logger.warning(
                    f"Docker SDK not available, simulating command: {' '.join(cmd)}"
                )
                return ProcessResult(
                    returncode=0,
                    stdout="",
                    stderr="",
                    command=cmd,
                    timeout=timeout,
                    start_time=start_time,
                    end_time=datetime.now(),
                )

            if not self._container:
                if not self.start_container():
                    return ProcessResult(
                        returncode=1,
                        stderr="Container not available",
                        command=cmd,
                        timeout=timeout,
                        start_time=start_time,
                        end_time=datetime.now(),
                    )

            # 准备执行环境
            exec_env = self.environment_vars.copy()
            if env_vars:
                exec_env.update(env_vars)

            # 执行命令
            exit_code, output = self._container.exec_run(
                cmd,
                environment=exec_env,
                workdir=str(cwd or self.path),
                demux=False,
            )

            result = ProcessResult(
                returncode=exit_code,
                stdout=output,
                stderr="",
                command=cmd,
                timeout=timeout,
                start_time=start_time,
                end_time=datetime.now(),
            )

            if result.success:
                logger.info(f"Command executed successfully: {' '.join(cmd)}")
            else:
                logger.error(f"Command failed: {' '.join(cmd)}")

            return result

        except Exception as e:
            logger.error(f"Failed to execute command: {e}")
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
        """在Docker容器中安装包"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating package installation: {package}"
                )
                return True

            # 构建安装命令
            package_spec = f"{package}{f'=={version}' if version else ''}"
            install_cmd = ["pip", "install"]
            if upgrade:
                install_cmd.append("--upgrade")
            install_cmd.append(package_spec)

            # 执行安装命令
            result = self.execute_command(install_cmd, timeout=300)
            self._emit_event(IsolationEvent.PACKAGE_INSTALLED, package=package_spec)

            return result.success

        except Exception as e:
            logger.error(f"Failed to install package {package}: {e}")
            return False

    def uninstall_package(self, package: str) -> bool:
        """在Docker容器中卸载包"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating package uninstallation: {package}"
                )
                return True

            # 执行卸载命令
            uninstall_cmd = ["pip", "uninstall", "-y", package]
            result = self.execute_command(uninstall_cmd, timeout=120)
            self._emit_event(IsolationEvent.PACKAGE_INSTALLED, package=package)

            return result.success

        except Exception as e:
            logger.error(f"Failed to uninstall package {package}: {e}")
            return False

    def get_installed_packages(self) -> Dict[str, str]:
        """获取已安装的包列表"""
        try:
            if not DOCKER_AVAILABLE:
                return {}

            if not self._container:
                return {}

            # 执行pip list命令
            result = self.execute_command(["pip", "list", "--format=json"], timeout=30)

            if result.success:
                packages = {}
                import json

                try:
                    package_list = json.loads(result.stdout)
                    for pkg in package_list:
                        packages[pkg["name"]] = pkg["version"]
                    return packages
                except:
                    logger.warning("Failed to parse package list output")
                    return {}
            else:
                logger.error("Failed to get package list")
                return {}

        except Exception as e:
            logger.error(f"Error getting package list: {e}")
            return {}

    def get_package_version(self, package: str) -> Optional[str]:
        """获取特定包的版本"""
        packages = self.get_installed_packages()
        return packages.get(package)

    def allocate_port(self) -> int:
        """分配端口"""
        # 在模拟模式下，使用简单的端口分配策略
        if not DOCKER_AVAILABLE:
            import socket

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.bind(("", 0))
                s.listen(1)
                port = s.getsockname()[1]
            self.allocated_ports.append(port)
            return port

    def release_port(self, port: int) -> bool:
        """释放端口"""
        if port in self.allocated_ports:
            self.allocated_ports.remove(port)
            return True
        return False

    def activate(self) -> bool:
        """激活环境（启动容器）"""
        return self.start_container()

    def deactivate(self) -> bool:
        """停用环境（停止容器）"""
        return self.stop_container()

    def cleanup(self, force: bool = False) -> bool:
        """清理Docker环境"""
        try:
            # 先停止容器
            if self._container:
                self.stop_container()

            # 删除容器
            self.remove_container()

            # 清理网络和卷（如果需要）
            if self.network_name:
                try:
                    if (
                        hasattr(self.isolation_engine, "docker_client")
                        and self.isolation_engine.docker_client
                    ):
                        networks = self.isolation_engine.docker_client.networks.list(
                            names=[self.network_name]
                        )
                        for network in networks:
                            try:
                                network.remove()
                                logger.info(f"Removed Docker network: {network.name}")
                            except:
                                pass
                except Exception as e:
                    logger.error(f"Error cleaning up network {self.network_name}: {e}")

            for volume_name in self.volumes.keys():
                try:
                    if (
                        hasattr(self.isolation_engine, "docker_client")
                        and self.isolation_engine.docker_client
                    ):
                        volumes = self.isolation_engine.docker_client.volumes.list(
                            filters={"name": volume_name}
                        )
                        for volume in volumes:
                            try:
                                volume.remove()
                                logger.info(f"Removed Docker volume: {volume_name}")
                            except:
                                pass
                except Exception as e:
                    logger.error(f"Error cleaning up volume {volume_name}: {e}")

            self.status = EnvironmentStatus.CLEANUP_COMPLETE
            self._emit_event(IsolationEvent.ENVIRONMENT_CLEANUP_COMPLETE)
            return True

        except Exception as e:
            logger.error(f"Error cleaning up Docker environment: {e}")
            if not force:
                self.status = EnvironmentStatus.ERROR
                return False
            return True

    def validate_isolation(self) -> bool:
        """验证隔离有效性"""
        try:
            if not DOCKER_AVAILABLE:
                return False

            if not self._container:
                return False

            # 检查容器状态
            self._container.reload()
            status = self._container.status
            return status in ("running", "exited")

        except Exception as e:
            logger.error(f"Error validating Docker isolation: {e}")
            return False

    def create_snapshot(self, snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        """创建Docker环境快照"""
        try:
            if snapshot_id is None:
                timestamp = int(time.time())
                snapshot_id = f"docker_snapshot_{timestamp}_{uuid.uuid4().hex[:8]}"

            self.logger.info(f"Creating Docker snapshot {snapshot_id}")

            # 收集Docker特有状态
            docker_info = {
                "container_id": self.container_id,
                "container_name": self.container_name,
                "image_name": self.image_name,
                "network_name": self.network_name,
                "volumes": dict(self.volumes),
                "port_mappings": dict(self.port_mappings),
                "environment_vars": dict(self.environment_vars),
                "resource_limits": dict(self.resource_limits),
                "created_at": self.activated_at.isoformat()
                if self.activated_at
                else None,
                "container_status": self._container.status if self._container else None,
            }

            snapshot_data = {
                "snapshot_id": snapshot_id,
                "env_id": self.env_id,
                "created_at": datetime.now().isoformat(),
                "env_type": "docker",
                "docker_info": docker_info,
            }

            self._emit_event(IsolationEvent.SNAPSHOT_CREATED, snapshot_id=snapshot_id)
            self.logger.info(f"Successfully created Docker snapshot {snapshot_id}")
            return snapshot_data

        except Exception as e:
            self.logger.error(f"Failed to create Docker snapshot: {e}")
            raise

    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """从快照恢复Docker环境"""
        try:
            snapshot_id = snapshot.get("snapshot_id")
            self.logger.info(
                f"Restoring Docker environment {self.env_id} from snapshot {snapshot_id}"
            )

            docker_info = snapshot.get("docker_info", {})

            # 恢复Docker特有配置
            self.image_name = docker_info.get("image_name", self.image_name)
            self.network_name = docker_info.get("network_name", "")
            self.volumes = docker_info.get("volumes", {})
            self.port_mappings = docker_info.get("port_mappings", {})
            self.environment_vars = docker_info.get("environment_vars", {})
            self.resource_limits = docker_info.get("resource_limits", {})

            # 创建并配置容器
            if not self.create_container():
                return False

            # 启动容器
            if not self.start_container():
                return False

            self._emit_event(IsolationEvent.SNAPSHOT_RESTORED, snapshot_id=snapshot_id)
            self.logger.info(
                f"Successfully restored Docker environment from snapshot {snapshot_id}"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to restore from Docker snapshot {snapshot_id}: {e}"
            )
            return False

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除Docker快照"""
        # Docker快照主要是内存中的配置，不需要特殊清理
        try:
            self.logger.info(f"Deleting Docker snapshot {snapshot_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete Docker snapshot {snapshot_id}: {e}")
            return False

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """列出所有快照"""
        # Docker环境的快照由管理器管理
        return []

    def get_container_info(self) -> Dict[str, Any]:
        """获取容器信息"""
        try:
            if not self._container:
                return {
                    "container_id": None,
                    "container_name": self.container_name,
                    "status": "not_created",
                    "image": self.image_name,
                }

            self._container.reload()

            return {
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
                "container_id": self.container_id,
                "container_name": self.container_name,
                "status": "error",
                "error": str(e),
                "image": self.image_name,
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
            volume_config = {
                "Name": volume_name,
                "Driver": "local",
                "Labels": {"created_by": "ptest", "purpose": "test_isolation"},
            }

            volume = self.docker_client.volumes.create(volume_config)
            logger.info(f"Created Docker volume: {volume_name}")
            return volume

        except Exception as e:
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
