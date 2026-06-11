# tests/unit/problem/test_crash_linkage.py
"""P5-D 受管对象 Crash 联动测试"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from ptest.app.workflow import WorkflowService
from ptest.models import (
    OBJECT_STATUS_CRASH_PRESERVED,
    ManagedObjectRecord,
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
def installed_object(workflow: WorkflowService) -> ManagedObjectRecord:
    """创建已安装的 object"""
    workflow.install_object(
        "database_server",
        "mysql_demo",
        {"workspace_path": str(workflow.root_path)},
    )
    return workflow.storage.get_object("mysql_demo")


class TestUpdateObjectAfterCrash:
    """测试 crash 后 object 状态更新"""

    def test_update_object_status(self, workflow: WorkflowService, installed_object):
        """测试：crash 后 object 状态更新为 crash_preserved"""
        # 执行
        workflow._update_object_after_crash(
            object_name="mysql_demo",
            execution_id="exec_1",
            problem_id="prob_1",
            crash_info={"signal": "SIGABRT", "returncode": -6},
        )

        # 验证
        record = workflow.storage.get_object("mysql_demo")
        assert record.status == OBJECT_STATUS_CRASH_PRESERVED

    def test_update_crash_capture_metadata(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：crash_capture 元数据正确更新"""
        # 执行
        workflow._update_object_after_crash(
            object_name="mysql_demo",
            execution_id="exec_1",
            problem_id="prob_1",
            crash_info={"signal": "SIGABRT", "returncode": -6},
        )

        # 验证
        record = workflow.storage.get_object("mysql_demo")
        crash_capture = record.metadata.get("crash_capture", {})
        assert crash_capture.get("crash_count") == 1
        assert crash_capture.get("last_execution_id") == "exec_1"
        assert crash_capture.get("last_problem_id") == "prob_1"
        assert crash_capture.get("last_crash_time") is not None

    def test_update_crash_history(self, workflow: WorkflowService, installed_object):
        """测试：crash_history 正确记录"""
        # 执行
        workflow._update_object_after_crash(
            object_name="mysql_demo",
            execution_id="exec_1",
            problem_id="prob_1",
            crash_info={"signal": "SIGABRT", "returncode": -6},
        )

        # 验证
        record = workflow.storage.get_object("mysql_demo")
        crash_capture = record.metadata.get("crash_capture", {})
        history = crash_capture.get("crash_history", [])
        assert len(history) == 1
        assert history[0]["execution_id"] == "exec_1"
        assert history[0]["problem_id"] == "prob_1"
        assert history[0]["signal"] == "SIGABRT"

    def test_crash_count_increments(self, workflow: WorkflowService, installed_object):
        """测试：crash_count 正确累计"""
        # 执行 3 次 crash
        for i in range(3):
            workflow._update_object_after_crash(
                object_name="mysql_demo",
                execution_id=f"exec_{i}",
                problem_id=f"prob_{i}",
                crash_info={"signal": "SIGABRT"},
            )

        # 验证
        record = workflow.storage.get_object("mysql_demo")
        crash_capture = record.metadata.get("crash_capture", {})
        assert crash_capture.get("crash_count") == 3

    def test_crash_history_limit(self, workflow: WorkflowService, installed_object):
        """测试：crash_history 只保留最近 10 条"""
        # 执行 11 次 crash
        for i in range(11):
            workflow._update_object_after_crash(
                object_name="mysql_demo",
                execution_id=f"exec_{i}",
                problem_id=f"prob_{i}",
                crash_info={"signal": "SIGABRT"},
            )

        # 验证
        record = workflow.storage.get_object("mysql_demo")
        crash_capture = record.metadata.get("crash_capture", {})
        history = crash_capture.get("crash_history", [])
        assert len(history) == 10
        assert crash_capture.get("crash_count") == 11
        # 最早的记录被移除
        assert history[0]["problem_id"] == "prob_1"

    def test_skip_when_object_not_exist(self, workflow: WorkflowService):
        """测试：object 不存在时静默跳过"""
        # 执行 - 不应抛出异常
        workflow._update_object_after_crash(
            object_name="nonexistent",
            execution_id="exec_1",
            problem_id="prob_1",
            crash_info={"signal": "SIGABRT"},
        )

    def test_skip_when_object_name_empty(self, workflow: WorkflowService):
        """测试：object_name 为空时静默跳过"""
        # 执行 - 不应抛出异常
        workflow._update_object_after_crash(
            object_name="",
            execution_id="exec_1",
            problem_id="prob_1",
            crash_info={"signal": "SIGABRT"},
        )

    def test_log_warning_when_update_failed(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：更新失败时记录警告日志"""
        # mock 失败
        with patch.object(
            workflow.storage,
            "upsert_object",
            side_effect=Exception("write failed"),
        ):
            # 执行 - 不应抛出异常
            workflow._update_object_after_crash(
                object_name="mysql_demo",
                execution_id="exec_1",
                problem_id="prob_1",
                crash_info={"signal": "SIGABRT"},
            )


class TestListObjectIssues:
    """测试 object issues 查询"""

    def test_list_issues_empty(self, workflow: WorkflowService, installed_object):
        """测试：无关联 problem 时返回空列表"""
        issues = workflow.list_object_issues("mysql_demo")
        assert issues == []

    def test_list_issues_with_problems(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：列出关联的 problem"""
        # 创建 problem 记录
        for i in range(3):
            problem = ProblemRecord(
                problem_id=f"prob_{i}",
                problem_type="crash_dump",
                summary=f"Crash {i}",
                object_refs=["mysql_demo"],
                created_at=datetime.now().isoformat(),
            )
            assets = ProblemAssetRecord(
                problem_id=f"prob_{i}",
                problem_type="crash_dump",
                summary=f"Crash {i}",
            )
            workflow._save_problem_bundle(problem, assets)

        # 查询
        issues = workflow.list_object_issues("mysql_demo")

        # 验证
        assert len(issues) == 3

    def test_list_issues_filter_by_type(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：按 problem_type 过滤"""
        # 创建不同类型的 problem
        for problem_type in ["crash_dump", "api_response", "crash_dump"]:
            problem = ProblemRecord(
                problem_id=f"prob_{problem_type}_{id(object)}",
                problem_type=problem_type,
                summary=f"Problem {problem_type}",
                object_refs=["mysql_demo"],
                created_at=datetime.now().isoformat(),
            )
            assets = ProblemAssetRecord(
                problem_id=f"prob_{problem_type}_{id(object)}",
                problem_type=problem_type,
                summary=f"Problem {problem_type}",
            )
            workflow._save_problem_bundle(problem, assets)

        # 查询 crash_dump 类型
        issues = workflow.list_object_issues("mysql_demo", problem_type="crash_dump")

        # 验证
        assert all(issue["problem_type"] == "crash_dump" for issue in issues)

    def test_list_issues_limit(self, workflow: WorkflowService, installed_object):
        """测试：限制返回数量"""
        # 创建 5 个 problem
        for i in range(5):
            problem = ProblemRecord(
                problem_id=f"prob_{i}",
                problem_type="crash_dump",
                summary=f"Crash {i}",
                object_refs=["mysql_demo"],
                created_at=datetime.now().isoformat(),
            )
            assets = ProblemAssetRecord(
                problem_id=f"prob_{i}",
                problem_type="crash_dump",
                summary=f"Crash {i}",
            )
            workflow._save_problem_bundle(problem, assets)

        # 查询限制 3 条
        issues = workflow.list_object_issues("mysql_demo", limit=3)

        # 验证
        assert len(issues) == 3


class TestGetObjectCrashInfo:
    """测试 object crash info 查询"""

    def test_get_crash_info_not_found(self, workflow: WorkflowService):
        """测试：object 不存在时返回 not_found"""
        result = workflow.get_object_crash_info("nonexistent")
        assert result["object_found"] is False

    def test_get_crash_info_no_crash(self, workflow: WorkflowService, installed_object):
        """测试：无 crash 信息时返回 None"""
        result = workflow.get_object_crash_info("mysql_demo")
        assert result["object_found"] is True
        assert result["crash_info"] is None

    def test_get_crash_info_with_crash(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：有 crash 信息时返回正确数据"""
        # 模拟 crash
        workflow._update_object_after_crash(
            object_name="mysql_demo",
            execution_id="exec_1",
            problem_id="prob_1",
            crash_info={"signal": "SIGABRT", "returncode": -6},
        )

        # 查询
        result = workflow.get_object_crash_info("mysql_demo")

        # 验证
        assert result["object_found"] is True
        assert result["crash_info"] is not None
        assert result["crash_info"]["crash_count"] == 1
        assert result["crash_info"]["last_problem_id"] == "prob_1"


class TestGetObjectStatusWithCrashInfo:
    """测试 object status 增强"""

    def test_status_without_crash_info(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：无 crash 信息时 status 正常返回"""
        result = workflow.get_object_status("mysql_demo")
        assert result["success"] is True
        assert "crash_info" not in result.get("object", {})

    def test_status_with_crash_info(self, workflow: WorkflowService, installed_object):
        """测试：有 crash 信息时 status 包含 crash_info"""
        # 模拟 crash
        workflow._update_object_after_crash(
            object_name="mysql_demo",
            execution_id="exec_1",
            problem_id="prob_1",
            crash_info={"signal": "SIGABRT"},
        )

        # 查询
        result = workflow.get_object_status("mysql_demo")

        # 验证
        assert result["success"] is True
        obj_data = result.get("object", {})
        assert "crash_info" in obj_data
        assert obj_data["crash_info"]["crash_count"] == 1


class TestBuildObjectCrashRecommendations:
    """测试 crash 恢复建议"""

    def test_recommendations_include_basic_actions(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：建议包含基本动作"""
        # 创建 problem
        problem = ProblemRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
            object_refs=["mysql_demo"],
            execution_id="exec_1",
        )
        assets = ProblemAssetRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
        )

        # 获取建议
        recommendations = workflow._build_object_crash_recommendations(
            "mysql_demo", problem, assets
        )

        # 验证
        actions = [r["action"] for r in recommendations]
        assert "view_details" in actions
        assert "check_object" in actions
        assert "list_issues" in actions
        assert "restart_object" in actions

    def test_recommendations_for_sigsegv(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：SIGSEGV crash 的建议"""
        # 创建 problem
        problem = ProblemRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="SIGSEGV crash",
            object_refs=["mysql_demo"],
            execution_id="exec_1",
        )
        assets = ProblemAssetRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="SIGSEGV crash",
            details={"process_result": {"signal": "SIGSEGV"}},
        )

        # 获取建议
        recommendations = workflow._build_object_crash_recommendations(
            "mysql_demo", problem, assets
        )

        # 验证
        actions = [r["action"] for r in recommendations]
        assert "analyze_core" in actions

    def test_recommendations_for_sigabrt(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：SIGABRT crash 的建议"""
        # 创建 problem
        problem = ProblemRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="SIGABRT crash",
            object_refs=["mysql_demo"],
            execution_id="exec_1",
        )
        assets = ProblemAssetRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="SIGABRT crash",
            details={"process_result": {"signal": "SIGABRT"}},
        )

        # 获取建议
        recommendations = workflow._build_object_crash_recommendations(
            "mysql_demo", problem, assets
        )

        # 验证
        actions = [r["action"] for r in recommendations]
        assert "check_logs" in actions


