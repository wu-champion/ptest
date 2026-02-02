# ptest/cases/result.py
from datetime import datetime
from typing import Optional, Dict, Any


class TestCaseResult:
    """测试用例结果类"""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.status = "pending"
        self.start_time = datetime.now()
        self.end_time = datetime.now()
        self.duration: float = 0  # duration in seconds (can be float)
        self.error_message = ""
        self.output = ""
        self.test_type = ""
        self.assertions_passed = 0
        self.assertions_failed = 0

    def is_passed(self) -> bool:
        """是否通过"""
        return self.status == "passed"

    def is_failed(self) -> bool:
        """是否失败"""
        return self.status == "failed"

    def is_error(self) -> bool:
        """是否有错误"""
        return self.status == "error"

    def is_success(self) -> bool:
        """是否成功（通过）"""
        return self.is_passed()

    def get_output(self) -> str:
        """获取输出"""
        return self.output

    def get_error(self) -> str:
        """获取错误信息"""
        return self.error_message

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "case_id": self.case_id,
            "status": self.status,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration": self.duration,
            "error_message": self.error_message,
            "output": self.output,
            "test_type": self.test_type,
            "assertions_passed": self.assertions_passed,
            "assertions_failed": self.assertions_failed,
        }
