# tests/unit/problem/test_field_mapping.py
"""REQ-003 字段命名收口 - 字段映射测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from ptest.app.workflow import (
    PROBLEM_OUTPUT_SCHEMA,
    _apply_output_schema,
    WorkflowService,
)
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


class TestApplyOutputSchema:
    """测试 _apply_output_schema 函数"""

    def test_applies_field_mapping(self):
        """测试：字段映射正确应用"""
        payload = {
            "preservation_status": "success",
            "latest_action": "preserved",
            "object_refs": ["obj1"],
            "artifact_refs": {"art1": "path1"},
            "log_refs": {"log1": "path2"},
        }
        result = _apply_output_schema(payload)

        # 验证新字段存在
        assert result["preservation_integrity"] == "success"
        assert result["last_recovery_action"] == "preserved"
        assert result["objects"] == ["obj1"]
        assert result["artifacts"] == {"art1": "path1"}
        assert result["logs"] == {"log1": "path2"}

    def test_preserves_old_fields(self):
        """测试：旧字段保留"""
        payload = {
            "preservation_status": "success",
            "latest_action": "preserved",
        }
        result = _apply_output_schema(payload)

        # 验证旧字段仍然存在
        assert result["preservation_status"] == "success"
        assert result["latest_action"] == "preserved"

    def test_adds_meta_information(self):
        """测试：添加 _meta 元数据"""
        payload = {"problem_id": "prob_1"}
        result = _apply_output_schema(payload)

        # 验证 _meta 存在
        assert "_meta" in result
        assert "field_aliases" in result["_meta"]
        assert "deprecated_fields" in result["_meta"]

    def test_does_not_overwrite_existing_new_field(self):
        """测试：不覆盖已存在的新字段"""
        payload = {
            "preservation_status": "success",
            "preservation_integrity": "custom_value",
        }
        result = _apply_output_schema(payload)

        # 验证不覆盖
        assert result["preservation_integrity"] == "custom_value"

    def test_empty_payload(self):
        """测试：空 payload"""
        payload = {}
        result = _apply_output_schema(payload)

        # 验证仍然添加 _meta
        assert "_meta" in result

    def test_custom_schema(self):
        """测试：自定义 schema"""
        payload = {"old_field": "value"}
        custom_schema = {"old_field": "new_field"}
        result = _apply_output_schema(payload, schema=custom_schema)

        # 验证自定义映射
        assert result["new_field"] == "value"
        assert result["old_field"] == "value"


class TestProblemRecordPayloadFieldMapping:
    """测试 _problem_record_payload 字段映射"""

    def test_payload_contains_new_fields(self, workflow: WorkflowService):
        """测试：payload 包含新字段"""
        # 创建 problem record
        record = ProblemRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
            preservation_status="success",
            latest_action="preserved",
            object_refs=["obj1"],
            artifact_refs={"art1": "path1"},
            log_refs={"log1": "path2"},
        )

        # 获取 payload
        payload = workflow._problem_record_payload(record)

        # 验证新字段存在
        assert "preservation_integrity" in payload
        assert "last_recovery_action" in payload
        assert "objects" in payload
        assert "artifacts" in payload
        assert "logs" in payload

    def test_payload_preserves_old_fields(self, workflow: WorkflowService):
        """测试：payload 保留旧字段"""
        record = ProblemRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
            preservation_status="success",
            latest_action="preserved",
            object_refs=["obj1"],
        )

        payload = workflow._problem_record_payload(record)

        # 验证旧字段仍然存在
        assert "preservation_status" in payload
        assert "latest_action" in payload
        assert "object_refs" in payload

    def test_payload_new_and_old_values_match(self, workflow: WorkflowService):
        """测试：新旧字段值一致"""
        record = ProblemRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
            preservation_status="success",
            latest_action="preserved",
            object_refs=["obj1"],
            artifact_refs={"art1": "path1"},
            log_refs={"log1": "path2"},
        )

        payload = workflow._problem_record_payload(record)

        # 验证新旧字段值相同
        assert payload["preservation_integrity"] == payload["preservation_status"]
        assert payload["last_recovery_action"] == payload["latest_action"]
        assert payload["objects"] == payload["object_refs"]
        assert payload["artifacts"] == payload["artifact_refs"]
        assert payload["logs"] == payload["log_refs"]


class TestProblemAssetsPayloadFieldMapping:
    """测试 _problem_assets_payload 字段映射"""

    def test_payload_contains_new_fields(self, workflow: WorkflowService):
        """测试：payload 包含新字段"""
        assets = ProblemAssetRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
            preservation_status="success",
            object_refs=["obj1"],
            artifact_refs={"art1": "path1"},
            log_refs={"log1": "path2"},
        )

        payload = workflow._problem_assets_payload(assets)

        # 验证新字段存在
        assert "preservation_integrity" in payload
        assert "objects" in payload
        assert "artifacts" in payload
        assert "logs" in payload

    def test_payload_preserves_old_fields(self, workflow: WorkflowService):
        """测试：payload 保留旧字段"""
        assets = ProblemAssetRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
            preservation_status="success",
            object_refs=["obj1"],
        )

        payload = workflow._problem_assets_payload(assets)

        # 验证旧字段仍然存在
        assert "preservation_status" in payload
        assert "object_refs" in payload


class TestFieldMappingConstants:
    """测试字段映射常量"""

    def test_problem_output_schema_keys(self):
        """测试：PROBLEM_OUTPUT_SCHEMA 包含预期的字段"""
        expected_keys = {
            "preservation_status",
            "latest_action",
            "object_refs",
            "artifact_refs",
            "log_refs",
        }
        assert set(PROBLEM_OUTPUT_SCHEMA.keys()) == expected_keys

    def test_problem_output_schema_values(self):
        """测试：PROBLEM_OUTPUT_SCHEMA 包含预期的映射值"""
        expected_values = {
            "preservation_integrity",
            "last_recovery_action",
            "objects",
            "artifacts",
            "logs",
        }
        assert set(PROBLEM_OUTPUT_SCHEMA.values()) == expected_values
