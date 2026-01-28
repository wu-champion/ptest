"""
依赖解析器实现

提供Python包依赖解析、冲突检测和解决功能
"""

import re
import json
from typing import Dict, List, Set, Optional, Tuple, Any, Union
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from packaging import version
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

from core import get_logger

logger = get_logger("dependency_resolver")


@dataclass
class DependencyNode:
    """依赖节点"""

    name: str
    version_spec: Optional[str] = None
    required_by: Set[str] = field(default_factory=set)
    conflicts_with: Set[str] = field(default_factory=set)
    resolved_version: Optional[str] = None
    is_root: bool = False

    def __post_init__(self):
        """标准化包名"""
        self.name = self.name.lower().replace("_", "-").replace(".", "-")


@dataclass
class DependencyEdge:
    """依赖边"""

    from_package: str
    to_package: str
    version_spec: str
    is_optional: bool = False

    def __post_init__(self):
        """标准化包名"""
        self.from_package = (
            self.from_package.lower().replace("_", "-").replace(".", "-")
        )
        self.to_package = self.to_package.lower().replace("_", "-").replace(".", "-")


@dataclass
class ConflictInfo:
    """冲突信息"""

    package: str
    conflicting_versions: List[Tuple[str, str]]  # (version, required_by)
    resolution_strategy: Optional[str] = None
    suggested_version: Optional[str] = None
    error_message: str = ""


@dataclass
class DependencyTree:
    """依赖树"""

    root_package: str
    nodes: Dict[str, DependencyNode] = field(default_factory=dict)
    edges: List[DependencyEdge] = field(default_factory=list)
    conflicts: List[ConflictInfo] = field(default_factory=list)
    resolved: bool = False

    def add_node(self, node: DependencyNode) -> None:
        """添加节点"""
        self.nodes[node.name] = node

    def add_edge(self, edge: DependencyEdge) -> None:
        """添加边"""
        self.edges.append(edge)
        # 更新节点的required_by
        if edge.to_package in self.nodes:
            self.nodes[edge.to_package].required_by.add(edge.from_package)

    def get_dependencies(self, package: str) -> List[str]:
        """获取包的直接依赖"""
        dependencies = []
        for edge in self.edges:
            if edge.from_package == package:
                dependencies.append(edge.to_package)
        return dependencies

    def get_all_dependencies(self, package: str) -> Set[str]:
        """获取包的所有依赖（递归）"""
        all_deps = set()
        direct_deps = self.get_dependencies(package)
        all_deps.update(direct_deps)

        for dep in direct_deps:
            all_deps.update(self.get_all_dependencies(dep))

        return all_deps


