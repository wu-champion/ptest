"""
Docker卷管理器

提供完整的Docker卷管理功能，包括快照和恢复
"""

import os
import uuid
import shutil
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    import docker  # noqa: F401

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

if DOCKER_AVAILABLE:
    from docker.errors import NotFound

from ...core import get_logger

logger = get_logger("volume_manager")


class VolumeManager:
    """Docker卷管理器"""

    def __init__(self, docker_client, prefix: str = "ptest_vol_"):
        self.client = docker_client
        self.prefix = prefix

    def create_volume(
        self,
        volume_name: str,
        driver: str = "local",
        driver_opts: Optional[Dict[str, str]] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> Optional[Any]:
        """创建Docker卷"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating volume creation: {volume_name}"
                )
                return None

            if not self.client:
                logger.error("Docker client not initialized")
                return None

            try:
                existing_volume = self.client.volumes.get(volume_name)
                logger.info(f"Volume {volume_name} already exists")
                return existing_volume
            except NotFound:
                pass

            volume_config: Dict[str, Any] = {
                "Name": volume_name,
                "Driver": driver,
            }

            if labels:
                volume_config["Labels"] = labels
            else:
                volume_config["Labels"] = {
                    "created_by": "ptest",
                    "purpose": "test_isolation",
                }

            if driver_opts:
                volume_config["DriverOpts"] = driver_opts

            if driver_opts:
                volume_config["DriverOpts"] = driver_opts

            volume = self.client.volumes.create(volume_config)
            logger.info(f"Created volume: {volume_name}")
            return volume

        except Exception as e:
            logger.error(f"Failed to create volume {volume_name}: {e}")
            return None

    def remove_volume(self, volume_name: str, force: bool = False) -> bool:
        """删除Docker卷"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating volume removal: {volume_name}"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            volume = self.client.volumes.get(volume_name)
            if volume:
                volume.remove(force=force)
                logger.info(f"Removed volume: {volume_name}")
                return True

            logger.info(f"Volume {volume_name} not found")
            return False

        except Exception as e:
            logger.error(f"Failed to remove volume {volume_name}: {e}")
            return False

    def list_volumes(self) -> List[Dict[str, Any]]:
        """列出所有Docker卷"""
        try:
            if not DOCKER_AVAILABLE:
                return []

            if not self.client:
                return []

            volumes = self.client.volumes.list()
            result = []

            volumes_data = volumes.get("Volumes", volumes)
            volumes_list = (
                volumes_data
                if isinstance(volumes_data, list)
                else [volumes]
                if volumes
                else []
            )

            for vol in volumes_list:
                attrs = vol.attrs if hasattr(vol, "attrs") else {}
                result.append(
                    {
                        "name": vol.name,
                        "driver": attrs.get("Driver"),
                        "mountpoint": attrs.get("Mountpoint"),
                        "created": attrs.get("CreatedAt"),
                        "status": attrs.get("Status"),
                        "labels": attrs.get("Labels", {}),
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Failed to list volumes: {e}")
            return []

    def prune_volumes(self) -> Dict[str, Any]:
        """清理未使用的Docker卷"""
        try:
            if not DOCKER_AVAILABLE:
                return {"VolumesDeleted": []}

            if not self.client:
                return {"VolumesDeleted": []}

            result = self.client.volumes.prune()
            logger.info(f"Pruned {len(result.get('VolumesDeleted', []))} volumes")
            return result

        except Exception as e:
            logger.error(f"Failed to prune volumes: {e}")
            return {"VolumesDeleted": []}

    def inspect_volume(self, volume_name: str) -> Optional[Dict[str, Any]]:
        """检查Docker卷详细信息"""
        try:
            if not DOCKER_AVAILABLE:
                return None

            if not self.client:
                return None

            volume = self.client.volumes.get(volume_name)
            return volume.attrs

        except Exception as e:
            logger.error(f"Failed to inspect volume {volume_name}: {e}")
            return None

    def get_volume_usage(self, volume_name: str) -> Dict[str, Any]:
        """获取Docker卷使用情况"""
        try:
            if not DOCKER_AVAILABLE:
                return {"size": 0, "container_count": 0}

            if not self.client:
                return {"size": 0, "container_count": 0}

            volume = self.client.volumes.get(volume_name)
            if not volume:
                return {"error": "Volume not found"}

            usage_data = volume.attrs.get("UsageData", {})
            containers = (
                usage_data.get("RefCount", 0) if isinstance(usage_data, dict) else 0
            )
            size = volume.attrs.get("Size", 0)

            return {
                "size": size,
                "container_count": containers,
                "mountpoint": volume.attrs.get("Mountpoint"),
            }
        except Exception as e:
            logger.error(f"Failed to get volume usage {volume_name}: {e}")
            return {"error": str(e)}

    def create_volume_snapshot(
        self, volume_name: str, snapshot_id: Optional[str] = None
    ) -> bool:
        """创建卷快照"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating volume snapshot: {volume_name}"
                )
                return True

            if not snapshot_id:
                snapshot_id = f"{volume_name}_snapshot_{uuid.uuid4().hex[:8]}"

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            volume = self.client.volumes.get(volume_name)
            if not volume:
                logger.error(f"Volume {volume_name} not found")
                return False

            mountpoint = volume.attrs.get("Mountpoint")
            if not mountpoint or not os.path.exists(mountpoint):
                logger.error(f"Volume mountpoint not accessible: {mountpoint}")
                return False

            snapshot_path = Path(mountpoint) / f".snapshot_{snapshot_id}"
            if snapshot_path.exists():
                shutil.rmtree(str(snapshot_path))

            shutil.copytree(
                mountpoint,
                str(snapshot_path),
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".dockerignore"),
            )

            logger.info(f"Created volume snapshot: {snapshot_id} for {volume_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create volume snapshot for {volume_name}: {e}")
            return False

    def restore_volume_snapshot(
        self, volume_name: str, snapshot_id: str, force: bool = False
    ) -> bool:
        """从快照恢复卷"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating volume restoration: {volume_name}"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            volume = self.client.volumes.get(volume_name)
            if not volume:
                logger.error(f"Volume {volume_name} not found")
                return False

            mountpoint = volume.attrs.get("Mountpoint")
            if not mountpoint:
                logger.error(f"Volume mountpoint not accessible: {mountpoint}")
                return False

            snapshot_path = Path(mountpoint) / f".snapshot_{snapshot_id}"
            if not snapshot_path.exists():
                logger.error(f"Snapshot not found: {snapshot_path}")
                return False

            if not os.path.exists(mountpoint):
                os.makedirs(mountpoint, exist_ok=True)

            if os.listdir(mountpoint) and not force:
                logger.warning("Volume mountpoint not empty, use force=True to restore")
                return False

            shutil.rmtree(mountpoint)
            shutil.copytree(str(snapshot_path), mountpoint, dirs_exist_ok=True)

            logger.info(f"Restored volume snapshot: {snapshot_id} to {volume_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore volume snapshot for {volume_name}: {e}")
            return False

    def delete_volume_snapshot(self, volume_name: str, snapshot_id: str) -> bool:
        """删除卷快照"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating snapshot deletion: {volume_name}"
                )
                return True

            volume = self.client.volumes.get(volume_name)
            if not volume:
                logger.warning(f"Volume {volume_name} not found")
                return True

            mountpoint = volume.attrs.get("Mountpoint")
            if not mountpoint:
                return True

            snapshot_path = Path(mountpoint) / f".snapshot_{snapshot_id}"
            if snapshot_path.exists():
                shutil.rmtree(str(snapshot_path))
                logger.info(f"Deleted volume snapshot: {snapshot_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete volume snapshot {snapshot_id}: {e}")
            return False

    def list_volume_snapshots(self, volume_name: str) -> List[str]:
        """列出卷的所有快照"""
        try:
            if not DOCKER_AVAILABLE:
                return []

            volume = self.client.volumes.get(volume_name)
            if not volume:
                return []

            mountpoint = volume.attrs.get("Mountpoint")
            if not mountpoint or not os.path.exists(mountpoint):
                return []

            snapshots = []
            for item in os.listdir(mountpoint):
                if item.startswith(".snapshot_"):
                    snapshot_id = item.replace(".snapshot_", "")
                    snapshots.append(snapshot_id)

            return sorted(snapshots)

        except Exception as e:
            logger.error(f"Failed to list volume snapshots for {volume_name}: {e}")
            return []
