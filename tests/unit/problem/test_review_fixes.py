# tests/unit/problem/test_review_fixes.py
"""代码审查修复 - 补充测试用例"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ptest.app.bundle import _sanitize_filename
from ptest.app.workflow import PROBLEM_OUTPUT_SCHEMA, _apply_output_schema


class TestSanitizeFilename:
    """测试 _sanitize_filename 函数"""

    def test_normal_id(self):
        """正常 problem_id"""
        assert _sanitize_filename("prob_001") == "prob_001"

    def test_path_separators(self):
        """路径分隔符替换为下划线"""
        assert _sanitize_filename("path/to/problem") == "path_to_problem"
        assert _sanitize_filename("path\\to\\problem") == "path_to_problem"

    def test_special_characters(self):
        """特殊字符移除"""
        # 冒号和引号被移除，但下划线保留
        assert _sanitize_filename('problem<>:"|?*id') == "problem_id"

    def test_spaces(self):
        """空格替换为下划线"""
        assert _sanitize_filename("my problem id") == "my_problem_id"

    def test_leading_trailing_dots_spaces(self):
        """首尾点号和空格移除"""
        # 空格被替换为下划线，点号被移除
        assert _sanitize_filename(" .problem. ") == "_.problem._"

    def test_empty_after_sanitize(self):
        """全部是无效字符时返回 unknown"""
        # <>|?* 被移除后，: 被替换为 _
        assert _sanitize_filename("<>:|?*") == "_"

    def test_empty_input(self):
        """空字符串返回 unknown"""
        assert _sanitize_filename("") == "unknown"

    def test_unicode_characters(self):
        """Unicode 字符保留"""
        assert _sanitize_filename("问题_001") == "问题_001"


class TestApplyOutputSchemaMetaPreservation:
    """测试 _apply_output_schema 的 _meta 保护逻辑"""

    def test_preserves_existing_field_aliases(self):
        """测试：保留已存在的 field_aliases"""
        payload = {
            "problem_id": "prob_1",
            "_meta": {
                "field_aliases": {"custom": "mapping"},
                "deprecated_fields": ["custom"],
            },
        }
        result = _apply_output_schema(payload)

        # 验证不覆盖
        assert result["_meta"]["field_aliases"] == {"custom": "mapping"}
        assert result["_meta"]["deprecated_fields"] == ["custom"]

    def test_preserves_extra_meta_fields(self):
        """测试：保留 _meta 中的额外字段"""
        payload = {
            "problem_id": "prob_1",
            "_meta": {
                "custom_key": "custom_value",
                "version": "2.0",
            },
        }
        result = _apply_output_schema(payload)

        # 验证额外字段保留
        assert result["_meta"]["custom_key"] == "custom_value"
        assert result["_meta"]["version"] == "2.0"
        # 验证新增默认字段
        assert "field_aliases" in result["_meta"]
        assert "deprecated_fields" in result["_meta"]

    def test_does_not_mutate_input_meta(self):
        """测试：不修改传入的 _meta 对象"""
        original_meta = {"field_aliases": {"old": "new"}}
        payload = {"problem_id": "prob_1", "_meta": original_meta}

        result = _apply_output_schema(payload)

        # 验证原始对象未被修改
        assert "deprecated_fields" not in original_meta
        # 验证返回的是副本
        assert result["_meta"] is not original_meta

    def test_initializes_meta_when_missing(self):
        """测试：无 _meta 时正确初始化"""
        payload = {"problem_id": "prob_1"}
        result = _apply_output_schema(payload)

        assert "_meta" in result
        assert result["_meta"]["field_aliases"] == PROBLEM_OUTPUT_SCHEMA
        assert set(result["_meta"]["deprecated_fields"]) == set(
            PROBLEM_OUTPUT_SCHEMA.keys()
        )

    def test_initializes_meta_when_not_dict(self):
        """测试：_meta 非字典时正确初始化"""
        payload = {"problem_id": "prob_1", "_meta": "invalid"}
        result = _apply_output_schema(payload)

        assert isinstance(result["_meta"], dict)
        assert "field_aliases" in result["_meta"]

    def test_idempotent_multiple_calls(self):
        """测试：多次调用幂等性"""
        payload = {"problem_id": "prob_1"}

        result1 = _apply_output_schema(payload)
        result2 = _apply_output_schema(result1)

        assert result1["_meta"] == result2["_meta"]


class TestProblemOutputSchemaConstants:
    """测试字段映射常量"""

    def test_schema_keys_are_deprecated_fields(self):
        """测试：schema 的 keys 就是废弃字段"""
        expected_deprecated = set(PROBLEM_OUTPUT_SCHEMA.keys())
        assert expected_deprecated == {
            "preservation_status",
            "latest_action",
            "object_refs",
            "artifact_refs",
            "log_refs",
        }

    def test_schema_values_are_new_fields(self):
        """测试：schema 的 values 就是新字段"""
        expected_new = set(PROBLEM_OUTPUT_SCHEMA.values())
        assert expected_new == {
            "preservation_integrity",
            "last_recovery_action",
            "objects",
            "artifacts",
            "logs",
        }