class TestObjectSummaryBackwardCompatibility:
    """测试 object_summary 向后兼容性"""

    def test_object_summary_contains_both_fields(
        self, workflow: WorkflowService, installed_object
    ):
        """测试：object_summary 同时包含 object_name 和 service_name"""
        # 获取 object summary
        summary = workflow._build_crash_dump_object_summary("mysql_demo")

        # 验证同时包含两个字段
        assert "object_name" in summary
        assert "service_name" in summary
        assert summary["object_name"] == "mysql_demo"
        assert summary["service_name"] == "mysql_demo"

    def test_object_summary_not_found_contains_both_fields(
        self, workflow: WorkflowService
    ):
        """测试：object 不存在时也同时包含两个字段"""
        # 获取 object summary
        summary = workflow._build_crash_dump_object_summary("nonexistent")

        # 验证同时包含两个字段
        assert "object_name" in summary
        assert "service_name" in summary
        assert summary["object_name"] == "nonexistent"
        assert summary["service_name"] == "nonexistent"
        assert summary["object_found"] is False

    def test_object_summary_empty_name_contains_both_fields(
        self, workflow: WorkflowService
    ):
        """测试：空名称时也同时包含两个字段"""
        # 获取 object summary
        summary = workflow._build_crash_dump_object_summary("")

        # 验证同时包含两个字段
        assert "object_name" in summary
        assert "service_name" in summary
        assert summary["object_name"] == ""
        assert summary["service_name"] == ""
        assert summary["object_found"] is False


