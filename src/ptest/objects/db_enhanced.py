# ptest/objects/db_enhanced.py
"""
增强的数据库对象 - 正确的服务端/客户端分离架构
"""

import shutil
import subprocess
import tarfile
from pathlib import Path

from .base import BaseManagedObject
from .db_server import DatabaseServerComponent
from .db_client import DatabaseClientComponent
from typing import Dict, Any, Optional, Tuple

try:
    from ..utils import get_colored_text
except ImportError:

    def get_colored_text(text: Any, color_code: Any) -> str:
        return str(text)


class DatabaseServerObject(BaseManagedObject):
    """数据库服务端对象"""

    def __init__(self, name: str, env_manager):
        super().__init__(name, "database_server", env_manager)
        self.server_component: Optional[DatabaseServerComponent] = None

    def install(self, params: Dict[str, Any] = None) -> str:  # type: ignore
        """安装数据库服务端"""
        if not params:
            return "✗ Database server installation requires parameters"

        self.env_manager.logger.info(f"Installing database server: {self.name}")

        db_type = str(params.get("db_type", "sqlite")).lower()
        if db_type == "mysql":
            return self._install_mysql_managed_instance(params)

        # 准备服务端配置
        server_config = {
            "db_type": db_type,
            "host": params.get("server_host", "localhost"),
            "port": params.get("server_port", self._get_default_port(db_type)),
            "data_dir": params.get("data_dir", f"/tmp/{self.name}_data"),
            "log_file": params.get("log_file", f"/tmp/{self.name}.log"),
            "pid_file": params.get("pid_file", f"/tmp/{self.name}.pid"),
            "config_file": params.get("config_file", ""),
        }

        # 添加数据库特定配置
        if "mysql_config" in params:
            server_config["mysql_config"] = params["mysql_config"]
        if "postgresql_config" in params:
            server_config["postgresql_config"] = params["postgresql_config"]
        if "mongodb_config" in params:
            server_config["mongodb_config"] = params["mongodb_config"]

        try:
            self.server_component = DatabaseServerComponent(server_config)
            self.installed = True
            self.status = "installed"

            db_type = server_config["db_type"]
            return f"✓ {get_colored_text('Database Server', 92)} object '{self.name}' ({db_type}) installed and ready"

        except Exception as e:
            return f"✗ Failed to install database server: {str(e)}"

    def _install_mysql_managed_instance(self, params: Dict[str, Any]) -> str:
        package_path_value = params.get("mysql_package_path")
        if not isinstance(package_path_value, str) or not package_path_value:
            return "✗ MySQL installation requires mysql_package_path"

        package_path = Path(package_path_value).expanduser().resolve()
        if not package_path.exists():
            return f"✗ MySQL package does not exist: {package_path}"
        if not package_path.is_file():
            return f"✗ MySQL package path is not a file: {package_path}"
        if not package_path.stat().st_size:
            return f"✗ MySQL package is empty: {package_path}"

        managed_instance = params.get("managed_instance", {})
        if not isinstance(managed_instance, dict):
            return "✗ Managed instance layout is missing for MySQL installation"

        required_dirs = (
            "instance_root",
            "install_dir",
            "data_dir",
            "config_dir",
            "lib_dir",
            "files_dir",
            "log_dir",
            "run_dir",
        )
        missing_dir_keys = [key for key in required_dirs if key not in managed_instance]
        if missing_dir_keys:
            joined = ", ".join(sorted(missing_dir_keys))
            return f"✗ Managed instance layout is incomplete: missing {joined}"

        instance_paths = {
            key: Path(str(managed_instance[key])).expanduser().resolve()
            for key in required_dirs
        }

        for path in instance_paths.values():
            path.mkdir(parents=True, exist_ok=True)
        instance_paths["files_dir"].chmod(0o700)

        config_file_value = params.get("config_file")
        if not isinstance(config_file_value, str) or not config_file_value:
            return "✗ MySQL managed instance requires config_file"
        config_file = Path(config_file_value).expanduser().resolve()
        config_file.parent.mkdir(parents=True, exist_ok=True)

        staged_package = instance_paths["install_dir"] / package_path.name
        if staged_package != package_path:
            shutil.copy2(package_path, staged_package)
        params["staged_package_path"] = str(staged_package.resolve())
        extracted_install_root, dependency_requirements = self._extract_mysql_package(
            staged_package=staged_package,
            install_dir=instance_paths["install_dir"],
        )
        params["dependency_requirements"] = dependency_requirements
        runtime_library_paths = self._prepare_mysql_dependencies(
            dependency_assets=params.get("dependency_assets", []),
            lib_dir=instance_paths["lib_dir"],
        )
        params["runtime_library_paths"] = runtime_library_paths
        params["mysql_binary"] = self._resolve_mysql_binary_path(extracted_install_root)

        mysql_config = {
            "max_connections": 100,
            "innodb_buffer_pool_size": "256M",
            **params.get("mysql_config", {}),
        }
        mysql_server_options = self._filter_mysql_server_options(mysql_config)

        config_content = self._build_mysql_config(
            host=str(params.get("server_host", "127.0.0.1")),
            port=int(params.get("server_port", self._get_default_port("mysql"))),
            data_dir=instance_paths["data_dir"],
            files_dir=instance_paths["files_dir"],
            log_file=Path(
                str(params.get("log_file", instance_paths["log_dir"] / "mysql.log"))
            ).resolve(),
            pid_file=Path(
                str(params.get("pid_file", instance_paths["run_dir"] / "mysql.pid"))
            ).resolve(),
            socket_file=Path(
                str(params.get("socket_file", instance_paths["run_dir"] / "mysql.sock"))
            ).resolve(),
            mysql_config=mysql_server_options,
        )
        config_file.write_text(config_content, encoding="utf-8")

        server_config = {
            "db_type": "mysql",
            "host": str(params.get("server_host", "127.0.0.1")),
            "port": int(params.get("server_port", self._get_default_port("mysql"))),
            "runtime_backend": str(params.get("runtime_backend", "host")),
            "data_dir": str(instance_paths["data_dir"]),
            "log_file": str(
                Path(
                    str(params.get("log_file", instance_paths["log_dir"] / "mysql.log"))
                ).resolve()
            ),
            "pid_file": str(
                Path(
                    str(params.get("pid_file", instance_paths["run_dir"] / "mysql.pid"))
                ).resolve()
            ),
            "socket_file": str(
                Path(
                    str(
                        params.get(
                            "socket_file",
                            instance_paths["run_dir"] / "mysql.sock",
                        )
                    )
                ).resolve()
            ),
            "config_file": str(config_file),
            "database_name": str(params.get("database_name", "ptest_mysql")),
            "mysql_config": mysql_config,
            "install_root": str(extracted_install_root),
            "managed_instance": {
                key: str(path) for key, path in instance_paths.items()
            },
            "source_asset": params.get("source_asset", {}),
            "staged_package_path": str(staged_package.resolve()),
            "mysql_binary": self._resolve_mysql_binary_path(extracted_install_root),
            "workspace_path": params.get("workspace_path", ""),
            "runtime_library_paths": runtime_library_paths,
            "dependency_assets": params.get("dependency_assets", []),
            "dependency_requirements": dependency_requirements,
        }

        try:
            self.server_component = DatabaseServerComponent(server_config)
            self.installed = True
            self.status = "installed"
            return (
                f"✓ {get_colored_text('Database Server', 92)} object '{self.name}' "
                f"(mysql) installed in managed workspace"
            )
        except Exception as e:
            return f"✗ Failed to install MySQL managed instance: {str(e)}"

    def _prepare_mysql_dependencies(
        self,
        *,
        dependency_assets: Any,
        lib_dir: Path,
    ) -> list[str]:
        if not isinstance(dependency_assets, list):
            return []
        lib_dir.mkdir(parents=True, exist_ok=True)
        runtime_library_paths: list[str] = []
        for item in dependency_assets:
            if not isinstance(item, dict):
                continue
            source_value = item.get("path")
            if not isinstance(source_value, str) or not source_value:
                continue
            source_path = Path(source_value).expanduser().resolve()
            if not source_path.exists():
                continue
            if source_path.is_file() and source_path.suffix == ".deb":
                extract_root = lib_dir / source_path.stem
                if extract_root.exists():
                    shutil.rmtree(extract_root)
                extract_root.mkdir(parents=True, exist_ok=True)
                self._extract_dependency_deb_package(source_path, extract_root)
                runtime_library_paths.extend(
                    self._discover_shared_library_dirs(extract_root)
                )
                continue
            target_path = lib_dir / source_path.name
            if source_path.is_dir():
                if target_path.exists():
                    shutil.rmtree(target_path)
                shutil.copytree(source_path, target_path)
                runtime_library_paths.extend(
                    self._discover_shared_library_dirs(target_path)
                )
            else:
                shutil.copy2(source_path, target_path)
                runtime_library_paths.append(str(lib_dir.resolve()))
        return list(dict.fromkeys(path for path in runtime_library_paths if path))

    def _extract_dependency_deb_package(
        self,
        package_path: Path,
        target_dir: Path,
    ) -> None:
        subprocess.run(
            ["dpkg-deb", "-x", str(package_path), str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

    def _discover_shared_library_dirs(self, root: Path) -> list[str]:
        if root.is_file():
            return [str(root.parent.resolve())] if ".so" in root.name else []

        library_dirs: list[str] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if ".so" not in path.name:
                continue
            directory = str(path.parent.resolve())
            if directory not in library_dirs:
                library_dirs.append(directory)
        return library_dirs

    def _build_mysql_config(
        self,
        *,
        host: str,
        port: int,
        data_dir: Path,
        files_dir: Path,
        log_file: Path,
        pid_file: Path,
        socket_file: Path,
        mysql_config: Dict[str, Any],
    ) -> str:
        lines = [
            "[mysqld]",
            f"bind-address={host}",
            f"port={port}",
            f"datadir={data_dir}",
            f"secure-file-priv={files_dir}",
            f"log-error={log_file}",
            f"pid-file={pid_file}",
            f"socket={socket_file}",
            "mysqlx=0",
            "skip-networking=0",
        ]
        for key, value in mysql_config.items():
            lines.append(f"{key}={value}")
        lines.append("")
        return "\n".join(lines)

    def _filter_mysql_server_options(
        self,
        mysql_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        reserved_keys = {"health_check_mode"}
        return {
            key: value
            for key, value in mysql_config.items()
            if key not in reserved_keys
        }

    def _extract_mysql_package(
        self, *, staged_package: Path, install_dir: Path
    ) -> tuple[Path, dict[str, Any]]:
        if staged_package.name.endswith(".deb-bundle.tar"):
            return self._extract_mysql_deb_bundle(
                staged_package=staged_package,
                install_dir=install_dir,
            )
        if tarfile.is_tarfile(staged_package):
            with tarfile.open(staged_package) as archive:
                archive.extractall(install_dir)
            extracted_roots = sorted(
                path
                for path in install_dir.iterdir()
                if path.is_dir() and path.name != "__MACOSX"
            )
            if len(extracted_roots) == 1:
                return extracted_roots[0], {}
            return install_dir, {}
        return install_dir, {}

    def _extract_mysql_deb_bundle(
        self, *, staged_package: Path, install_dir: Path
    ) -> tuple[Path, dict[str, Any]]:
        bundle_dir = install_dir / "_deb_bundle"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(staged_package) as archive:
            archive.extractall(bundle_dir)

        rootfs_dir = install_dir / "mysql-rootfs"
        rootfs_dir.mkdir(parents=True, exist_ok=True)

        package_names = {
            "server_core": "mysql-community-server-core_",
            "client_core": "mysql-community-client-core_",
            "common": "mysql-common_",
        }
        matched_packages: dict[str, Path] = {}
        for package_type, prefix in package_names.items():
            matches = sorted(bundle_dir.glob(f"{prefix}*.deb"))
            if matches:
                matched_packages[package_type] = matches[0]

        server_core = matched_packages.get("server_core")
        if server_core is None:
            raise FileNotFoundError(
                "MySQL DEB bundle is missing mysql-community-server-core package"
            )
        dependency_requirements = self._read_deb_dependency_requirements(server_core)

        for package in matched_packages.values():
            self._extract_deb_package(package, rootfs_dir)

        return rootfs_dir, dependency_requirements

    def _extract_deb_package(self, package_path: Path, rootfs_dir: Path) -> None:
        subprocess.run(
            ["dpkg-deb", "-x", str(package_path), str(rootfs_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

    def _read_deb_dependency_requirements(self, package_path: Path) -> dict[str, Any]:
        result = subprocess.run(
            ["dpkg-deb", "-f", str(package_path), "Depends"],
            check=True,
            capture_output=True,
            text=True,
        )
        raw_depends = result.stdout.strip()
        if not raw_depends:
            return {
                "package": package_path.name,
                "raw": "",
                "external_packages": [],
            }

        external_packages: list[str] = []
        for requirement in raw_depends.split(","):
            for alternative in requirement.split("|"):
                name = alternative.strip().split(" ", 1)[0]
                if name and name not in external_packages:
                    external_packages.append(name)

        return {
            "package": package_path.name,
            "raw": raw_depends,
            "external_packages": external_packages,
        }

    def _resolve_mysql_binary_path(self, install_root: Path) -> str:
        candidates = (
            install_root / "bin" / "mysqld",
            install_root / "bin" / "mysqld.cmd",
            install_root / "bin" / "mysqld.bat",
            install_root / "bin" / "mysqld.exe",
            install_root / "usr" / "sbin" / "mysqld",
            install_root / "usr" / "sbin" / "mysqld.cmd",
            install_root / "usr" / "sbin" / "mysqld.bat",
            install_root / "usr" / "sbin" / "mysqld.exe",
        )
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return str(candidates[0])

    def start(self) -> str:
        """启动数据库服务端"""
        if not self.installed or not self.server_component:
            return f"✗ Database server '{self.name}' not installed"

        self.env_manager.logger.info(f"Starting database server: {self.name}")

        try:
            success, message = self.server_component.start()
            if success:
                self.status = "running"
                return f"✓ {get_colored_text('Database Server', 92)} '{self.name}' started: {message}"
            else:
                return f"✗ Failed to start database server: {message}"
        except Exception as e:
            return f"✗ Server start error: {str(e)}"

    def stop(self) -> str:
        """停止数据库服务端"""
        if self.status != "running":
            return f"✗ Database server '{self.name}' not running"

        self.env_manager.logger.info(f"Stopping database server: {self.name}")

        try:
            success, message = self.server_component.stop()  # type: ignore
            if success:
                self.status = "stopped"
                return f"✓ {get_colored_text('Database Server', 92)} '{self.name}' stopped: {message}"
            else:
                return f"✗ Failed to stop database server: {message}"
        except Exception as e:
            return f"✗ Server stop error: {str(e)}"

    def restart(self) -> str:
        """重启数据库服务端"""
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result

    def uninstall(self) -> str:
        """卸载数据库服务端"""
        if self.status == "running":
            stop_result = self.stop()
            if "✓" not in stop_result:
                return stop_result

        self.env_manager.logger.info(f"Removing database server: {self.name}")

        try:
            managed_instance: dict[str, Any] = {}
            if self.server_component:
                if self.server_component.status == "running":
                    success, message = self.server_component.stop()
                    if not success:
                        return f"✗ Failed to stop database server during uninstall: {message}"
                config = getattr(self.server_component, "config", {})
                if isinstance(config, dict):
                    managed_instance = config.get("managed_instance", {})
                self.server_component = None

            if isinstance(managed_instance, dict):
                instance_root_value = managed_instance.get("instance_root")
                if isinstance(instance_root_value, str) and instance_root_value:
                    instance_root = Path(instance_root_value).expanduser().resolve()
                    if instance_root.exists():
                        shutil.rmtree(instance_root)

            self.installed = False
            self.status = "removed"
            return (
                f"✓ {get_colored_text('Database Server', 92)} '{self.name}' uninstalled"
            )
        except Exception as e:
            return f"✗ Server uninstall error: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        """获取服务端状态"""
        if not self.server_component:
            return {
                "name": self.name,
                "type_name": self.type_name,
                "status": self.status,
                "installed": self.installed,
                "message": "Server component not initialized",
            }

        return self.server_component.get_status()

    def health_check(self) -> str:
        """健康检查"""
        if not self.server_component:
            return f"✗ Database server '{self.name}' not installed"

        try:
            success, message = self.server_component.health_check()
            if success:
                return f"✓ {get_colored_text('Database Server', 92)} '{self.name}' healthy: {message}"
            else:
                return f"✗ {get_colored_text('Database Server', 91)} '{self.name}' unhealthy: {message}"
        except Exception as e:
            return f"✗ Health check error: {str(e)}"

    def get_endpoint(self) -> str:
        """获取服务端点"""
        if self.server_component:
            return self.server_component.get_endpoint()
        return ""

    def _get_default_port(self, db_type: str) -> int:
        """获取数据库默认端口"""
        port_mapping = {
            "mysql": 3306,
            "postgresql": 5432,
            "postgres": 5432,
            "mongodb": 27017,
            "oracle": 1521,
            "sqlserver": 1433,
            "redis": 6379,
        }
        return port_mapping.get(db_type.lower(), 0)


class DatabaseClientObject(BaseManagedObject):
    """数据库客户端对象"""

    def __init__(self, name: str, env_manager):
        super().__init__(name, "database_client", env_manager)
        self.client_component: Optional[DatabaseClientComponent] = None

    def install(self, params: Dict[str, Any] = None) -> str:  # type: ignore
        """安装数据库客户端"""
        if not params:
            return "✗ Database client installation requires parameters"

        self.env_manager.logger.info(f"Installing database client: {self.name}")

        # 准备客户端配置
        client_config = {
            "db_type": params.get("db_type", "sqlite"),
            "server_host": params.get("server_host", "localhost"),
            "server_port": params.get(
                "server_port", self._get_default_port(params.get("db_type", "sqlite"))
            ),
            "database": params.get("database", ""),
            "username": params.get("username", ""),
            "password": params.get("password", ""),
            "timeout": params.get("timeout", 30),
            "connection_params": params.get("connection_params", {}),
        }

        try:
            self.client_component = DatabaseClientComponent(client_config)
            self.installed = True
            self.status = "installed"

            db_type = client_config["db_type"]
            return f"✓ {get_colored_text('Database Client', 92)} object '{self.name}' ({db_type}) installed and ready"

        except Exception as e:
            return f"✗ Failed to install database client: {str(e)}"

    def start(self) -> str:
        """启动数据库客户端（建立连接）"""
        if not self.installed or not self.client_component:
            return f"✗ Database client '{self.name}' not installed"

        self.env_manager.logger.info(f"Starting database client: {self.name}")

        try:
            success, message = self.client_component.start()
            if success:
                self.status = "running"
                return f"✓ {get_colored_text('Database Client', 92)} '{self.name}' connected: {message}"
            else:
                return f"✗ Failed to connect database client: {message}"
        except Exception as e:
            return f"✗ Client start error: {str(e)}"

    def stop(self) -> str:
        """停止数据库客户端（断开连接）"""
        if self.status != "running":
            return f"✗ Database client '{self.name}' not running"

        self.env_manager.logger.info(f"Stopping database client: {self.name}")

        try:
            success, message = self.client_component.stop()  # type: ignore
            if success:
                self.status = "stopped"
                return f"✓ {get_colored_text('Database Client', 92)} '{self.name}' disconnected: {message}"
            else:
                return f"✗ Failed to disconnect database client: {message}"
        except Exception as e:
            return f"✗ Client stop error: {str(e)}"

    def restart(self) -> str:
        """重启数据库客户端"""
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result

    def uninstall(self) -> str:
        """卸载数据库客户端"""
        if self.status == "running":
            self.stop()

        self.env_manager.logger.info(f"Removing database client: {self.name}")

        try:
            if self.client_component:
                if self.client_component.status == "running":
                    self.client_component.stop()
                self.client_component = None

            self.installed = False
            self.status = "removed"
            return (
                f"✓ {get_colored_text('Database Client', 92)} '{self.name}' uninstalled"
            )
        except Exception as e:
            return f"✗ Client uninstall error: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        if not self.client_component:
            return {
                "name": self.name,
                "type_name": self.type_name,
                "status": self.status,
                "installed": self.installed,
                "message": "Client component not initialized",
            }

        return self.client_component.get_status()

    def health_check(self) -> str:
        """健康检查"""
        if not self.client_component:
            return f"✗ Database client '{self.name}' not installed"

        try:
            success, message = self.client_component.health_check()
            if success:
                return f"✓ {get_colored_text('Database Client', 92)} '{self.name}' healthy: {message}"
            else:
                return f"✗ {get_colored_text('Database Client', 91)} '{self.name}' unhealthy: {message}"
        except Exception as e:
            return f"✗ Health check error: {str(e)}"

    def execute_query(self, query: str) -> Tuple[bool, Any]:  # type: ignore
        """执行数据库查询"""
        if not self.installed or not self.client_component:
            return False, f"Database client '{self.name}' not properly installed"

        try:
            return self.client_component.execute_query(query)
        except Exception as e:
            return False, f"Query execution error: {str(e)}"

    def get_server_endpoint(self) -> str:
        """获取服务端点"""
        if self.client_component:
            return self.client_component.server_endpoint
        return ""

    def _get_default_port(self, db_type: str) -> int:
        """获取数据库默认端口"""
        port_mapping = {
            "mysql": 3306,
            "postgresql": 5432,
            "postgres": 5432,
            "mongodb": 27017,
            "oracle": 1521,
            "sqlserver": 1433,
            "redis": 6379,
        }
        return port_mapping.get(db_type.lower(), 0)
