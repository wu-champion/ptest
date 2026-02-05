"""
版本冲突检测器实现

提供Python包版本冲突检测、分析和解决功能
"""

import sys
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet, InvalidSpecifier

from ..core import get_logger

logger = get_logger("conflict_detector")


@dataclass
class VersionConflict:
    """版本冲突"""

    package: str
    conflict_type: str  # "direct", "transitive", "incompatible"
    conflicting_requirements: List[
        Tuple[str, str, str]
    ]  # (version_spec, source, reason)
    severity: str  # "error", "warning", "info"
    suggested_resolution: Optional[str] = None
    affected_packages: Set[str] = field(default_factory=set)
    error_message: str = ""

    def __post_init__(self):
        """标准化包名"""
        self.package = self.package.lower().replace("_", "-").replace(".", "-")


@dataclass
class ConflictResolution:
    """冲突解决方案"""

    conflict: VersionConflict
    strategy: str  # "upgrade", "downgrade", "replace", "remove", "ignore"
    target_version: Optional[str] = None
    packages_to_modify: List[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 - 1.0
    risk_level: str = "low"  # "low", "medium", "high"
    description: str = ""

    def __post_init__(self):
        """标准化包名"""
        if self.conflict:
            self.conflict.package = (
                self.conflict.package.lower().replace("_", "-").replace(".", "-")
            )


@dataclass
class ConflictAnalysis:
    """冲突分析结果"""

    total_conflicts: int
    error_conflicts: int
    warning_conflicts: int
    info_conflicts: int
    conflicts_by_package: Dict[str, List[VersionConflict]]
    resolutions: List[ConflictResolution]
    analysis_time: float
    recommendations: List[str]


class ConflictDetector:
    """版本冲突检测器"""

    def __init__(self, package_manager, config: Optional[Dict[str, Any]] = None):
        """
        初始化冲突检测器

        Args:
            package_manager: 包管理器实例
            config: 配置选项
        """
        self.package_manager = package_manager
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "check_transitive": True,
            "max_depth": 10,
            "allow_prereleases": False,
            "strict_mode": False,
            "auto_resolve": True,
            "confidence_threshold": 0.7,
            "cache_enabled": True,
            "cache_ttl": 300,
        }

        # 合并配置
        self.config = {**self.default_config, **self.config}

        # 缓存
        self._conflict_cache: Dict[str, List[VersionConflict]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

    def detect_version_conflicts(
        self,
        packages: Optional[List[str]] = None,
        requirements_file: Optional[str] = None,
        installed_packages: Optional[Dict[str, str]] = None,
    ) -> ConflictAnalysis:
        """
        检测版本冲突

        Args:
            packages: 要检查的包列表
            requirements_file: requirements文件路径
            installed_packages: 已安装包字典 {package: version}

        Returns:
            冲突分析结果
        """
        start_time = datetime.now()

        try:
            # 获取包信息
            if installed_packages is None:
                installed_packages = self.package_manager.list_packages()
                installed_packages = {
                    name: info.version for name, info in installed_packages.items()
                }

            # 获取要检查的包
            if packages is None:
                packages = list(installed_packages.keys())

            # 检测冲突
            all_conflicts = []
            conflicts_by_package = {}

            for package in packages:
                package_conflicts = self._detect_package_conflicts(
                    package, installed_packages
                )
                all_conflicts.extend(package_conflicts)
                conflicts_by_package[package] = package_conflicts

            # 分类冲突
            error_conflicts = len([c for c in all_conflicts if c.severity == "error"])
            warning_conflicts = len(
                [c for c in all_conflicts if c.severity == "warning"]
            )
            info_conflicts = len([c for c in all_conflicts if c.severity == "info"])

            # 生成解决方案
            resolutions = []
            if self.config["auto_resolve"]:
                resolutions = self._generate_resolutions(all_conflicts)

            # 生成建议
            recommendations = self._generate_recommendations(all_conflicts)

            analysis_time = (datetime.now() - start_time).total_seconds()

            return ConflictAnalysis(
                total_conflicts=len(all_conflicts),
                error_conflicts=error_conflicts,
                warning_conflicts=warning_conflicts,
                info_conflicts=info_conflicts,
                conflicts_by_package=conflicts_by_package,
                resolutions=resolutions,
                analysis_time=analysis_time,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Error detecting version conflicts: {e}")
            return ConflictAnalysis(
                total_conflicts=0,
                error_conflicts=0,
                warning_conflicts=0,
                info_conflicts=0,
                conflicts_by_package={},
                resolutions=[],
                analysis_time=(datetime.now() - start_time).total_seconds(),
                recommendations=[f"Error during conflict detection: {e}"],
            )

    def _detect_package_conflicts(
        self, package: str, installed_packages: Dict[str, str]
    ) -> List[VersionConflict]:
        """
        检测单个包的冲突

        Args:
            package: 包名
            installed_packages: 已安装包字典

        Returns:
            冲突列表
        """
        conflicts = []

        try:
            # 获取包的详细信息
            package_details = self.package_manager.get_package_details(package)
            if not package_details:
                return conflicts

            # 检查直接依赖冲突
            direct_conflicts = self._check_direct_dependencies(
                package, package_details, installed_packages
            )
            conflicts.extend(direct_conflicts)

            # 检查传递依赖冲突
            if self.config["check_transitive"]:
                transitive_conflicts = self._check_transitive_dependencies(
                    package, installed_packages
                )
                conflicts.extend(transitive_conflicts)

            # 检查版本兼容性
            compatibility_conflicts = self._check_version_compatibility(
                package, installed_packages
            )
            conflicts.extend(compatibility_conflicts)

        except Exception as e:
            logger.error(f"Error detecting conflicts for {package}: {e}")

        return conflicts

    def _check_direct_dependencies(
        self,
        package: str,
        package_details: Dict[str, Any],
        installed_packages: Dict[str, str],
    ) -> List[VersionConflict]:
        """
        检查直接依赖冲突

        Args:
            package: 包名
            package_details: 包详细信息
            installed_packages: 已安装包字典

        Returns:
            冲突列表
        """
        conflicts = []

        try:
            dependencies = package_details.get("requires", [])
            package_version = installed_packages.get(package)

            for dep_spec in dependencies:
                try:
                    # 解析依赖规格
                    req = Requirement(dep_spec)
                    dep_name = req.name

                    # 检查依赖是否已安装
                    if dep_name in installed_packages:
                        installed_version = installed_packages[dep_name]

                        # 检查版本是否满足要求
                        if not req.specifier.contains(installed_version):
                            conflict = VersionConflict(
                                package=dep_name,
                                conflict_type="direct",
                                conflicting_requirements=[
                                    (
                                        str(req.specifier),
                                        package,
                                        f"requires {dep_spec}",
                                    )
                                ],
                                severity="error",
                                error_message=f"{package} requires {dep_name} {req.specifier}, but {installed_version} is installed",
                                affected_packages={package, dep_name},
                            )
                            conflicts.append(conflict)

                except InvalidSpecifier as e:
                    logger.warning(f"Invalid dependency specifier: {dep_spec} - {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing dependency {dep_spec}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error checking direct dependencies for {package}: {e}")

        return conflicts

    def _check_transitive_dependencies(
        self, package: str, installed_packages: Dict[str, str]
    ) -> List[VersionConflict]:
        """
        检查传递依赖冲突

        Args:
            package: 包名
            installed_packages: 已安装包字典

        Returns:
            冲突列表
        """
        conflicts = []

        try:
            # 构建依赖图
            dependency_graph = self._build_dependency_graph(package, installed_packages)

            # 检查每个包的依赖是否满足
            for pkg_name, pkg_deps in dependency_graph.items():
                if pkg_name not in installed_packages:
                    continue

                pkg_version = installed_packages[pkg_name]

                for dep_spec, dep_source in pkg_deps:
                    try:
                        req = Requirement(dep_spec)
                        dep_name = req.name

                        if dep_name in installed_packages:
                            installed_version = installed_packages[dep_name]

                            if not req.specifier.contains(installed_version):
                                conflict = VersionConflict(
                                    package=dep_name,
                                    conflict_type="transitive",
                                    conflicting_requirements=[
                                        (
                                            str(req.specifier),
                                            dep_source,
                                            f"transitive dependency",
                                        )
                                    ],
                                    severity="warning",
                                    error_message=f"Transitive dependency conflict: {dep_source} requires {dep_name} {req.specifier}, but {installed_version} is installed",
                                    affected_packages={pkg_name, dep_name, dep_source},
                                )
                                conflicts.append(conflict)

                    except (InvalidSpecifier, Exception) as e:
                        logger.warning(
                            f"Error processing transitive dependency {dep_spec}: {e}"
                        )
                        continue

        except Exception as e:
            logger.error(f"Error checking transitive dependencies for {package}: {e}")

        return conflicts

    def _check_version_compatibility(
        self, package: str, installed_packages: Dict[str, str]
    ) -> List[VersionConflict]:
        """
        检查版本兼容性

        Args:
            package: 包名
            installed_packages: 已安装包字典

        Returns:
            冲突列表
        """
        conflicts = []

        try:
            # 检查Python版本兼容性
            package_details = self.package_manager.get_package_details(package)
            if package_details:
                requires_python = package_details.get("requires-python")
                if requires_python:
                    try:
                        python_specifier = SpecifierSet(requires_python)
                        current_python = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

                        if not python_specifier.contains(current_python):
                            conflict = VersionConflict(
                                package=package,
                                conflict_type="incompatible",
                                conflicting_requirements=[
                                    (
                                        requires_python,
                                        "python",
                                        "Python version requirement",
                                    )
                                ],
                                severity="error",
                                error_message=f"{package} requires Python {requires_python}, but {current_python} is installed",
                                affected_packages={package},
                            )
                            conflicts.append(conflict)

                    except InvalidSpecifier:
                        logger.warning(
                            f"Invalid Python version specifier: {requires_python}"
                        )

            # 检查已知的不兼容版本组合
            incompatible_combinations = self._get_incompatible_combinations()
            for combo in incompatible_combinations:
                if self._check_incompatible_combo(combo, installed_packages):
                    conflict = VersionConflict(
                        package=combo["package"],
                        conflict_type="incompatible",
                        conflicting_requirements=[
                            (combo["version"], combo["with_package"], combo["reason"])
                        ],
                        severity="warning",
                        error_message=f"Known incompatibility: {combo['package']} {combo['version']} with {combo['with_package']}",
                        affected_packages={combo["package"], combo["with_package"]},
                    )
                    conflicts.append(conflict)

        except Exception as e:
            logger.error(f"Error checking version compatibility for {package}: {e}")

        return conflicts

    def _build_dependency_graph(
        self,
        root_package: str,
        installed_packages: Dict[str, str],
        visited: Optional[Set[str]] = None,
        depth: int = 0,
    ) -> Dict[str, List[Tuple[str, str]]]:
        """
        构建依赖图

        Args:
            root_package: 根包名
            installed_packages: 已安装包字典
            visited: 已访问的包集合
            depth: 当前深度

        Returns:
            依赖图 {package: [(dep_spec, source), ...]}
        """
        if visited is None:
            visited = set()

        if depth >= self.config["max_depth"] or root_package in visited:
            return {}

        visited.add(root_package)
        graph = {}

        try:
            # 获取包的依赖
            package_details = self.package_manager.get_package_details(root_package)
            if package_details:
                dependencies = package_details.get("requires", [])
                graph[root_package] = [(dep, root_package) for dep in dependencies]

                # 递归构建子依赖图
                for dep_spec in dependencies:
                    try:
                        req = Requirement(dep_spec)
                        dep_name = req.name

                        if dep_name in installed_packages:
                            sub_graph = self._build_dependency_graph(
                                dep_name, installed_packages, visited.copy(), depth + 1
                            )
                            graph.update(sub_graph)
                    except Exception:
                        continue

        except Exception as e:
            logger.error(f"Error building dependency graph for {root_package}: {e}")

        return graph

    def _get_incompatible_combinations(self) -> List[Dict[str, str]]:
        """
        获取已知的不兼容版本组合

        Returns:
            不兼容组合列表
        """
        # 这里可以维护一个已知不兼容组合的数据库
        # 简化实现，返回一些常见的不兼容组合
        return [
            {
                "package": "django",
                "version": ">=4.0",
                "with_package": "python",
                "with_version": "<3.8",
                "reason": "Django 4.0+ requires Python 3.8+",
            },
            {
                "package": "numpy",
                "version": ">=1.20",
                "with_package": "python",
                "with_version": "<3.7",
                "reason": "NumPy 1.20+ requires Python 3.7+",
            },
            {
                "package": "tensorflow",
                "version": ">=2.0",
                "with_package": "python",
                "with_version": "<3.7",
                "reason": "TensorFlow 2.0+ requires Python 3.7+",
            },
        ]

    def _check_incompatible_combo(
        self, combo: Dict[str, str], installed_packages: Dict[str, str]
    ) -> bool:
        """
        检查不兼容组合

        Args:
            combo: 不兼容组合配置
            installed_packages: 已安装包字典

        Returns:
            是否存在不兼容
        """
        try:
            package = combo["package"]
            with_package = combo["with_package"]

            if (
                package not in installed_packages
                or with_package not in installed_packages
            ):
                return False

            package_version = installed_packages[package]
            with_version = installed_packages[with_package]

            # 检查版本规格
            package_spec = combo.get("version", "")
            with_spec = combo.get("with_version", "")

            if package_spec and with_spec:
                try:
                    package_match = SpecifierSet(package_spec).contains(package_version)
                    with_match = SpecifierSet(with_spec).contains(with_version)
                    return package_match and with_match
                except InvalidSpecifier:
                    return False

            return False

        except Exception:
            return False

    def _generate_resolutions(
        self, conflicts: List[VersionConflict]
    ) -> List[ConflictResolution]:
        """
        生成冲突解决方案

        Args:
            conflicts: 冲突列表

        Returns:
            解决方案列表
        """
        resolutions = []

        for conflict in conflicts:
            try:
                resolution = self._generate_resolution_for_conflict(conflict)
                if (
                    resolution
                    and resolution.confidence >= self.config["confidence_threshold"]
                ):
                    resolutions.append(resolution)

            except Exception as e:
                logger.error(
                    f"Error generating resolution for conflict {conflict.package}: {e}"
                )

        # 按置信度排序
        resolutions.sort(key=lambda r: r.confidence, reverse=True)
        return resolutions

    def _generate_resolution_for_conflict(
        self, conflict: VersionConflict
    ) -> Optional[ConflictResolution]:
        """
        为单个冲突生成解决方案

        Args:
            conflict: 版本冲突

        Returns:
            解决方案或None
        """
        try:
            if conflict.conflict_type == "direct":
                return self._resolve_direct_conflict(conflict)
            elif conflict.conflict_type == "transitive":
                return self._resolve_transitive_conflict(conflict)
            elif conflict.conflict_type == "incompatible":
                return self._resolve_incompatible_conflict(conflict)

        except Exception as e:
            logger.error(f"Error generating resolution for {conflict.package}: {e}")

        return None

    def _resolve_direct_conflict(self, conflict: VersionConflict) -> ConflictResolution:
        """解决直接依赖冲突"""
        # 简化实现：建议升级或降级
        strategy = "upgrade"
        confidence = 0.8
        risk_level = "medium"

        return ConflictResolution(
            conflict=conflict,
            strategy=strategy,
            confidence=confidence,
            risk_level=risk_level,
            description=f"Upgrade {conflict.package} to satisfy dependency requirements",
        )

    def _resolve_transitive_conflict(
        self, conflict: VersionConflict
    ) -> ConflictResolution:
        """解决传递依赖冲突"""
        strategy = "ignore"
        confidence = 0.6
        risk_level = "low"

        return ConflictResolution(
            conflict=conflict,
            strategy=strategy,
            confidence=confidence,
            risk_level=risk_level,
            description=f"Ignore transitive conflict for {conflict.package} (may cause runtime issues)",
        )

    def _resolve_incompatible_conflict(
        self, conflict: VersionConflict
    ) -> ConflictResolution:
        """解决不兼容冲突"""
        strategy = "replace"
        confidence = 0.9
        risk_level = "high"

        return ConflictResolution(
            conflict=conflict,
            strategy=strategy,
            confidence=confidence,
            risk_level=risk_level,
            description=f"Replace {conflict.package} with compatible version",
        )

    def _generate_recommendations(self, conflicts: List[VersionConflict]) -> List[str]:
        """
        生成建议

        Args:
            conflicts: 冲突列表

        Returns:
            建议列表
        """
        recommendations = []

        if not conflicts:
            recommendations.append(
                "No version conflicts detected. All packages are compatible."
            )
            return recommendations

        # 统计冲突类型
        error_count = len([c for c in conflicts if c.severity == "error"])
        warning_count = len([c for c in conflicts if c.severity == "warning"])

        if error_count > 0:
            recommendations.append(
                f"Found {error_count} error conflicts that must be resolved."
            )

        if warning_count > 0:
            recommendations.append(
                f"Found {warning_count} warning conflicts that should be reviewed."
            )

        # 通用建议
        recommendations.append(
            "Consider updating packages to their latest compatible versions."
        )
        recommendations.append(
            "Review dependency specifications in requirements files."
        )
        recommendations.append(
            "Use virtual environments to isolate package dependencies."
        )

        return recommendations

    def clear_cache(self) -> None:
        """清除缓存"""
        self._conflict_cache.clear()
        self._cache_timestamps.clear()
        logger.info("Conflict detector cache cleared")