class TestCrashLinkageIntegration:
    """集成测试：crash 联动完整流程"""

    def test_crash_updates_object_and_creates_problem(self, workflow: WorkflowService):
        """测试：crash 后同时更新 object 和创建 problem"""
        # 安装 object
        workflow.install_object(
            "database_server",
            "mysql_demo",
            {"workspace_path": str(workflow.root_path)},
        )

        # 创建 problem（模拟 crash_dump problem 创建流程）
        problem = ProblemRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
            object_refs=["mysql_demo"],
            execution_id="exec_1",
            created_at=datetime.now().isoformat(),
        )
        assets = ProblemAssetRecord(
            problem_id="prob_1",
            problem_type="crash_dump",
            summary="Test crash",
        )
        workflow._save_problem_bundle(problem, assets)

        # 模拟 crash 后更新
        workflow._update_object_after_crash(
            object_name="mysql_demo",
            execution_id="exec_1",
            problem_id="prob_1",
            crash_info={"signal": "SIGABRT", "returncode": -6},
        )

        # 验证 object 状态
        obj_record = workflow.storage.get_object("mysql_demo")
        assert obj_record.status == OBJECT_STATUS_CRASH_PRESERVED

        # 验证 object issues
        issues = workflow.list_object_issues("mysql_demo")
        assert len(issues) == 1
        assert issues[0]["problem_id"] == "prob_1"

        # 验证 object crash info
        crash_info = workflow.get_object_crash_info("mysql_demo")
        assert crash_info["crash_info"]["crash_count"] == 1
