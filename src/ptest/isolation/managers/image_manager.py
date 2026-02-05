"""
Docker镜像管理器

提供完整的Docker镜像管理功能，包括拉取、推送、构建、标签等
"""

from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

try:
    import docker  # noqa: F401

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

if DOCKER_AVAILABLE:
    from docker.errors import NotFound

from ...core import get_logger

logger = get_logger("image_manager")


class ImageManager:
    """Docker镜像管理器"""

    def __init__(self, docker_client, config: Dict[str, Any] | None = None):
        self.client = docker_client
        self.config = config or {}

    def pull_image(
        self,
        image_name: str,
        tag: str = "latest",
        auth_config: Dict[str, str] | None = None,
    ) -> bool:
        """拉取Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image pull: {image_name}:{tag}"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            full_image_name = f"{image_name}:{tag}"
            logger.info(f"Pulling image: {full_image_name}")

            try:
                self.client.images.get(full_image_name)
                logger.info(f"Image {full_image_name} already exists locally")
                return True
            except NotFound:
                logger.debug(
                    f"Image {full_image_name} not found locally, proceeding with pull"
                )

            kwargs: dict = {"tag": full_image_name}
            if auth_config:
                kwargs["auth_config"] = auth_config

            self.client.images.pull(**kwargs)
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
        """推送Docker镜像到仓库"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image push: {image_name}:{tag}"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            full_image_name = f"{image_name}:{tag}"
            logger.info(f"Pushing image: {full_image_name}")

            if registry:
                registry_image_name = f"{registry}/{full_image_name}"
                self.client.images.tag(full_image_name, registry_image_name)
                full_image_name = registry_image_name

            auth_config = None
            if username and password:
                auth_config = {"username": username, "password": password}

            for line in self.client.images.push(
                full_image_name, stream=True, decode=True, auth_config=auth_config
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

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            logger.info(f"Tagging image: {source} -> {target}")
            self.client.images.tag(source, target)
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
                    f"Docker SDK not available, simulating image save: {image_name}"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            logger.info(f"Saving image: {image_name} to {output_path}")

            output_path.parent.mkdir(parents=True, exist_ok=True)

            image = self.client.images.get(image_name)

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

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            logger.info(f"Loading image from: {input_path}")

            with open(input_path, "rb") as f:
                image_data = f.read()

            self.client.images.load(image_data)
            logger.info(f"Successfully loaded image from: {input_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load image from {input_path}: {e}")
            return False

    def build_image(
        self,
        dockerfile_path: Path,
        tag: str,
        buildargs: Dict[str, str] | None = None,
        build_context: Path | None = None,
        cache: bool = True,
        timeout: int = 1800,
        progress_callback: Callable[[Dict[str, Any]], None] | None = None,
    ) -> bool:
        """构建Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image build: {tag}"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            logger.info(f"Building image: {tag}")

            build_path = build_context or dockerfile_path.parent
            build_kwargs = {
                "path": str(build_path),
                "dockerfile": dockerfile_path.name,
                "tag": tag,
                "rm": True,
                "decode": True,
                "nocache": not cache,
            }

            if buildargs:
                build_kwargs["buildargs"] = buildargs

            image, build_logs = self.client.images.build(**build_kwargs)

            for chunk in build_logs:
                if "stream" in chunk:
                    log_line = chunk["stream"].strip()
                    if log_line:
                        logger.debug(f"Build: {log_line}")
                        if progress_callback:
                            progress_callback({"type": "log", "message": log_line})

            logger.info(f"Successfully built image: {tag}")
            return True

        except Exception as e:
            logger.error(f"Failed to build image {tag}: {e}")
            return False

    def remove_image(self, image_name: str, force: bool = False) -> bool:
        """删除Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                logger.warning(
                    f"Docker SDK not available, simulating image remove: {image_name}"
                )
                return True

            if not self.client:
                logger.error("Docker client not initialized")
                return False

            self.client.images.remove(image_name, force=force)
            logger.info(f"Removed image: {image_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove image {image_name}: {e}")
            return False

    def list_images(self, all_images: bool = False) -> List[Dict[str, Any]]:
        """列出所有Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                return []

            if not self.client:
                return []

            images = self.client.images.list(all=all_images)
            result = []

            for img in images:
                tags = img.tags
                result.append(
                    {
                        "id": img.id,
                        "short_id": img.short_id,
                        "tags": tags,
                        "created": img.attrs.get("Created"),
                        "size": img.attrs.get("Size"),
                        "labels": img.attrs.get("Labels", {}),
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Failed to list images: {e}")
            return []

    def prune_images(self, dangling_only: bool = True) -> Dict[str, Any]:
        """清理未使用的Docker镜像"""
        try:
            if not DOCKER_AVAILABLE:
                return {"ImagesDeleted": [], "SpaceReclaimed": 0}

            if not self.client:
                return {"ImagesDeleted": [], "SpaceReclaimed": 0}

            result = self.client.images.prune(dangling=dangling_only)
            logger.info(f"Pruned {len(result.get('ImagesDeleted', []))} images")
            return result

        except Exception as e:
            logger.error(f"Failed to prune images: {e}")
            return {"ImagesDeleted": [], "SpaceReclaimed": 0}

    def inspect_image(self, image_name: str) -> Optional[Dict[str, Any]]:
        """检查Docker镜像详细信息"""
        try:
            if not DOCKER_AVAILABLE:
                return None

            if not self.client:
                return None

            image = self.client.images.get(image_name)
            return image.attrs
        except Exception as e:
            logger.error(f"Failed to inspect image {image_name}: {e}")
            return None

    def cleanup_images(
        self,
        prune_dangling: bool = True,
        prune_unused: bool = False,
        min_age_hours: int | None = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """清理Docker镜像，支持定期清理策略"""
        try:
            if not DOCKER_AVAILABLE:
                return {"images_removed": 0, "space_reclaimed": 0}

            if not self.client:
                return {"images_removed": 0, "space_reclaimed": 0}

            results = {
                "dangling_removed": 0,
                "unused_removed": 0,
                "total_removed": 0,
                "space_reclaimed": 0,
                "images": [],
            }

            if prune_dangling:
                dangling_result = self.client.images.prune(filters={"dangling": True})
                results["dangling_removed"] = len(
                    dangling_result.get("ImagesDeleted", [])
                )
                results["space_reclaimed"] += dangling_result.get("SpaceReclaimed", 0)
                results["images"].extend(dangling_result.get("ImagesDeleted", []))

            if prune_unused and min_age_hours:
                all_images = self.client.images.list(all=True)
                import time

                cutoff_time = time.time() - (min_age_hours * 3600)

                unused_images = []
                for img in all_images:
                    created_at = img.attrs.get("Created", "")
                    if created_at and not any(img.tags):
                        try:
                            from datetime import datetime

                            created_dt = datetime.fromisoformat(
                                created_at.replace("Z", "+00:00").replace("+00:00", "")
                            )
                            if created_dt.timestamp() < cutoff_time:
                                unused_images.append(img.id)
                        except (ValueError, TypeError):
                            pass

                for img_id in unused_images:
                    if not dry_run:
                        self.client.images.remove(img_id)
                        logger.debug(f"Removed unused image: {img_id}")

                results["unused_removed"] = len(unused_images)
                results["images"].extend(unused_images)

            results["total_removed"] = (
                results["dangling_removed"] + results["unused_removed"]
            )

            if dry_run:
                logger.info(
                    f"Cleanup dry run: would remove {results['total_removed']} images"
                )
            else:
                logger.info(
                    f"Cleaned up {results['total_removed']} images, reclaimed {results['space_reclaimed']} bytes"
                )

            return results

        except Exception as e:
            logger.error(f"Failed to cleanup images: {e}")
            return {"images_removed": 0, "space_reclaimed": 0, "error": str(e)}
