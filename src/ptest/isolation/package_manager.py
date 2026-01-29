"""
高级包管理器实现

提供完整的Python包管理功能，包括安装、卸载、升级、依赖解析等
"""

import os
import sys
import json
import subprocess
import re
from typing import Dict, List, Optional, Set, Tuple, Any, Union
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from packaging import version
from packaging.requirements import Requirement

from core import get_logger

logger = get_logger("package_manager")


@dataclass
class PackageInfo:
    """包信息数据类"""

    name: str
    version: str
    location: Optional[str] = None
    requires: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    installed_at: Optional[datetime] = None

    def __post_init__(self):
        """标准化包名"""
        self.name = self.name.lower().replace("_", "-").replace(".", "-")


@dataclass
class InstallResult:
    """安装结果数据类"""

    success: bool
    package: str
    version: Optional[str] = None
    message: str = ""
    dependencies_installed: List[str] = field(default_factory=list)
    conflicts_resolved: List[str] = field(default_factory=list)
    install_time: float = 0.0
    error_details: Optional[str] = None


@dataclass
class UninstallResult:
    """卸载结果数据类"""

    success: bool
    package: str
    message: str = ""
    removed_dependencies: List[str] = field(default_factory=list)
    uninstall_time: float = 0.0
    error_details: Optional[str] = None


