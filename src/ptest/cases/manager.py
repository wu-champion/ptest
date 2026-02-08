# ptest/cases/manager.py
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from .result import TestCaseResult
from .executor import TestExecutor

try:
    from ..utils import get_colored_text
except ImportError:

    def get_colored_text(text: Any, color_code: Any) -> str:
        return str(text)


class CaseManager:
    """测试用例管理器"""

    def __init__(self, env_manager, auto_save: bool = True):
        self.env_manager = env_manager
        self.cases: dict[str, Any] = {}
        self.results: dict[str, TestCaseResult] = {}
        self.failed_cases: list[str] = []
        self.passed_cases: list[str] = []
        self.executor = TestExecutor(env_manager)
        self.auto_save = auto_save
        self._storage_file = self._get_storage_path()

        if self.auto_save:
            self._load_cases()

    def _get_storage_path(self) -> Path:
        """获取用例存储路径"""
        if self.env_manager.test_path:
            storage_dir = Path(self.env_manager.test_path) / ".ptest"
        else:
            storage_dir = Path.home() / ".ptest"
        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir / "cases.json"

    def _load_cases(self) -> None:
        """从文件加载用例"""
        if self._storage_file.exists():
            try:
                with open(self._storage_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.cases = data.get("cases", {})
                    self.failed_cases = data.get("failed_cases", [])
                    self.passed_cases = data.get("passed_cases", [])
            except Exception:
                self.cases = {}

    def _save_cases(self) -> None:
        """保存用例到文件"""
        if not self.auto_save:
            return
        try:
            data = {
                "cases": self.cases,
                "failed_cases": self.failed_cases,
                "passed_cases": self.passed_cases,
                "saved_at": datetime.now().isoformat(),
            }
            with open(self._storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.env_manager.logger.warning(f"Failed to save cases: {e}")

    def add_case(self, case_id: str, case_data: dict):
        self.cases[case_id] = {
            "id": case_id,
            "data": case_data,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "status": "pending",
        }
        self._save_cases()
        self.env_manager.logger.info(f"Test case '{case_id}' added")
        return f"✓ Test case '{case_id}' added"

    def remove_case(self, case_id: str):
        if case_id in self.cases:
            del self.cases[case_id]
            if case_id in self.results:
                del self.results[case_id]
            if case_id in self.passed_cases:
                self.passed_cases.remove(case_id)
            if case_id in self.failed_cases:
                self.failed_cases.remove(case_id)
            self._save_cases()
            self.env_manager.logger.info(f"Test case '{case_id}' removed")
            return f"✓ Test case '{case_id}' removed"
        return f"✗ Test case '{case_id}' does not exist"

    def list_cases(self):
        """列出所有测试用例"""
        if not self.cases:
            return "No test cases found"

        result = f"{get_colored_text('Test Cases:', 95)}\n"
        for case_id, case_info in self.cases.items():
            status = case_info["status"].upper()
            color = 92 if status == "PASSED" else 91 if status == "FAILED" else 97
            result += f"{get_colored_text(case_id, 94)} [{get_colored_text(status, color)}] - Created: {case_info['created_at']}\n"
        return result.rstrip()

    def run_case(self, case_id: str) -> TestCaseResult:
        """
        运行指定测试用例
        使用真实的测试执行器执行测试

        Returns:
            TestCaseResult: 结构化的测试结果对象
        """
        if case_id not in self.cases:
            result_obj = TestCaseResult(case_id=case_id)
            result_obj.status = "error"
            result_obj.error_message = f"Test case '{case_id}' does not exist"
            result_obj.end_time = datetime.now()
            return result_obj

        case_data = self.cases[case_id]["data"]
        self.env_manager.logger.info(f"Running test case: {case_id}")

        # 使用测试执行器执行测试
        result_obj = self.executor.execute_case(case_id, case_data)
        self.results[case_id] = result_obj

        # 更新用例状态和结果列表
        self.cases[case_id]["status"] = result_obj.status
        self.cases[case_id]["last_run"] = result_obj.end_time.isoformat()

        # 更新通过/失败列表
        if result_obj.status == "passed":
            if case_id not in self.passed_cases:
                self.passed_cases.append(case_id)
            if case_id in self.failed_cases:
                self.failed_cases.remove(case_id)
            self.env_manager.logger.info(f"Test case '{case_id}' PASSED")
        elif result_obj.status == "failed":
            if case_id not in self.failed_cases:
                self.failed_cases.append(case_id)
            if case_id in self.passed_cases:
                self.passed_cases.remove(case_id)
            self.env_manager.logger.error(
                f"Test case '{case_id}' FAILED: {result_obj.error_message}"
            )
        else:
            if case_id not in self.failed_cases:
                self.failed_cases.append(case_id)
            if case_id in self.passed_cases:
                self.passed_cases.remove(case_id)
            self.env_manager.logger.error(
                f"Test case '{case_id}' ERROR: {result_obj.error_message}"
            )

        self._save_cases()
        return result_obj

    def run_all_cases(self) -> Dict[str, Any]:
        """运行所有测试用例

        Returns:
            Dict[str, Any]: 包含测试结果摘要和详细结果列表
        """
        if not self.cases:
            return {
                "success": False,
                "message": "No test cases to run",
                "total": 0,
                "passed": 0,
                "failed": 0,
                "results": [],
            }

        self.env_manager.logger.info(f"Running all {len(self.cases)} test cases")
        results = []
        passed_count = 0
        failed_count = 0

        for case_id in self.cases:
            result = self.run_case(case_id)
            results.append(result)
            if result.status == "passed":
                passed_count += 1
            else:
                failed_count += 1

        return {
            "success": failed_count == 0,
            "message": f"Completed {len(results)} test cases",
            "total": len(results),
            "passed": passed_count,
            "failed": failed_count,
            "results": results,
        }

    def run_failed_cases(self):
        """运行失败的测试用例"""
        if not self.failed_cases:
            return "No failed test cases to run"

        self.env_manager.logger.info(
            f"Running {len(self.failed_cases)} failed test cases"
        )
        results = []
        for case_id in self.failed_cases:
            results.append(self.run_case(case_id))
        return "\n".join(results)
