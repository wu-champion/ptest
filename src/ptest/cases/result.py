# ptest/cases/result.py
from datetime import datetime
from typing import Optional


class TestCaseResult:
    """测试用例结果类"""

    def __init__(self, case_id: str):
        self.case_id                    = case_id
        self.status                     = "pending"
        self.start_time                 = datetime.now()
        self.end_time                   = datetime.now()
        self.duration       :float      = 0  # duration in seconds (can be float)
        self.error_message              = ""
        self.output                     = ""
