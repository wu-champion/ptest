"""
包缓存管理器实现

提供Python包下载、存储和管理功能
"""

import json
import hashlib
import shutil
import tempfile
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import requests

from ..core import get_logger

logger = get_logger("package_cache")


@dataclass
class CacheEntry:
    """缓存条目"""

    package: str
    version: str
    file_path: Path
    file_hash: str
    file_size: int
    download_time: datetime
    last_accessed: datetime
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """标准化包名"""
        self.package = self.package.lower().replace("_", "-").replace(".", "-")


@dataclass
class CacheStats:
    """缓存统计"""

    total_entries: int
    total_size: int
    cache_hit_rate: float
    oldest_entry: Optional[datetime]
    newest_entry: Optional[datetime]
    most_accessed: Optional[str]
    least_accessed: Optional[str]


class PackageCache:
    """包缓存管理器"""

    def __init__(self, cache_dir: Path, config: Optional[Dict[str, Any]] = None):
        """
        初始化包缓存管理器

        Args:
            cache_dir: 缓存目录
            config: 配置选项
        """
        self.cache_dir = cache_dir
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "max_cache_size": 5 * 1024 * 1024 * 1024,  # 5GB
            "max_entries": 1000,
            "cleanup_threshold": 0.8,  # 80%时开始清理
            "ttl_days": 30,  # 30天TTL
            "hash_algorithm": "sha256",
            "verify_downloads": True,
            "parallel_downloads": True,
            "max_retries": 3,
            "timeout": 300,
            "user_agent": "ptest-package-cache/1.0",
        }

        # 合并配置
        self.config = {**self.default_config, **self.config}

        # 创建缓存目录
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir = self.cache_dir / ".metadata"
        self.metadata_dir.mkdir(exist_ok=True)

        # 缓存索引
        self._cache_index: Dict[str, CacheEntry] = {}
        self._stats = CacheStats(
            total_entries=0,
            total_size=0,
            cache_hit_rate=0.0,
            oldest_entry=None,
            newest_entry=None,
            most_accessed=None,
            least_accessed=None,
        )

        # 加载缓存索引
        self._load_cache_index()

    def get_cached_package(self, package: str, version: str) -> Optional[Path]:
        """
        获取缓存的包文件

        Args:
            package: 包名
            version: 版本

        Returns:
            缓存文件路径或None
        """
        cache_key = self._get_cache_key(package, version)

        if cache_key in self._cache_index:
            entry = self._cache_index[cache_key]

            # 检查文件是否存在
            if not entry.file_path.exists():
                logger.warning(f"Cache file not found: {entry.file_path}")
                self._remove_entry(cache_key)
                return None

            # 检查TTL
            if self._is_expired(entry):
                logger.info(f"Cache entry expired: {package} {version}")
                self._remove_entry(cache_key)
                return None

            # 更新访问信息
            entry.last_accessed = datetime.now()
            entry.access_count += 1
            self._save_cache_index()

            logger.debug(f"Cache hit: {package} {version}")
            return entry.file_path

        logger.debug(f"Cache miss: {package} {version}")
        return None

    def cache_package(
        self, package: str, version: str, download_url: str, force_refresh: bool = False
    ) -> Optional[Path]:
        """
        缓存包文件

        Args:
            package: 包名
            version: 版本
            download_url: 下载URL
            force_refresh: 是否强制刷新

        Returns:
            缓存文件路径或None
        """
        cache_key = self._get_cache_key(package, version)

        # 检查是否已缓存
        if not force_refresh and cache_key in self._cache_index:
            entry = self._cache_index[cache_key]
            if entry.file_path.exists() and not self._is_expired(entry):
                logger.debug(f"Package already cached: {package} {version}")
                return entry.file_path

        try:
            # 下载文件
            temp_file = self._download_file(download_url, package, version)
            if not temp_file:
                return None

            # 验证文件
            if self.config["verify_downloads"]:
                if not self._verify_package_file(temp_file, package, version):
                    temp_file.unlink(missing_ok=True)
                    return None

            # 生成缓存文件路径
            cache_filename = f"{package}-{version}.whl"
            cache_file_path = self.cache_dir / cache_filename

            # 移动文件到缓存目录
            shutil.move(str(temp_file), str(cache_file_path))

            # 计算文件哈希
            file_hash = self._calculate_file_hash(cache_file_path)
            file_size = cache_file_path.stat().st_size

            # 创建缓存条目
            entry = CacheEntry(
                package=package,
                version=version,
                file_path=cache_file_path,
                file_hash=file_hash,
                file_size=file_size,
                download_time=datetime.now(),
                last_accessed=datetime.now(),
                access_count=1,
            )

            # 添加到缓存索引
            self._cache_index[cache_key] = entry

            # 检查缓存大小限制
            self._check_cache_limits()

            # 保存索引
            self._save_cache_index()

            logger.info(f"Cached package: {package} {version} ({file_size} bytes)")
            return cache_file_path

        except Exception as e:
            logger.error(f"Error caching package {package} {version}: {e}")
            return None

    def remove_cached_package(self, package: str, version: str) -> bool:
        """
        移除缓存的包

        Args:
            package: 包名
            version: 版本

        Returns:
            是否成功移除
        """
        cache_key = self._get_cache_key(package, version)

        if cache_key in self._cache_index:
            return self._remove_entry(cache_key)

        return False

    def cleanup_cache(self, force: bool = False) -> Dict[str, Any]:
        """
        清理缓存

        Args:
            force: 是否强制清理

        Returns:
            清理结果
        """
        cleanup_result = {
            "removed_entries": 0,
            "freed_space": 0,
            "remaining_entries": 0,
            "remaining_space": 0,
        }

        try:
            # 获取需要清理的条目
            entries_to_remove = []

            for cache_key, entry in self._cache_index.items():
                should_remove = False

                # 检查TTL
                if self._is_expired(entry):
                    should_remove = True
                    logger.debug(
                        f"Removing expired entry: {entry.package} {entry.version}"
                    )

                # 检查文件是否存在
                elif not entry.file_path.exists():
                    should_remove = True
                    logger.debug(
                        f"Removing missing file entry: {entry.package} {entry.version}"
                    )

                # 强制清理模式
                elif force:
                    should_remove = True
                    logger.debug(
                        f"Force removing entry: {entry.package} {entry.version}"
                    )

                if should_remove:
                    entries_to_remove.append(cache_key)

            # 移除条目
            for cache_key in entries_to_remove:
                if self._remove_entry(cache_key):
                    cleanup_result["removed_entries"] += 1
                    cache_entry: CacheEntry | None = self._cache_index.get(cache_key)
                    if cache_entry:
                        cleanup_result["freed_space"] += cache_entry.file_size

            # 更新统计
            self._update_stats()
            cleanup_result["remaining_entries"] = self._stats.total_entries
            cleanup_result["remaining_space"] = self._stats.total_size

            # 保存索引
            self._save_cache_index()

            logger.info(
                f"Cache cleanup completed: removed {cleanup_result['removed_entries']} entries, freed {cleanup_result['freed_space']} bytes"
            )
            return cleanup_result

        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            return cleanup_result

    def get_cache_stats(self) -> CacheStats:
        """
        获取缓存统计信息

        Returns:
            缓存统计
        """
        self._update_stats()
        return self._stats

    def list_cached_packages(self) -> List[Tuple[str, str, datetime]]:
        """
        列出缓存的包

        Returns:
            包列表 [(package, version, download_time), ...]
        """
        packages = []

        for entry in self._cache_index.values():
            packages.append((entry.package, entry.version, entry.download_time))

        # 按下载时间排序
        packages.sort(key=lambda x: x[2], reverse=True)
        return packages

    def _get_cache_key(self, package: str, version: str) -> str:
        """生成缓存键"""
        return f"{package.lower()}:{version}"

    def _download_file(self, url: str, package: str, version: str) -> Optional[Path]:
        """下载文件"""
        temp_file = None
        try:
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".whl")
            temp_file.close()

            # 下载文件
            headers = {"User-Agent": self.config["user_agent"]}

            with requests.get(
                url, headers=headers, stream=True, timeout=self.config["timeout"]
            ) as response:
                response.raise_for_status()

                with open(temp_file.name, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

            logger.debug(f"Downloaded {package} {version} to {temp_file.name}")
            return Path(temp_file.name)

        except Exception as e:
            logger.error(f"Error downloading {package} {version}: {e}")
            if temp_file:
                Path(temp_file.name).unlink(missing_ok=True)
            return None

    def _verify_package_file(self, file_path: Path, package: str, version: str) -> bool:
        """验证包文件"""
        try:
            # 简化验证：检查文件大小和格式
            if file_path.stat().st_size == 0:
                return False

            # 检查文件扩展名
            if file_path.suffix not in [".whl", ".zip", ".tar.gz"]:
                return False

            return True

        except Exception as e:
            logger.error(f"Error verifying package file: {e}")
            return False

    def _calculate_file_hash(self, file_path: Path) -> str:
        """计算文件哈希"""
        hash_algo = self.config["hash_algorithm"]
        hash_func = hashlib.new(hash_algo)

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)

        return hash_func.hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """检查缓存条目是否过期"""
        ttl = timedelta(days=self.config["ttl_days"])
        return datetime.now() - entry.download_time > ttl

    def _remove_entry(self, cache_key: str) -> bool:
        """移除缓存条目"""
        try:
            if cache_key in self._cache_index:
                entry = self._cache_index[cache_key]

                # 删除文件
                if entry.file_path.exists():
                    entry.file_path.unlink()

                # 从索引中移除
                del self._cache_index[cache_key]

                return True

        except Exception as e:
            logger.error(f"Error removing cache entry {cache_key}: {e}")

        return False

    def _check_cache_limits(self) -> None:
        """检查缓存限制"""
        # 检查条目数量限制
        if len(self._cache_index) > self.config["max_entries"]:
            self._cleanup_by_lru()

        # 检查大小限制
        total_size = sum(entry.file_size for entry in self._cache_index.values())
        if total_size > self.config["max_cache_size"]:
            self._cleanup_by_size()

    def _cleanup_by_lru(self) -> None:
        """按LRU清理缓存"""
        # 按最后访问时间排序
        sorted_entries = sorted(
            self._cache_index.items(), key=lambda x: x[1].last_accessed
        )

        # 移除最旧的条目
        target_count = int(
            self.config["max_entries"] * self.config["cleanup_threshold"]
        )

        for i, (cache_key, entry) in enumerate(sorted_entries):
            if i >= len(self._cache_index) - target_count:
                break
            self._remove_entry(cache_key)

    def _cleanup_by_size(self) -> None:
        """按大小清理缓存"""
        target_size = int(
            self.config["max_cache_size"] * self.config["cleanup_threshold"]
        )

        # 按最后访问时间排序
        sorted_entries = sorted(
            self._cache_index.items(), key=lambda x: x[1].last_accessed
        )

        current_size = sum(entry.file_size for entry in self._cache_index.values())

        for cache_key, entry in sorted_entries:
            if current_size <= target_size:
                break

            self._remove_entry(cache_key)
            current_size -= entry.file_size

    def _update_stats(self) -> None:
        """更新统计信息"""
        if not self._cache_index:
            self._stats = CacheStats(
                total_entries=0,
                total_size=0,
                cache_hit_rate=0.0,
                oldest_entry=None,
                newest_entry=None,
                most_accessed=None,
                least_accessed=None,
            )
            return

        entries = list(self._cache_index.values())
        total_size = sum(entry.file_size for entry in entries)

        # 计算时间范围
        download_times = [entry.download_time for entry in entries]
        oldest = min(download_times)
        newest = max(download_times)

        # 计算访问统计
        access_counts = [entry.access_count for entry in entries]
        most_accessed_idx = access_counts.index(max(access_counts))
        least_accessed_idx = access_counts.index(min(access_counts))

        self._stats = CacheStats(
            total_entries=len(entries),
            total_size=total_size,
            cache_hit_rate=0.0,  # 需要额外跟踪
            oldest_entry=oldest,
            newest_entry=newest,
            most_accessed=f"{entries[most_accessed_idx].package}:{entries[most_accessed_idx].version}",
            least_accessed=f"{entries[least_accessed_idx].package}:{entries[least_accessed_idx].version}",
        )

    def _load_cache_index(self) -> None:
        """加载缓存索引"""
        index_file = self.metadata_dir / "cache_index.json"

        try:
            if index_file.exists():
                with open(index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for cache_key, entry_data in data.items():
                    entry = CacheEntry(
                        package=entry_data["package"],
                        version=entry_data["version"],
                        file_path=Path(entry_data["file_path"]),
                        file_hash=entry_data["file_hash"],
                        file_size=entry_data["file_size"],
                        download_time=datetime.fromisoformat(
                            entry_data["download_time"]
                        ),
                        last_accessed=datetime.fromisoformat(
                            entry_data["last_accessed"]
                        ),
                        access_count=entry_data["access_count"],
                        metadata=entry_data.get("metadata", {}),
                    )
                    self._cache_index[cache_key] = entry

                logger.debug(f"Loaded {len(self._cache_index)} cache entries")

        except Exception as e:
            logger.error(f"Error loading cache index: {e}")

    def _save_cache_index(self) -> None:
        """保存缓存索引"""
        index_file = self.metadata_dir / "cache_index.json"

        try:
            data = {}
            for cache_key, entry in self._cache_index.items():
                data[cache_key] = {
                    "package": entry.package,
                    "version": entry.version,
                    "file_path": str(entry.file_path),
                    "file_hash": entry.file_hash,
                    "file_size": entry.file_size,
                    "download_time": entry.download_time.isoformat(),
                    "last_accessed": entry.last_accessed.isoformat(),
                    "access_count": entry.access_count,
                    "metadata": entry.metadata,
                }

            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving cache index: {e}")