class AdvancedPackageManager:
    """高级包管理器"""

    def __init__(self, venv_path: Path, config: Optional[Dict[str, Any]] = None):
        """
        初始化包管理器

        Args:
            venv_path: 虚拟环境路径
            config: 配置选项
        """
        self.venv_path = venv_path
        self.python_path = venv_path / "bin" / "python"
        self.pip_path = venv_path / "bin" / "pip"
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "install_timeout": 300,
            "uninstall_timeout": 120,
            "upgrade_timeout": 300,
            "list_timeout": 30,
            "show_timeout": 30,
            "use_cache": True,
            "cache_dir": venv_path / ".pip_cache",
            "index_url": None,
            "extra_index_urls": [],
            "trusted_hosts": [],
            "no_deps": False,
            "prefer_binary": False,
            "compile": False,
            "no_compile": False,
            "ignore_requires_python": False,
            "progress_bar": True,
        }

        # 合并配置
        self.config = {**self.default_config, **self.config}

        # 创建缓存目录
        if self.config["use_cache"]:
            self.config["cache_dir"].mkdir(parents=True, exist_ok=True)

        # 已安装包缓存
        self._installed_packages_cache: Optional[Dict[str, PackageInfo]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 60  # 缓存有效期60秒

    def install_package(
        self,
        package: str,
        version_spec: Optional[str] = None,
        upgrade: bool = False,
        force_reinstall: bool = False,
        ignore_deps: Optional[bool] = None,
        editable: bool = False,
        constraints: Optional[List[str]] = None,
        requirements_file: Optional[Path] = None,
    ) -> InstallResult:
        """
        安装Python包

        Args:
            package: 包名或包规格
            version_spec: 版本规格 (如 ">=1.0.0,<2.0.0")
            upgrade: 是否升级已安装的包
            force_reinstall: 是否强制重新安装
            ignore_deps: 是否忽略依赖
            editable: 是否以可编辑模式安装
            constraints: 约束条件列表
            requirements_file: requirements文件路径

        Returns:
            安装结果
        """
        start_time = datetime.now()

        try:
            # 构建安装命令
            cmd = [str(self.pip_path), "install"]

            # 添加选项
            if upgrade:
                cmd.append("--upgrade")

            if force_reinstall:
                cmd.append("--force-reinstall")

            if ignore_deps or self.config["no_deps"]:
                cmd.append("--no-deps")

            if editable:
                cmd.append("-e")

            if self.config["prefer_binary"]:
                cmd.append("--prefer-binary")

            if self.config["compile"]:
                cmd.append("--compile")
            elif self.config["no_compile"]:
                cmd.append("--no-compile")

            if self.config["ignore_requires_python"]:
                cmd.append("--ignore-requires-python")

            # 添加索引配置
            if self.config["index_url"]:
                cmd.extend(["--index-url", self.config["index_url"]])

            for extra_index in self.config["extra_index_urls"]:
                cmd.extend(["--extra-index-url", extra_index])

            for host in self.config["trusted_hosts"]:
                cmd.extend(["--trusted-host", host])

            # 添加缓存配置
            if self.config["use_cache"]:
                cmd.extend(["--cache-dir", str(self.config["cache_dir"])])
            else:
                cmd.append("--no-cache-dir")

            # 添加约束条件
            if constraints:
                for constraint in constraints:
                    cmd.extend(["--constraint", constraint])

            # 添加包规格
            if requirements_file:
                cmd.extend(["-r", str(requirements_file)])
            else:
                package_spec = package
                if version_spec:
                    package_spec = f"{package}{version_spec}"
                cmd.append(package_spec)

            # 执行安装
            logger.info(f"Installing package: {package_spec}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config["install_timeout"],
            )

            install_time = (datetime.now() - start_time).total_seconds()

            if result.returncode == 0:
                # 解析安装结果
                installed_packages = self._parse_install_output(result.stdout)
                dependencies_installed = [
                    p for p in installed_packages if p.lower() != package.lower()
                ]

                # 获取安装的版本
                installed_version = self._get_installed_version(package)

                # 清除缓存
                self._clear_cache()

                logger.info(f"Successfully installed {package} v{installed_version}")
                return InstallResult(
                    success=True,
                    package=package,
                    version=installed_version,
                    dependencies_installed=dependencies_installed,
                    install_time=install_time,
                    message=f"Successfully installed {package} v{installed_version}",
                )
            else:
                # 解析错误信息
                error_details = self._parse_install_error(result.stderr)
                logger.error(f"Failed to install {package}: {error_details}")
                return InstallResult(
                    success=False,
                    package=package,
                    install_time=install_time,
                    message=f"Failed to install {package}",
                    error_details=error_details,
                )

        except subprocess.TimeoutExpired:
            install_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Package installation timed out: {package}")
            return InstallResult(
                success=False,
                package=package,
                install_time=install_time,
                message="Installation timed out",
                error_details=f"Installation exceeded timeout of {self.config['install_timeout']} seconds",
            )

        except Exception as e:
            install_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Unexpected error installing {package}: {e}")
            return InstallResult(
                success=False,
                package=package,
                install_time=install_time,
                message="Unexpected error during installation",
                error_details=str(e),
            )

    def uninstall_package(
        self,
        package: str,
        yes: bool = True,
        clean_deps: bool = False,
    ) -> UninstallResult:
        """
        卸载Python包

        Args:
            package: 包名
            yes: 是否自动确认
            clean_deps: 是否同时卸载不再需要的依赖

        Returns:
            卸载结果
        """
        start_time = datetime.now()

        try:
            # 检查包是否已安装
            if not self.is_package_installed(package):
                uninstall_time = (datetime.now() - start_time).total_seconds()
                return UninstallResult(
                    success=False,
                    package=package,
                    uninstall_time=uninstall_time,
                    message="Package not installed",
                    error_details=f"Package '{package}' is not installed in the environment",
                )

            # 获取卸载前的依赖信息
            removed_dependencies = []
            if clean_deps:
                removed_dependencies = self._get_orphaned_dependencies(package)

            # 构建卸载命令
            cmd = [str(self.pip_path), "uninstall"]

            if yes:
                cmd.append("-y")

            if clean_deps:
                cmd.append("--yes")

            cmd.append(package)

            # 执行卸载
            logger.info(f"Uninstalling package: {package}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config["uninstall_timeout"],
            )

            uninstall_time = (datetime.now() - start_time).total_seconds()

            if result.returncode == 0:
                # 清除缓存
                self._clear_cache()

                logger.info(f"Successfully uninstalled {package}")
                return UninstallResult(
                    success=True,
                    package=package,
                    removed_dependencies=removed_dependencies,
                    uninstall_time=uninstall_time,
                    message=f"Successfully uninstalled {package}",
                )
            else:
                error_details = result.stderr
                logger.error(f"Failed to uninstall {package}: {error_details}")
                return UninstallResult(
                    success=False,
                    package=package,
                    uninstall_time=uninstall_time,
                    message=f"Failed to uninstall {package}",
                    error_details=error_details,
                )

        except subprocess.TimeoutExpired:
            uninstall_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Package uninstallation timed out: {package}")
            return UninstallResult(
                success=False,
                package=package,
                uninstall_time=uninstall_time,
                message="Uninstallation timed out",
                error_details=f"Uninstallation exceeded timeout of {self.config['uninstall_timeout']} seconds",
            )

        except Exception as e:
            uninstall_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Unexpected error uninstalling {package}: {e}")
            return UninstallResult(
                success=False,
                package=package,
                uninstall_time=uninstall_time,
                message="Unexpected error during uninstallation",
                error_details=str(e),
            )

    def upgrade_package(
        self,
        package: str,
        to_version: Optional[str] = None,
        force: bool = False,
    ) -> InstallResult:
        """
        升级Python包

        Args:
            package: 包名
            to_version: 目标版本 (None表示升级到最新版本)
            force: 是否强制升级

        Returns:
            升级结果
        """
        package_spec = package
        if to_version:
            package_spec = f"{package}=={to_version}"

        return self.install_package(
            package=package_spec, upgrade=True, force_reinstall=force
        )

    def list_packages(self, include_outdated: bool = False) -> Dict[str, PackageInfo]:
        """
        列出已安装的包

        Args:
            include_outdated: 是否包含过时包信息

        Returns:
            包信息字典
        """
        # 检查缓存
        if (
            self._installed_packages_cache is not None
            and self._cache_timestamp is not None
            and (datetime.now() - self._cache_timestamp).total_seconds()
            < self._cache_ttl
        ):
            return self._installed_packages_cache

        try:
            # 获取包列表
            cmd = [str(self.pip_path), "list", "--format=json"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config["list_timeout"],
            )

            if result.returncode != 0:
                logger.error(f"Failed to list packages: {result.stderr}")
                return {}

            packages_data = json.loads(result.stdout)
            packages = {}

            for pkg_data in packages_data:
                package_info = PackageInfo(
                    name=pkg_data["name"],
                    version=pkg_data["version"],
                )

                # 获取详细信息
                detailed_info = self.get_package_details(package_info.name)
                if detailed_info:
                    package_info.requires = detailed_info.get("requires", [])
                    package_info.metadata = detailed_info.get("metadata", {})
                    package_info.location = detailed_info.get("location")

                packages[package_info.name] = package_info

            # 更新缓存
            self._installed_packages_cache = packages
            self._cache_timestamp = datetime.now()

            return packages

        except Exception as e:
            logger.error(f"Error listing packages: {e}")
            return {}

    def get_package_details(self, package: str) -> Optional[Dict[str, Any]]:
        """
        获取包详细信息

        Args:
            package: 包名

        Returns:
            包详细信息
        """
        try:
            cmd = [str(self.pip_path), "show", package]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config["show_timeout"],
            )

            if result.returncode != 0:
                return None

            # 解析show输出
            details = {}
            for line in result.stdout.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    details[key.strip().lower()] = value.strip()

            # 处理特殊字段
            if "requires" in details and details["requires"]:
                details["requires"] = [
                    req.strip() for req in details["requires"].split(",")
                ]
            else:
                details["requires"] = []

            return details

        except Exception as e:
            logger.error(f"Error getting package details for {package}: {e}")
            return None

    def is_package_installed(self, package: str) -> bool:
        """
        检查包是否已安装

        Args:
            package: 包名

        Returns:
            是否已安装
        """
        packages = self.list_packages()
        return package.lower() in packages

    def get_package_version(self, package: str) -> Optional[str]:
        """
        获取包版本

        Args:
            package: 包名

        Returns:
            包版本
        """
        packages = self.list_packages()
        package_info = packages.get(package.lower())
        return package_info.version if package_info else None

    def freeze_requirements(self) -> str:
        """
        生成requirements.txt格式的内容

        Returns:
            requirements内容
        """
        try:
            cmd = [str(self.pip_path), "freeze"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config["list_timeout"],
            )

            if result.returncode == 0:
                return result.stdout
            else:
                logger.error(f"Failed to freeze requirements: {result.stderr}")
                return ""

        except Exception as e:
            logger.error(f"Error freezing requirements: {e}")
            return ""

    def check_outdated(self) -> List[Dict[str, str]]:
        """
        检查过时的包

        Returns:
            过时包列表
        """
        try:
            cmd = [str(self.pip_path), "list", "--outdated", "--format=json"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config["list_timeout"],
            )

            if result.returncode != 0:
                logger.error(f"Failed to check outdated packages: {result.stderr}")
                return []

            outdated_data = json.loads(result.stdout)
            return [
                {
                    "name": pkg["name"],
                    "current_version": pkg["version"],
                    "latest_version": pkg["latest_version"],
                    "type": pkg.get("type", "pip"),
                }
                for pkg in outdated_data
            ]

        except Exception as e:
            logger.error(f"Error checking outdated packages: {e}")
            return []

    def _parse_install_output(self, output: str) -> List[str]:
        """解析安装输出，提取安装的包名"""
        installed_packages = []

        # 查找 "Successfully installed" 行
        for line in output.split("\n"):
            if line.startswith("Successfully installed"):
                # 提取包名
                packages = line.replace("Successfully installed", "").strip().split()
                installed_packages.extend(packages)
                break

        return installed_packages

    def _parse_install_error(self, stderr: str) -> str:
        """解析安装错误信息"""
        # 查找主要错误信息
        error_lines = stderr.split("\n")
        for line in error_lines:
            line = line.strip()
            if line.startswith("ERROR:"):
                return line
            elif "Could not find" in line:
                return line
            elif "conflict" in line.lower():
                return line

        return stderr.strip()

    def _get_installed_version(self, package: str) -> Optional[str]:
        """获取已安装包的版本"""
        try:
            cmd = [str(self.pip_path), "show", package]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()

        except Exception:
            pass

        return None

    def _get_orphaned_dependencies(self, package: str) -> List[str]:
        """获取将成为孤立依赖的包列表"""
        # 这是一个简化实现，实际应用中可能需要更复杂的依赖图分析
        try:
            # 获取当前包的依赖
            package_details = self.get_package_details(package)
            if not package_details:
                return []

            direct_deps = set(package_details.get("requires", []))
            orphaned = []

            # 检查每个依赖是否被其他包需要
            for dep in direct_deps:
                dep_name = (
                    dep.split(">")[0]
                    .split("<")[0]
                    .split("==")[0]
                    .split(">=")[0]
                    .split("<=")[0]
                    .strip()
                )
                required_by_others = False

                for other_package, other_info in self.list_packages().items():
                    if other_package.lower() != package.lower():
                        other_requires = set(other_info.requires)
                        if dep_name.lower() in [
                            r.lower().split(">")[0].split("<")[0].split("==")[0].strip()
                            for r in other_requires
                        ]:
                            required_by_others = True
                            break

                if not required_by_others:
                    orphaned.append(dep_name)

            return orphaned

        except Exception as e:
            logger.error(f"Error finding orphaned dependencies: {e}")
            return []

    def _clear_cache(self) -> None:
        """清除包信息缓存"""
        self._installed_packages_cache = None
        self._cache_timestamp = None
