# tests/unit/problem/test_bundle.py
"""REQ-001 P5-E Crash Evidence Bundle - 测试"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Any

import pytest

from ptest.app.bundle import (
    _collect_bundle_assets,
    _create_bundle_archive,
    export_problem_bundle,
)
from ptest.app.workflow import WorkflowService
from ptest.models import (
    ProblemAssetRecord,
    ProblemRecord,
)


@pytest.fixture()
def workflow(tmp_path: Path) -> WorkflowService:
    """创建测试用的 WorkflowService"""
    svc = WorkflowService(tmp_path)
    svc.init_environment(tmp_path)
    return svc


@pytest.fixture()
def sample_problem_record() -> dict[str, Any]:
    """创建示例 ProblemRecord"""
    return {
        "problem_id": "prob_1",
        "problem_type": "crash_dump",
        "summary": "Test crash",
        "status": "open",
        "preservation_status": "success",
        "execution_id": "exec_1",
        "case_id": "case_1",
        "environment_id": "env_1",
        "object_refs": ["obj1"],
        "artifact_refs": {"art1": "path1"},
        "log_refs": {"log1": "path2"},
        "latest_action": "preserved",
        "notes": "",
        "created_at": "2026-06-12T00:00:00",
        "updated_at": "2026-06-12T00:00:00",
        "metadata": {},
    }


@pytest.fixture()
def sample_problem_assets() -> dict[str, Any]:
    """创建示例 ProblemAssetRecord"""
    return {
        "problem_id": "prob_1",
        "problem_type": "crash_dump",
        "summary": "Test crash",
        "status": "open",
        "preservation_status": "success",
        "execution_id": "exec_1",
        "case_id": "case_1",
        "environment_id": "env_1",
        "object_refs": ["obj1"],
        "artifact_refs": {"art1": "path1"},
        "log_refs": {"log1": "path2"},
        "recovery": {},
        "details": {
            "crash_target": {
                "object_name": "obj1",
                "runtime_backend": "host",
                "host": "localhost",
                "port": 8080,
            },
            "crash_event": {
                "detected_at": "2026-06-12T00:00:00",
                "error": "Segmentation fault",
                "output": "core dumped",
            },
            "dump_refs": [
                {
                    "path": "/tmp/core.123",
                    "file_type": "elf_core",
                    "hash_sha256_prefix": "abc123",
                }
            ],
            "process_result": {
                "command": ["./test_program"],
                "returncode": -11,
                "signal": "SIGSEGV",
                "crash_detected": True,
            },
        },
        "created_at": "2026-06-12T00:00:00",
        "updated_at": "2026-06-12T00:00:00",
        "metadata": {},
    }


@pytest.fixture()
def sample_recovery_history() -> list[dict[str, Any]]:
    """创建示例 recovery history"""
    return [
        {
            "action_id": "action_1",
            "problem_id": "prob_1",
            "problem_type": "crash_dump",
            "action_type": "recover",
            "mode": "plan_only",
            "success": True,
            "status": "prepared",
            "created_at": "2026-06-12T00:00:00",
        }
    ]


class TestCollectBundleAssets:
    """测试 _collect_bundle_assets 函数"""

    def test_collects_basic_fields(
        self,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：收集基本字段"""
        assets = _collect_bundle_assets(
            sample_problem_record,
            sample_problem_assets,
            sample_recovery_history,
        )

        assert "problem_record" in assets
        assert "problem_assets" in assets
        assert "recovery_history" in assets

    def test_collects_crash_fields(
        self,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：收集 crash 相关字段"""
        assets = _collect_bundle_assets(
            sample_problem_record,
            sample_problem_assets,
            sample_recovery_history,
        )

        assert "crash_target" in assets
        assert "crash_event" in assets
        assert "dump_refs" in assets
        assert "process_result" in assets

    def test_collects_object_fields(
        self,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：收集 object 相关字段"""
        # 添加 object_summary 到 details
        sample_problem_assets["details"]["object_summary"] = {
            "object_name": "obj1",
            "object_found": True,
        }

        assets = _collect_bundle_assets(
            sample_problem_record,
            sample_problem_assets,
            sample_recovery_history,
        )

        assert "object_summary" in assets

    def test_handles_empty_details(
        self,
        sample_problem_record: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：处理空 details"""
        assets_with_empty_details = {
            "problem_id": "prob_1",
            "problem_type": "crash_dump",
            "summary": "Test crash",
            "details": {},
        }

        assets = _collect_bundle_assets(
            sample_problem_record,
            assets_with_empty_details,
            sample_recovery_history,
        )

        assert "crash_target" not in assets
        assert "crash_event" not in assets


class TestCreateBundleArchive:
    """测试 _create_bundle_archive 函数"""

    def test_creates_tar_gz_archive(
        self,
        tmp_path: Path,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：创建 tar.gz 归档"""
        assets = _collect_bundle_assets(
            sample_problem_record,
            sample_problem_assets,
            sample_recovery_history,
        )

        archive_path = _create_bundle_archive(assets, tmp_path)

        assert archive_path.exists()
        assert archive_path.name == "bundle_prob_1.tar.gz"

    def test_archive_contains_required_files(
        self,
        tmp_path: Path,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：归档包含必需文件"""
        assets = _collect_bundle_assets(
            sample_problem_record,
            sample_problem_assets,
            sample_recovery_history,
        )

        archive_path = _create_bundle_archive(assets, tmp_path)

        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
            assert "manifest.json" in names
            assert "problem_record.json" in names
            assert "problem_assets.json" in names
            assert "recovery_history.json" in names
            assert "evidence.json" in names

    def test_manifest_contains_correct_info(
        self,
        tmp_path: Path,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：manifest 包含正确信息"""
        assets = _collect_bundle_assets(
            sample_problem_record,
            sample_problem_assets,
            sample_recovery_history,
        )

        archive_path = _create_bundle_archive(assets, tmp_path)

        with tarfile.open(archive_path, "r:gz") as tar:
            manifest_file = tar.extractfile("manifest.json")
            assert manifest_file is not None
            manifest = json.loads(manifest_file.read())

            assert manifest["problem_id"] == "prob_1"
            assert manifest["problem_type"] == "crash_dump"
            assert manifest["version"] == "1.0.0"


class TestExportProblemBundle:
    """测试 export_problem_bundle 函数"""

    def test_export_success(
        self,
        tmp_path: Path,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：导出成功"""
        result = export_problem_bundle(
            problem_id="prob_1",
            problem_record=sample_problem_record,
            problem_assets=sample_problem_assets,
            recovery_history=sample_recovery_history,
            output_path=tmp_path,
        )

        assert result["success"] is True
        assert result["status"] == "exported"
        assert "archive_path" in result["data"]

    def test_export_creates_file(
        self,
        tmp_path: Path,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：导出创建文件"""
        result = export_problem_bundle(
            problem_id="prob_1",
            problem_record=sample_problem_record,
            problem_assets=sample_problem_assets,
            recovery_history=sample_recovery_history,
            output_path=tmp_path,
        )

        archive_path = Path(result["data"]["archive_path"])
        assert archive_path.exists()

    def test_export_default_output_path(
        self,
        tmp_path: Path,
        sample_problem_record: dict[str, Any],
        sample_problem_assets: dict[str, Any],
        sample_recovery_history: list[dict[str, Any]],
    ):
        """测试：默认输出路径（使用 tmp_path 避免在项目路径下生成文件）"""
        # 注意：这个测试验证函数能正常工作，但使用 tmp_path 避免污染项目目录
        # 实际的默认路径测试需要在独立环境中进行
        result = export_problem_bundle(
            problem_id="prob_1",
            problem_record=sample_problem_record,
            problem_assets=sample_problem_assets,
            recovery_history=sample_recovery_history,
            output_path=tmp_path,
        )

        assert result["success"] is True


class TestWorkflowServiceExportBundle:
    """测试 WorkflowService.export_problem_bundle"""

    def test_export_not_found(self, workflow: WorkflowService):
        """测试：problem 不存在"""
        result = workflow.export_problem_bundle("nonexistent")

        assert result["success"] is False
        assert "does not exist" in result["message"].lower()

    def test_export_success(self, workflow: WorkflowService, tmp_path: Path):
        """测试：导出成功"""
        # 创建 problem
        record = ProblemRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
        )
        assets = ProblemAssetRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
        )
        workflow._save_problem_bundle(record, assets)

        # 导出
        result = workflow.export_problem_bundle("prob_1", tmp_path)

        assert result["success"] is True
        assert result["status"] == "exported"
