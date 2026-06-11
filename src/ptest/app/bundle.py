# ptest/app/bundle.py
"""
Crash Evidence Bundle 模块

提供问题证据包的收集和导出功能。
"""

from __future__ import annotations

import json
import re
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core import get_logger

logger = get_logger("bundle")


def _sanitize_filename(name: str) -> str:
    """规范化文件名，移除或替换无效字符。

    Args:
        name: 原始文件名

    Returns:
        规范化后的文件名
    """
    # 替换路径分隔符和空格
    sanitized = re.sub(r"[/\\:\s]+", "_", name)
    # 移除其他特殊字符
    sanitized = re.sub(r'[<>"|?*]+', "", sanitized)
    # 移除首尾空格和点
    sanitized = sanitized.strip(" .")
    # 如果为空，使用默认值
    if not sanitized:
        sanitized = "unknown"
    return sanitized


def _collect_bundle_assets(
    problem_record: dict[str, Any],
    problem_assets: dict[str, Any],
    recovery_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """收集证据包资产。

    Args:
        problem_record: ProblemRecord 字典
        problem_assets: ProblemAssetRecord 字典
        recovery_history: 恢复历史记录列表

    Returns:
        证据包资产字典
    """
    assets: dict[str, Any] = {
        "problem_record": problem_record,
        "problem_assets": problem_assets,
        "recovery_history": recovery_history,
    }

    # 提取 details 中的关键字段
    details = problem_assets.get("details", {})
    if isinstance(details, dict):
        # crash 相关字段
        if "crash_target" in details:
            assets["crash_target"] = details["crash_target"]
        if "crash_event" in details:
            assets["crash_event"] = details["crash_event"]
        if "dump_refs" in details:
            assets["dump_refs"] = details["dump_refs"]
        if "dump_summary" in details:
            assets["dump_summary"] = details["dump_summary"]
        if "process_result" in details:
            assets["process_result"] = details["process_result"]
        if "core_environment" in details:
            assets["core_environment"] = details["core_environment"]
        if "log_window" in details:
            assets["log_window"] = details["log_window"]

        # object 相关字段
        if "object_summary" in details:
            assets["object_summary"] = details["object_summary"]
        if "object_artifacts" in details:
            assets["object_artifacts"] = details["object_artifacts"]

        # config 相关字段
        if "config_refs" in details:
            assets["config_refs"] = details["config_refs"]
        if "data_dir_summaries" in details:
            assets["data_dir_summaries"] = details["data_dir_summaries"]

    return assets


def _create_bundle_archive(
    assets: dict[str, Any],
    output_path: Path,
) -> Path:
    """创建证据包归档文件。

    Args:
        assets: 证据包资产字典
        output_path: 输出目录路径

    Returns:
        归档文件路径
    """
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 写入 manifest.json
        manifest = {
            "problem_id": assets.get("problem_record", {}).get("problem_id", ""),
            "problem_type": assets.get("problem_record", {}).get("problem_type", ""),
            "created_at": datetime.now().isoformat(),
            "version": "1.0.0",
            "files": [],
        }

        # 写入 problem_record.json
        record_path = tmp_path / "problem_record.json"
        record_path.write_text(
            json.dumps(assets.get("problem_record", {}), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest["files"].append({"name": "problem_record.json", "type": "json"})

        # 写入 problem_assets.json
        assets_path = tmp_path / "problem_assets.json"
        assets_path.write_text(
            json.dumps(assets.get("problem_assets", {}), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest["files"].append({"name": "problem_assets.json", "type": "json"})

        # 写入 recovery_history.json
        history_path = tmp_path / "recovery_history.json"
        history_path.write_text(
            json.dumps(
                assets.get("recovery_history", []), indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        manifest["files"].append({"name": "recovery_history.json", "type": "json"})

        # 写入 evidence.json（crash 相关证据）
        evidence = {}
        for key in [
            "crash_target",
            "crash_event",
            "dump_refs",
            "dump_summary",
            "process_result",
            "core_environment",
            "log_window",
            "object_summary",
            "object_artifacts",
            "config_refs",
            "data_dir_summaries",
        ]:
            if key in assets:
                evidence[key] = assets[key]

        if evidence:
            evidence_path = tmp_path / "evidence.json"
            evidence_path.write_text(
                json.dumps(evidence, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest["files"].append({"name": "evidence.json", "type": "json"})

        # 写入 manifest.json
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 创建 tar.gz 归档
        sanitized_id = _sanitize_filename(manifest["problem_id"])
        archive_path = output_path / f"bundle_{sanitized_id}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            for file_path in tmp_path.iterdir():
                tar.add(file_path, arcname=file_path.name)

        return archive_path


def export_problem_bundle(
    problem_id: str,
    problem_record: dict[str, Any],
    problem_assets: dict[str, Any],
    recovery_history: list[dict[str, Any]],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """导出问题证据包。

    Args:
        problem_id: 问题 ID
        problem_record: ProblemRecord 字典
        problem_assets: ProblemAssetRecord 字典
        recovery_history: 恢复历史记录列表
        output_path: 输出目录路径，默认为当前目录

    Returns:
        导出结果字典
    """
    try:
        # 收集资产
        assets = _collect_bundle_assets(
            problem_record,
            problem_assets,
            recovery_history,
        )

        # 确定输出路径
        if output_path is None:
            output_path = Path.cwd()
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        # 创建归档
        archive_path = _create_bundle_archive(assets, output_path)

        logger.info(f"Problem bundle exported: {archive_path}")

        return {
            "success": True,
            "status": "exported",
            "message": f"Problem bundle exported to {archive_path}",
            "data": {
                "problem_id": problem_id,
                "archive_path": str(archive_path),
                "archive_size": archive_path.stat().st_size,
                "created_at": datetime.now().isoformat(),
            },
        }

    except Exception as e:
        logger.exception("Failed to export problem bundle")
        return {
            "success": False,
            "status": "error",
            "message": f"Failed to export problem bundle: {e}",
            "error": str(e),
        }
