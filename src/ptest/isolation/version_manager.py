"""
版本管理器实现

提供Python包版本检查、兼容性验证和安全更新功能
"""

import sys
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from packaging import version
from packaging.specifiers import SpecifierSet

from ..core import get_logger

logger = get_logger("version_manager")


@dataclass
class VersionInfo:
    """版本信息"""

    package: str
    current_version: str
    latest_version: str
    available_versions: List[str] = field(default_factory=list)
    release_date: Optional[datetime] = None
    is_prerelease: bool = False
    is_security_update: bool = False
    python_requires: Optional[str] = None
    deprecated_versions: List[str] = field(default_factory=list)

    def __post_init__(self):
        """标准化包名"""
        self.package = self.package.lower().replace("_", "-").replace(".", "-")


@dataclass
class CompatibilityResult:
    """兼容性检查结果"""

    package: str
    version: str
    is_compatible: bool
    python_version: str
    python_requires: Optional[str] = None
    conflicts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class SecurityAdvisory:
    """安全建议"""

    package: str
    affected_versions: List[str]
    fixed_version: Optional[str]
    severity: str  # "low", "medium", "high", "critical"
    cve_id: Optional[str] = None
    summary: str = ""
    published_date: Optional[datetime] = None
    references: List[str] = field(default_factory=list)


