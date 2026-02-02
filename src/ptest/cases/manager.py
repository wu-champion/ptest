# ptest/cases/manager.py
from pathlib import Path
import json
from datetime import datetime
import time
from .result import TestCaseResult
from .executor import TestExecutor

try:
    from ..utils import get_colored_text
except ImportError:
    # 简单的颜色输出函数，当无法导入时使用
    def get_colored_text(text, color_code):
        return text


class CaseManager:
    """测试用例管理器"""

    def __init__(self, env_manager):
        self.env_manager = env_manager
        self.cases = {}
        self.results = {}
        self.failed_cases = []
        self.passed_cases = []
        self.executor = TestExecutor(env_manager)

    def add_case(self, case_id: str, case_data: dict):
        self.cases[case_id] = {
            "id": case_id,
            "data": case_data,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "status": "pending",
        }
        self.env_manager.logger.info(f"Test case '{case_id}' added")
        return f"✓ Test case '{case_id}' added"

    def remove_case(self, case_id: str):
        if case_id in self.cases:
            del self.cases[case_id]
            if case_id in self.results:
                del self.results[case_id]
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

    def run_case(self, case_id: str):
        """
        运行指定测试用例
        使用真实的测试执行器执行测试
        """
        if case_id not in self.cases:
            return f"✗ Test case '{case_id}' does not exist"

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
            result = f"✓ Test case '{case_id}' {get_colored_text('PASSED', 92)} ({result_obj.duration:.2f}s)"
        elif result_obj.status == "failed":
            if case_id not in self.failed_cases:
                self.failed_cases.append(case_id)
            if case_id in self.passed_cases:
                self.passed_cases.remove(case_id)
            self.env_manager.logger.error(
                f"Test case '{case_id}' FAILED: {result_obj.error_message}"
            )
            result = f"✗ Test case '{case_id}' {get_colored_text('FAILED', 91)} ({result_obj.duration:.2f}s): {result_obj.error_message}"
        else:  # error
            if case_id not in self.failed_cases:
                self.failed_cases.append(case_id)
            if case_id in self.passed_cases:
                self.passed_cases.remove(case_id)
            self.env_manager.logger.error(
                f"Test case '{case_id}' ERROR: {result_obj.error_message}"
            )
            result = f"✗ Test case '{case_id}' {get_colored_text('ERROR', 93)} ({result_obj.duration:.2f}s): {result_obj.error_message}"

        return result

    def run_all_cases(self):
        """运行所有测试用例"""
        if not self.cases:
            # TODO: 返回内容改为更结构化的格式，或者直接raise Exception
            return "No test cases to run"

        self.env_manager.logger.info(f"Running all {len(self.cases)} test cases")
        results = []
        for case_id in self.cases:
            results.append(self.run_case(case_id))
        return "\n".join(results)

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
