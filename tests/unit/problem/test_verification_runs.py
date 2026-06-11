# tests/unit/problem/test_verification_runs.py
"""REQ-002 问题差异对比与多次验证记录 - 测试"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from ptest.app.workflow import WorkflowService
from ptest.models import (
    ProblemAssetRecord,
    ProblemRecoveryRecord,
    ProblemRecord,
)


@pytest.fixture()
def workflow(tmp_path: Path) -> WorkflowService:
    """创建测试用的 WorkflowService"""
    svc = WorkflowService(tmp_path)
    svc.init_environment(tmp_path)
    return svc


@pytest.fixture()
def problem_with_replays(workflow: WorkflowService) -> str:
    """创建带有多个 replay 记录的 problem"""
    # 创建 problem
    record = ProblemRecord(
        problem_id="prob_replay",
        problem_type="api_response",
        summary="Test API problem",
    )
    assets = ProblemAssetRecord(
        problem_id="prob_replay",
        problem_type="api_response",
        summary="Test API problem",
    )
    workflow._save_problem_bundle(record, assets)

    # 创建多个 recovery history 记录
    for i in range(3):
        recovery = ProblemRecoveryRecord(
            action_id=f"action_{i}",
            problem_id="prob_replay",
            problem_type="api_response",
            action_type="replay",
            mode="request_replay",
            success=True,
            status="completed",
            created_at=f"2026-06-12T00:{i:02d}:00",
            metadata={
                "result": {
                    "comparison": {
                        "expectation": {"reproduced": i < 2},
                        "assertion_outcome": "reproduced"
                        if i < 2
                        else "not_reproduced",
                    }
                }
            },
        )
        workflow.storage.save_problem_recovery_history(recovery)

    return "prob_replay"


class TestGetProblemVerificationRuns:
    """测试 get_problem_verification_runs 方法"""

    def test_get_runs_success(
        self, workflow: WorkflowService, problem_with_replays: str
    ):
        """测试：获取验证历史成功"""
        result = workflow.get_problem_verification_runs(problem_with_replays)

        assert result["success"] is True
        assert "data" in result
        assert result["data"]["problem_id"] == problem_with_replays

    def test_get_runs_total(self, workflow: WorkflowService, problem_with_replays: str):
        """测试：返回正确的总数"""
        result = workflow.get_problem_verification_runs(problem_with_replays)

        assert result["data"]["total"] == 3

    def test_get_runs_limit(self, workflow: WorkflowService, problem_with_replays: str):
        """测试：limit 参数正常工作"""
        result = workflow.get_problem_verification_runs(problem_with_replays, limit=2)

        assert len(result["data"]["runs"]) == 2
        assert result["data"]["total"] == 3

    def test_get_runs_offset(
        self, workflow: WorkflowService, problem_with_replays: str
    ):
        """测试：offset 参数正常工作"""
        result = workflow.get_problem_verification_runs(problem_with_replays, offset=1)

        assert len(result["data"]["runs"]) == 2
        assert result["data"]["total"] == 3

    def test_get_runs_summary(
        self, workflow: WorkflowService, problem_with_replays: str
    ):
        """测试：返回正确的摘要"""
        result = workflow.get_problem_verification_runs(problem_with_replays)

        summary = result["data"]["summary"]
        assert summary["run_count"] == 3
        assert summary["replay_count"] == 3
        assert summary["ever_reproduced"] is True
        assert summary["latest_result_status"] is not None

    def test_get_runs_not_found(self, workflow: WorkflowService):
        """测试：problem 不存在"""
        result = workflow.get_problem_verification_runs("nonexistent")

        assert result["success"] is False
        assert "does not exist" in result["message"].lower()

    def test_get_runs_empty_history(self, workflow: WorkflowService):
        """测试：无验证历史"""
        # 创建无 recovery 的 problem
        record = ProblemRecord(
            problem_id="prob_empty",
            problem_type="api_response",
            summary="Test problem",
        )
        assets = ProblemAssetRecord(
            problem_id="prob_empty",
            problem_type="api_response",
            summary="Test problem",
        )
        workflow._save_problem_bundle(record, assets)

        result = workflow.get_problem_verification_runs("prob_empty")

        assert result["success"] is True
        assert result["data"]["total"] == 0
        assert result["data"]["runs"] == []

    def test_get_runs_pagination(
        self, workflow: WorkflowService, problem_with_replays: str
    ):
        """测试：分页功能"""
        # 第一页
        result1 = workflow.get_problem_verification_runs(
            problem_with_replays, limit=2, offset=0
        )
        assert len(result1["data"]["runs"]) == 2

        # 第二页
        result2 = workflow.get_problem_verification_runs(
            problem_with_replays, limit=2, offset=2
        )
        assert len(result2["data"]["runs"]) == 1

        # 验证不同页的数据不同
        ids1 = {r["action_id"] for r in result1["data"]["runs"]}
        ids2 = {r["action_id"] for r in result2["data"]["runs"]}
        assert ids1 != ids2


class TestVerificationRunFromAction:
    """测试 _build_verification_run_from_action 静态方法"""

    def test_replay_reproduced(self):
        """测试：replay 复现成功"""
        action = {
            "action_id": "action_1",
            "action_type": "replay",
            "status": "completed",
            "success": True,
            "created_at": "2026-06-12T00:00:00",
            "mode": "request_replay",
            "metadata": {
                "result": {
                    "comparison": {
                        "expectation": {"reproduced": True},
                        "assertion_outcome": "reproduced",
                    }
                }
            },
        }

        run = WorkflowService._build_verification_run_from_action(action)

        assert run["result_status"] == "reproduced"
        assert run["reproduced"] is True
        assert run["action_type"] == "replay"

    def test_replay_not_reproduced(self):
        """测试：replay 未复现"""
        action = {
            "action_id": "action_2",
            "action_type": "replay",
            "status": "completed",
            "success": True,
            "created_at": "2026-06-12T00:00:00",
            "mode": "request_replay",
            "metadata": {
                "result": {
                    "comparison": {
                        "expectation": {"reproduced": False},
                        "assertion_outcome": "not_reproduced",
                    }
                }
            },
        }

        run = WorkflowService._build_verification_run_from_action(action)

        assert run["result_status"] == "not_reproduced"
        assert run["reproduced"] is False

    def test_replay_failed(self):
        """测试：replay 执行失败"""
        action = {
            "action_id": "action_3",
            "action_type": "replay",
            "status": "failed",
            "success": False,
            "created_at": "2026-06-12T00:00:00",
            "mode": "request_replay",
        }

        run = WorkflowService._build_verification_run_from_action(action)

        assert run["result_status"] == "failed"
        assert run["reproduced"] is None

    def test_recover_success(self):
        """测试：recover 成功"""
        action = {
            "action_id": "action_4",
            "action_type": "recover",
            "status": "completed",
            "success": True,
            "created_at": "2026-06-12T00:00:00",
            "mode": "recovery",
        }

        run = WorkflowService._build_verification_run_from_action(action)

        assert run["result_status"] == "recovered"

    def test_recover_plan_only(self):
        """测试：recover 仅计划"""
        action = {
            "action_id": "action_5",
            "action_type": "recover",
            "status": "prepared",
            "success": True,
            "created_at": "2026-06-12T00:00:00",
            "mode": "plan_only",
        }

        run = WorkflowService._build_verification_run_from_action(action)

        assert run["result_status"] == "inconclusive"


class TestHistoryVerificationSummary:
    """测试 _build_history_verification_summary 静态方法"""

    def test_summary_with_multiple_runs(self):
        """测试：多次运行的摘要"""
        runs = [
            {
                "action_type": "replay",
                "result_status": "reproduced",
                "created_at": "2026-06-12T00:00:00",
            },
            {
                "action_type": "replay",
                "result_status": "not_reproduced",
                "created_at": "2026-06-12T00:01:00",
            },
            {
                "action_type": "recover",
                "result_status": "recovered",
                "created_at": "2026-06-12T00:02:00",
            },
        ]

        summary = WorkflowService._build_history_verification_summary(runs)

        assert summary["run_count"] == 3
        assert summary["replay_count"] == 2
        assert summary["recover_count"] == 1
        assert summary["ever_reproduced"] is True
        # runs 按 created_at 降序排列，所以第一个是最新状态
        assert summary["latest_result_status"] == "reproduced"

    def test_summary_empty_runs(self):
        """测试：空运行列表的摘要"""
        runs = []

        summary = WorkflowService._build_history_verification_summary(runs)

        assert summary["run_count"] == 0
        assert summary["replay_count"] == 0
        assert summary["recover_count"] == 0
        assert summary["ever_reproduced"] is False
        assert summary["latest_result_status"] is None

    def test_summary_latest_reproduced_at(self):
        """测试：最近复现时间"""
        runs = [
            {
                "action_type": "replay",
                "result_status": "reproduced",
                "created_at": "2026-06-12T00:00:00",
            },
            {
                "action_type": "replay",
                "result_status": "not_reproduced",
                "created_at": "2026-06-12T00:01:00",
            },
        ]

        summary = WorkflowService._build_history_verification_summary(runs)

        assert summary["latest_reproduced_at"] == "2026-06-12T00:00:00"

    def test_summary_latest_successful_recover_at(self):
        """测试：最近恢复成功时间"""
        runs = [
            {
                "action_type": "recover",
                "result_status": "recovered",
                "created_at": "2026-06-12T00:00:00",
            },
            {
                "action_type": "recover",
                "result_status": "failed",
                "created_at": "2026-06-12T00:01:00",
            },
        ]

        summary = WorkflowService._build_history_verification_summary(runs)

        assert summary["latest_successful_recover_at"] == "2026-06-12T00:00:00"

    def test_summary_inconclusive_count(self):
        """测试：inconclusive 计数"""
        runs = [
            {
                "action_type": "replay",
                "result_status": "inconclusive",
                "created_at": "2026-06-12T00:00:00",
            },
            {
                "action_type": "replay",
                "result_status": "inconclusive",
                "created_at": "2026-06-12T00:01:00",
            },
            {
                "action_type": "replay",
                "result_status": "reproduced",
                "created_at": "2026-06-12T00:02:00",
            },
        ]

        summary = WorkflowService._build_history_verification_summary(runs)

        assert summary["inconclusive_count"] == 2