class VersionManager:
    """版本管理器"""

    def __init__(self, package_manager, config: Optional[Dict[str, Any]] = None):
        """
        初始化版本管理器

        Args:
            package_manager: 包管理器实例
            config: 配置选项
        """
        self.package_manager = package_manager
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "pypi_url": "https://pypi.org/pypi",
            "security_db_url": "https://pypi.org/pypi",
            "cache_enabled": True,
            "cache_ttl": 3600,  # 1小时
            "timeout": 30,
            "max_retries": 3,
            "allow_prereleases": False,
            "check_security": True,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        }

        # 合并配置
        self.config = {**self.default_config, **self.config}

        # 缓存
        self._version_cache: Dict[str, VersionInfo] = {}
        self._security_cache: Dict[str, List[SecurityAdvisory]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

    def get_latest_version(
        self, package: str, allow_prerelease: Optional[bool] = None
    ) -> Optional[str]:
        """
        获取包的最新版本

        Args:
            package: 包名
            allow_prerelease: 是否允许预发布版本

        Returns:
            最新版本或None
        """
        try:
            version_info = self.get_version_info(package, allow_prerelease)
            return version_info.latest_version if version_info else None

        except Exception as e:
            logger.error(f"Error getting latest version for {package}: {e}")
            return None

    def get_version_info(
        self,
        package: str,
        allow_prerelease: Optional[bool] = None,
        force_refresh: bool = False,
    ) -> Optional[VersionInfo]:
        """
        获取包的详细版本信息

        Args:
            package: 包名
            allow_prerelease: 是否允许预发布版本
            force_refresh: 是否强制刷新缓存

        Returns:
            版本信息或None
        """
        if allow_prerelease is None:
            allow_prerelease = self.config["allow_prereleases"]

        # 检查缓存
        cache_key = f"{package}:{allow_prerelease}"
        if (
            not force_refresh
            and self.config["cache_enabled"]
            and cache_key in self._version_cache
            and cache_key in self._cache_timestamps
        ):
            cache_age = (
                datetime.now() - self._cache_timestamps[cache_key]
            ).total_seconds()
            if cache_age < self.config["cache_ttl"]:
                logger.debug(f"Using cached version info for {package}")
                return self._version_cache[cache_key]

        try:
            # 从PyPI获取版本信息
            version_info = self._fetch_version_info_from_pypi(package, allow_prerelease)

            if version_info:
                # 缓存结果
                if self.config["cache_enabled"]:
                    self._version_cache[cache_key] = version_info
                    self._cache_timestamps[cache_key] = datetime.now()

                return version_info

        except Exception as e:
            logger.error(f"Error fetching version info for {package}: {e}")

        return None

    def _fetch_version_info_from_pypi(
        self, package: str, allow_prerelease: bool
    ) -> Optional[VersionInfo]:
        """
        从PyPI获取版本信息

        Args:
            package: 包名
            allow_prerelease: 是否允许预发布版本

        Returns:
            版本信息或None
        """
        try:
            url = f"{self.config['pypi_url']}/{package}/json"
            response = requests.get(url, timeout=self.config["timeout"])
            response.raise_for_status()

            data = response.json()
            releases = data.get("releases", {})
            info = data.get("info", {})

            # 获取所有版本并排序
            all_versions = list(releases.keys())
            all_versions.sort(key=version.parse, reverse=True)

            # 过滤预发布版本
            if not allow_prerelease:
                all_versions = [v for v in all_versions if not self._is_prerelease(v)]

            if not all_versions:
                return None

            latest_version = all_versions[0]

            # 检查是否为预发布版本
            is_prerelease = self._is_prerelease(latest_version)

            # 获取发布日期
            release_date = None
            if latest_version in releases and releases[latest_version]:
                release_date = (
                    datetime.fromisoformat(
                        releases[latest_version][0].get("upload_time", "")
                    ).replace(tzinfo=None)
                    if releases[latest_version][0].get("upload_time")
                    else None
                )

            return VersionInfo(
                package=package,
                current_version="",  # 将在调用处设置
                latest_version=latest_version,
                available_versions=all_versions,
                release_date=release_date,
                is_prerelease=is_prerelease,
                python_requires=info.get("requires_python"),
            )

        except requests.RequestException as e:
            logger.error(f"HTTP error fetching version info for {package}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing version info for {package}: {e}")
            return None

    def _is_prerelease(self, version_str: str) -> bool:
        """
        检查是否为预发布版本

        Args:
            version_str: 版本字符串

        Returns:
            是否为预发布版本
        """
        try:
            parsed_version = version.parse(version_str)
            return parsed_version.is_prerelease
        except Exception:
            # 简单检查版本字符串中的预发布标识符
            prerelease_patterns = ["alpha", "beta", "rc", "dev", "a", "b", "rc"]
            version_lower = version_str.lower()
            return any(pattern in version_lower for pattern in prerelease_patterns)

    def check_compatibility(
        self, package: str, target_version: str, python_version: Optional[str] = None
    ) -> CompatibilityResult:
        """
        检查版本兼容性

        Args:
            package: 包名
            target_version: 目标版本
            python_version: Python版本

        Returns:
            兼容性结果
        """
        if python_version is None:
            python_version = self.config["python_version"]

        conflicts = []
        warnings = []
        recommendations = []

        try:
            # 获取包信息
            version_info = self.get_version_info(package)
            if not version_info:
                return CompatibilityResult(
                    package=package,
                    version=target_version,
                    is_compatible=False,
                    python_version=python_version,
                    conflicts=["Package information not available"],
                )

            # 检查Python版本兼容性
            python_requires = version_info.python_requires
            is_python_compatible = True

            if python_requires:
                try:
                    specifier = SpecifierSet(python_requires)
                    is_python_compatible = specifier.contains(python_version)

                    if not is_python_compatible:
                        conflicts.append(
                            f"Requires Python {python_requires}, but {python_version} is installed"
                        )
                except Exception as e:
                    warnings.append(
                        f"Could not parse Python requirement: {python_requires} - {e}"
                    )

            # 检查版本是否存在
            if target_version not in version_info.available_versions:
                conflicts.append(f"Version {target_version} is not available")
            else:
                # 检查是否为已弃用版本
                if target_version in version_info.deprecated_versions:
                    warnings.append(f"Version {target_version} is deprecated")

                # 检查是否为预发布版本
                if self._is_prerelease(target_version):
                    warnings.append(f"Version {target_version} is a pre-release")

            # 生成建议
            if not is_python_compatible:
                recommendations.append(
                    "Upgrade Python version or use an older package version"
                )
            elif warnings:
                recommendations.append("Consider using the latest stable version")

            return CompatibilityResult(
                package=package,
                version=target_version,
                is_compatible=is_python_compatible and len(conflicts) == 0,
                python_version=python_version,
                python_requires=python_requires,
                conflicts=conflicts,
                warnings=warnings,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(
                f"Error checking compatibility for {package} {target_version}: {e}"
            )
            return CompatibilityResult(
                package=package,
                version=target_version,
                is_compatible=False,
                python_version=python_version,
                conflicts=[f"Error during compatibility check: {e}"],
            )

    def find_compatible_version(
        self,
        package: str,
        version_constraints: Optional[str] = None,
        python_version: Optional[str] = None,
    ) -> Optional[str]:
        """
        查找兼容版本

        Args:
            package: 包名
            version_constraints: 版本约束
            python_version: Python版本

        Returns:
            兼容版本或None
        """
        try:
            version_info = self.get_version_info(package)
            if not version_info:
                return None

            # 应用版本约束
            candidate_versions = version_info.available_versions.copy()

            if version_constraints:
                try:
                    specifier = SpecifierSet(version_constraints)
                    candidate_versions = [
                        v for v in candidate_versions if specifier.contains(v)
                    ]
                except Exception as e:
                    logger.warning(
                        f"Invalid version constraint: {version_constraints} - {e}"
                    )

            # 检查Python兼容性
            if python_version is None:
                python_version = self.config["python_version"]

            compatible_versions = []
            for candidate in candidate_versions:
                compatibility = self.check_compatibility(
                    package, candidate, python_version
                )
                if compatibility.is_compatible:
                    compatible_versions.append(candidate)

            # 返回最新的兼容版本
            if compatible_versions:
                compatible_versions.sort(key=version.parse, reverse=True)
                return compatible_versions[0]

        except Exception as e:
            logger.error(f"Error finding compatible version for {package}: {e}")

        return None

    def check_security_advisories(self, package: str) -> List[SecurityAdvisory]:
        """
        检查安全建议

        Args:
            package: 包名

        Returns:
            安全建议列表
        """
        if not self.config["check_security"]:
            return []

        # 检查缓存
        if (
            self.config["cache_enabled"]
            and package in self._security_cache
            and package in self._cache_timestamps
        ):
            cache_age = (
                datetime.now() - self._cache_timestamps[package]
            ).total_seconds()
            if cache_age < self.config["cache_ttl"]:
                logger.debug(f"Using cached security advisories for {package}")
                return self._security_cache[package]

        try:
            # 这里应该从安全数据库获取信息
            # 简化实现：返回一些示例安全建议
            advisories = self._fetch_security_advisories(package)

            # 缓存结果
            if self.config["cache_enabled"]:
                self._security_cache[package] = advisories
                self._cache_timestamps[package] = datetime.now()

            return advisories

        except Exception as e:
            logger.error(f"Error checking security advisories for {package}: {e}")
            return []

    def _fetch_security_advisories(self, package: str) -> List[SecurityAdvisory]:
        """
        获取安全建议（简化实现）

        Args:
            package: 包名

        Returns:
            安全建议列表
        """
        # 这里应该从真正的安全数据库获取信息
        # 简化实现：返回一些已知的安全问题
        known_advisories = {
            "requests": [
                SecurityAdvisory(
                    package="requests",
                    affected_versions=["<2.25.0"],
                    fixed_version="2.25.0",
                    severity="medium",
                    cve_id="CVE-2023-1234",
                    summary="Potential security vulnerability in URL parsing",
                    published_date=datetime(2023, 1, 15),
                )
            ],
            "urllib3": [
                SecurityAdvisory(
                    package="urllib3",
                    affected_versions=["<1.26.0"],
                    fixed_version="1.26.0",
                    severity="high",
                    cve_id="CVE-2023-5678",
                    summary="Certificate validation bypass",
                    published_date=datetime(2023, 2, 20),
                )
            ],
        }

        return known_advisories.get(package, [])

    def is_version_vulnerable(self, package: str, version_str: str) -> bool:
        """
        检查版本是否存在安全漏洞

        Args:
            package: 包名
            version_str: 版本字符串

        Returns:
            是否存在漏洞
        """
        try:
            advisories = self.check_security_advisories(package)

            for advisory in advisories:
                for affected_version in advisory.affected_versions:
                    if self._version_matches(version_str, affected_version):
                        return True

            return False

        except Exception as e:
            logger.error(
                f"Error checking vulnerability for {package} {version_str}: {e}"
            )
            return False

    def _version_matches(self, version_str: str, pattern: str) -> bool:
        """
        检查版本是否匹配模式

        Args:
            version_str: 版本字符串
            pattern: 版本模式

        Returns:
            是否匹配
        """
        try:
            if pattern.startswith("<"):
                target_version = pattern[1:].strip()
                return version.parse(version_str) < version.parse(target_version)
            elif pattern.startswith("<="):
                target_version = pattern[2:].strip()
                return version.parse(version_str) <= version.parse(target_version)
            elif pattern.startswith(">"):
                target_version = pattern[1:].strip()
                return version.parse(version_str) > version.parse(target_version)
            elif pattern.startswith(">="):
                target_version = pattern[2:].strip()
                return version.parse(version_str) >= version.parse(target_version)
            elif pattern.startswith("=="):
                target_version = pattern[2:].strip()
                return version.parse(version_str) == version.parse(target_version)
            else:
                return version_str == pattern

        except Exception:
            return version_str == pattern

    def get_update_recommendation(
        self, package: str, current_version: str
    ) -> Dict[str, Any]:
        """
        获取更新建议

        Args:
            package: 包名
            current_version: 当前版本

        Returns:
            更新建议
        """
        try:
            version_info = self.get_version_info(package)
            if not version_info:
                return {
                    "recommendation": "unknown",
                    "reason": "Version info not available",
                }

            # 检查是否有安全漏洞
            is_vulnerable = self.is_version_vulnerable(package, current_version)

            # 检查是否有新版本
            has_newer = version.parse(current_version) < version.parse(
                version_info.latest_version
            )

            # 生成建议
            if is_vulnerable:
                return {
                    "recommendation": "security_update",
                    "reason": "Current version has security vulnerabilities",
                    "target_version": version_info.latest_version,
                    "urgency": "high",
                }
            elif has_newer:
                # 检查新版本是否为预发布
                if version_info.is_prerelease:
                    return {
                        "recommendation": "optional_update",
                        "reason": "Newer pre-release version available",
                        "target_version": version_info.latest_version,
                        "urgency": "low",
                    }
                else:
                    return {
                        "recommendation": "recommended_update",
                        "reason": "Newer stable version available",
                        "target_version": version_info.latest_version,
                        "urgency": "medium",
                    }
            else:
                return {
                    "recommendation": "up_to_date",
                    "reason": "Package is up to date",
                    "urgency": "none",
                }

        except Exception as e:
            logger.error(f"Error getting update recommendation for {package}: {e}")
            return {"recommendation": "error", "reason": str(e)}

    def clear_cache(self) -> None:
        """清除缓存"""
        self._version_cache.clear()
        self._security_cache.clear()
        self._cache_timestamps.clear()
        logger.info("Version manager cache cleared")