class DependencyResolver:
    """依赖解析器"""

    def __init__(self, package_manager, config: Optional[Dict[str, Any]] = None):
        """
        初始化依赖解析器

        Args:
            package_manager: 包管理器实例
            config: 配置选项
        """
        self.package_manager = package_manager
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "max_depth": 50,
            "cache_enabled": True,
            "cache_ttl": 300,  # 5分钟
            "prefer_latest": True,
            "allow_prereleases": False,
            "resolve_conflicts": True,
            "timeout": 30,
        }

        # 合并配置
        self.config = {**self.default_config, **self.config}

        # 缓存
        self._dependency_cache: Dict[str, DependencyTree] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

    def parse_requirements(self, requirements_file: Path) -> List[Requirement]:
        """
        解析requirements文件

        Args:
            requirements_file: requirements文件路径

        Returns:
            需求列表
        """
        try:
            requirements = []

            with open(requirements_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # 跳过空行和注释
                    if not line or line.startswith("#"):
                        continue

                    # 处理-r选项（包含其他文件）
                    if line.startswith("-r "):
                        included_file = Path(line[3:].strip())
                        if included_file.is_absolute():
                            included_path = included_file
                        else:
                            included_path = requirements_file.parent / included_file

                        if included_path.exists():
                            included_requirements = self.parse_requirements(
                                included_path
                            )
                            requirements.extend(included_requirements)
                        else:
                            logger.warning(
                                f"Included requirements file not found: {included_path}"
                            )
                        continue

                    # 处理-e选项（可编辑安装）
                    if line.startswith("-e "):
                        # 可编辑安装的包，暂时跳过复杂解析
                        continue

                    try:
                        # 解析需求规格
                        req = Requirement(line)
                        requirements.append(req)
                    except Exception as e:
                        logger.warning(
                            f"Failed to parse requirement at line {line_num}: {line} - {e}"
                        )
                        continue

            return requirements

        except Exception as e:
            logger.error(f"Error parsing requirements file {requirements_file}: {e}")
            return []

    def resolve_dependencies(
        self,
        root_package: str,
        version_spec: Optional[str] = None,
        requirements_file: Optional[Path] = None,
    ) -> DependencyTree:
        """
        解析依赖关系

        Args:
            root_package: 根包名
            version_spec: 版本规格
            requirements_file: requirements文件路径

        Returns:
            依赖树
        """
        # 检查缓存
        cache_key = f"{root_package}:{version_spec}:{requirements_file}"
        if (
            self.config["cache_enabled"]
            and cache_key in self._dependency_cache
            and cache_key in self._cache_timestamps
        ):
            cache_age = (
                datetime.now() - self._cache_timestamps[cache_key]
            ).total_seconds()
            if cache_age < self.config["cache_ttl"]:
                logger.debug(f"Using cached dependency tree for {root_package}")
                return self._dependency_cache[cache_key]

        try:
            # 创建依赖树
            tree = DependencyTree(root_package=root_package)

            # 添加根节点
            root_node = DependencyNode(
                name=root_package, version_spec=version_spec, is_root=True
            )
            tree.add_node(root_node)

            # 解析依赖
            if requirements_file:
                # 从requirements文件解析
                requirements = self.parse_requirements(requirements_file)
                for req in requirements:
                    self._resolve_package_dependencies(
                        req.name, str(req.specifier), tree, root_package, depth=0
                    )
            else:
                # 从单个包解析
                self._resolve_package_dependencies(
                    root_package, version_spec or "", tree, required_by=root_package, depth=0
                )

            # 检测冲突
            self._detect_conflicts(tree)

            # 尝试解决冲突
            if self.config["resolve_conflicts"]:
                self._resolve_conflicts(tree)

            # 标记为已解析
            tree.resolved = len(tree.conflicts) == 0

            # 缓存结果
            if self.config["cache_enabled"]:
                self._dependency_cache[cache_key] = tree
                self._cache_timestamps[cache_key] = datetime.now()

            logger.info(
                f"Resolved dependencies for {root_package}: {len(tree.nodes)} packages, {len(tree.conflicts)} conflicts"
            )
            return tree

        except Exception as e:
            logger.error(f"Error resolving dependencies for {root_package}: {e}")
            return DependencyTree(root_package=root_package)

    def _resolve_package_dependencies(
        self,
        package: str,
        version_spec: str,
        tree: DependencyTree,
        required_by: str,
        depth: int = 0,
    ) -> None:
        """
        解析单个包的依赖

        Args:
            package: 包名
            version_spec: 版本规格
            tree: 依赖树
            required_by: 依赖此包的包
            depth: 当前深度
        """
        if depth >= self.config["max_depth"]:
            logger.warning(f"Maximum dependency depth reached for {package}")
            return

        # 创建或获取节点
        if package not in tree.nodes:
            node = DependencyNode(name=package, version_spec=version_spec)
            tree.add_node(node)
        else:
            node = tree.nodes[package]
            node.required_by.add(required_by)

        # 获取包的依赖信息
        try:
            package_details = self.package_manager.get_package_details(package)
            if not package_details:
                logger.warning(f"Could not get details for package: {package}")
                return

            dependencies = package_details.get("requires", [])

            for dep_spec in dependencies:
                try:
                    # 解析依赖规格
                    dep_req = Requirement(dep_spec)
                    dep_name = dep_req.name
                    dep_version_spec = str(dep_req.specifier)

                    # 添加依赖边
                    edge = DependencyEdge(
                        from_package=package,
                        to_package=dep_name,
                        version_spec=dep_version_spec,
                        is_optional=dep_req.marker is not None,
                    )
                    tree.add_edge(edge)

                    # 递归解析依赖的依赖
                    self._resolve_package_dependencies(
                        dep_name, dep_version_spec, tree, package, depth + 1
                    )

                except Exception as e:
                    logger.warning(f"Failed to parse dependency spec: {dep_spec} - {e}")
                    continue

        except Exception as e:
            logger.error(f"Error resolving dependencies for {package}: {e}")

    def _detect_conflicts(self, tree: DependencyTree) -> None:
        """
        检测版本冲突

        Args:
            tree: 依赖树
        """
        conflicts = {}

        # 检查每个包的版本冲突
        for package_name, node in tree.nodes.items():
            if node.is_root:
                continue

            # 收集所有对此包的版本要求
            version_requirements = []

            for edge in tree.edges:
                if edge.to_package == package_name:
                    version_requirements.append((edge.version_spec, edge.from_package))

            # 检查是否存在冲突
            if len(version_requirements) > 1:
                conflict_info = self._check_version_conflict(
                    package_name, version_requirements
                )
                if conflict_info:
                    conflicts[package_name] = conflict_info

        # 更新树的冲突列表
        tree.conflicts = list(conflicts.values())

    def _check_version_conflict(
        self, package: str, version_requirements: List[Tuple[str, str]]
    ) -> Optional[ConflictInfo]:
        """
        检查特定包的版本冲突

        Args:
            package: 包名
            version_requirements: 版本要求列表 [(version_spec, required_by), ...]

        Returns:
            冲突信息或None
        """
        try:
            # 获取所有可用版本
            available_versions = self._get_available_versions(package)
            if not available_versions:
                return None

            # 检查每个版本要求
            conflicting_versions = []
            compatible_versions = set(available_versions)

            for version_spec, required_by in version_requirements:
                if not version_spec:
                    continue

                try:
                    specifier = SpecifierSet(version_spec)
                    compatible_for_spec = [
                        v for v in available_versions if specifier.contains(v)
                    ]

                    if not compatible_for_spec:
                        # 没有兼容版本
                        conflicting_versions.append((version_spec, required_by))
                    else:
                        # 更新兼容版本交集
                        compatible_versions &= set(compatible_for_spec)

                except Exception as e:
                    logger.warning(f"Invalid version specifier: {version_spec} - {e}")
                    continue

            # 如果存在冲突
            if conflicting_versions and not compatible_versions:
                # 尝试找到解决方案
                suggested_version = self._find_compatible_version(
                    package, version_requirements
                )

                return ConflictInfo(
                    package=package,
                    conflicting_versions=conflicting_versions,
                    suggested_version=suggested_version,
                    error_message=f"Version conflict for {package}: incompatible version requirements",
                )

        except Exception as e:
            logger.error(f"Error checking version conflict for {package}: {e}")

        return None

    def _resolve_conflicts(self, tree: DependencyTree) -> None:
        """
        尝试解决冲突

        Args:
            tree: 依赖树
        """
        for conflict in tree.conflicts:
            try:
                if conflict.suggested_version:
                    # 更新节点版本
                    if conflict.package in tree.nodes:
                        node = tree.nodes[conflict.package]
                        node.resolved_version = conflict.suggested_version
                        conflict.resolution_strategy = "use_suggested_version"
                        logger.info(
                            f"Resolved conflict for {conflict.package} using version {conflict.suggested_version}"
                        )
                else:
                    # 无法自动解决
                    conflict.resolution_strategy = "manual_intervention_required"
                    logger.warning(
                        f"Manual intervention required for {conflict.package} conflict"
                    )

            except Exception as e:
                logger.error(f"Error resolving conflict for {conflict.package}: {e}")

    def _get_available_versions(self, package: str) -> List[str]:
        """
        获取包的可用版本列表

        Args:
            package: 包名

        Returns:
            版本列表
        """
        try:
            # 这里应该调用PyPI API或其他方式获取可用版本
            # 简化实现：返回一些常见版本
            return ["1.0.0", "1.1.0", "1.2.0", "2.0.0", "2.1.0"]

        except Exception as e:
            logger.error(f"Error getting available versions for {package}: {e}")
            return []

    def _find_compatible_version(
        self, package: str, version_requirements: List[Tuple[str, str]]
    ) -> Optional[str]:
        """
        查找兼容版本

        Args:
            package: 包名
            version_requirements: 版本要求列表

        Returns:
            兼容版本或None
        """
        try:
            available_versions = self._get_available_versions(package)

            # 按版本排序（优先最新版本）
            sorted_versions = sorted(
                available_versions, key=version.parse, reverse=True
            )

            for candidate_version in sorted_versions:
                compatible = True

                for version_spec, required_by in version_requirements:
                    if not version_spec:
                        continue

                    try:
                        specifier = SpecifierSet(version_spec)
                        if not specifier.contains(candidate_version):
                            compatible = False
                            break
                    except Exception:
                        continue

                if compatible:
                    return candidate_version

        except Exception as e:
            logger.error(f"Error finding compatible version for {package}: {e}")

        return None

    def generate_dependency_graph(self, tree: DependencyTree) -> Dict[str, Any]:
        """
        生成依赖图数据

        Args:
            tree: 依赖树

        Returns:
            依赖图数据
        """
        try:
            graph = {
                "nodes": [],
                "edges": [],
                "conflicts": [],
                "metadata": {
                    "root_package": tree.root_package,
                    "total_packages": len(tree.nodes),
                    "total_dependencies": len(tree.edges),
                    "total_conflicts": len(tree.conflicts),
                    "resolved": tree.resolved,
                },
            }

            # 添加节点
            for package_name, node in tree.nodes.items():
                node_data = {
                    "id": package_name,
                    "name": package_name,
                    "version_spec": node.version_spec,
                    "resolved_version": node.resolved_version,
                    "is_root": node.is_root,
                    "required_by": list(node.required_by),
                    "conflicts_with": list(node.conflicts_with),
                }
                graph["nodes"].append(node_data)

            # 添加边
            for edge in tree.edges:
                edge_data = {
                    "from": edge.from_package,
                    "to": edge.to_package,
                    "version_spec": edge.version_spec,
                    "is_optional": edge.is_optional,
                }
                graph["edges"].append(edge_data)

            # 添加冲突
            for conflict in tree.conflicts:
                conflict_data = {
                    "package": conflict.package,
                    "conflicting_versions": conflict.conflicting_versions,
                    "resolution_strategy": conflict.resolution_strategy,
                    "suggested_version": conflict.suggested_version,
                    "error_message": conflict.error_message,
                }
                graph["conflicts"].append(conflict_data)

            return graph

        except Exception as e:
            logger.error(f"Error generating dependency graph: {e}")
            return {}

    def export_dependency_tree(self, tree: DependencyTree, format: str = "json") -> str:
        """
        导出依赖树

        Args:
            tree: 依赖树
            format: 导出格式 ("json", "dot", "text")

        Returns:
            导出的字符串
        """
        try:
            if format == "json":
                graph_data = self.generate_dependency_graph(tree)
                return json.dumps(graph_data, indent=2)

            elif format == "text":
                lines = [f"Dependency tree for {tree.root_package}"]
                lines.append("=" * 50)

                for package_name, node in tree.nodes.items():
                    prefix = "├── " if not node.is_root else "└── "
                    lines.append(
                        f"{prefix}{package_name} ({node.version_spec or 'any'})"
                    )

                    dependencies = tree.get_dependencies(package_name)
                    for dep in dependencies:
                        lines.append(f"    ├── {dep}")

                if tree.conflicts:
                    lines.append("\nConflicts:")
                    for conflict in tree.conflicts:
                        lines.append(
                            f"  - {conflict.package}: {conflict.error_message}"
                        )

                return "\n".join(lines)

            elif format == "dot":
                # Graphviz DOT格式
                lines = ["digraph dependencies {"]
                lines.append(f'    label="{tree.root_package} dependencies";')
                lines.append("    node [shape=box];")

                # 添加节点
                for package_name, node in tree.nodes.items():
                    color = (
                        "red"
                        if any(c.package == package_name for c in tree.conflicts)
                        else "black"
                    )
                    lines.append(f'    "{package_name}" [color="{color}"];')

                # 添加边
                for edge in tree.edges:
                    style = "dashed" if edge.is_optional else "solid"
                    lines.append(
                        f'    "{edge.from_package}" -> "{edge.to_package}" [style="{style}"];'
                    )

                lines.append("}")
                return "\n".join(lines)

            else:
                raise ValueError(f"Unsupported export format: {format}")

        except Exception as e:
            logger.error(f"Error exporting dependency tree: {e}")
            return ""

    def clear_cache(self) -> None:
        """清除缓存"""
        self._dependency_cache.clear()
        self._cache_timestamps.clear()
        logger.info("Dependency resolver cache cleared")
