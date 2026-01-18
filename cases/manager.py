# ptest/cases/manager.py
from pathlib import Path
import json
from datetime import datetime
import time
import random
from .result import TestCaseResult
from ..utils import get_colored_text

class CaseManager:
    """测试用例管理器"""
    
    def __init__(self, env_manager):
        self.env_manager = env_manager
        self.cases = {}
        self.results = {}
        self.failed_cases = []
        self.passed_cases = []
        
    def add_case(self, case_id: str, case_data: dict):
        """
        添加测试用例
        TODO: 增加添加case后的检查与返回，
        例如检查case_id是否重复等，检查case是否存在cases集合中，
        TODO: 返回改为bool类型
        """
        self.cases[case_id] = {
            'id': case_id,
            'data': case_data,
            'created_at': datetime.now().isoformat(),
            'last_run': None,
            'status': 'pending'
        }
        self.env_manager.logger.info(f"Test case '{case_id}' added")
        return f"✓ Test case '{case_id}' added"
        
    def remove_case(self, case_id: str):
        """
        删除测试用例
        TODO: 增加删除case后的检查与返回，
        检查case是否存在cases集合中，
        TODO: 返回改为bool类型
        """
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
        
        # TODO 将返回内容改为字典或者列表，方便后续处理
        result = f"{get_colored_text('Test Cases:', 95)}\n"
        for case_id, case_info in self.cases.items():
            status = case_info['status'].upper()
            color = 92 if status == "PASSED" else 91 if status == "FAILED" else 97
            result += f"{get_colored_text(case_id, 94)} [{get_colored_text(status, color)}] - Created: {case_info['created_at']}\n"
        return result.rstrip()
        
    def run_case(self, case_id: str):
        """
        运行指定测试用例
        !!! TODO !!!: 目前为模拟实现，后续需根据case_data实际执行测试逻辑
        TODO: 增加运行case后的检查与返回，
        返回为bool对象还是其他内容还有待考虑，
        ? 比如可以将错误信息等也返回，或者将错误信息写入指定日志文件？
        但肯定不能简单的返回字符串
        """
        if case_id not in self.cases:
            return f"✗ Test case '{case_id}' does not exist"
        
        # 创建测试用例结果对象
        result_obj = TestCaseResult(case_id)
        self.results[case_id] = result_obj
        result_obj.start_time = datetime.now()
        
        self.env_manager.logger.info(f"Running test case: {case_id}")
        
        # 模拟测试执行
        time.sleep(0.5)  # 模拟执行时间
        
        # 模拟测试结果
        success = random.choice([True, False])
        
        result_obj.end_time = datetime.now()
        result_obj.duration = (result_obj.end_time - result_obj.start_time).total_seconds().__round__()
        
        if success:
            result_obj.status = 'passed'
            self.cases[case_id]['status'] = 'passed'
            self.passed_cases.append(case_id)
            self.env_manager.logger.info(f"Test case '{case_id}' PASSED")
            result = f"✓ Test case '{case_id}' {get_colored_text('PASSED', 92)} ({result_obj.duration:.2f}s)"
        else:
            result_obj.status = 'failed'
            self.cases[case_id]['status'] = 'failed'
            self.failed_cases.append(case_id)
            result_obj.error_message = "Simulated test failure"
            self.env_manager.logger.error(f"Test case '{case_id}' FAILED: Simulated test failure")
            result = f"✗ Test case '{case_id}' {get_colored_text('FAILED', 91)} ({result_obj.duration:.2f}s): Simulated test failure"
        
        self.cases[case_id]['last_run'] = result_obj.end_time.isoformat()
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
            # TODO: 返回内容改为更结构化的格式，或者直接raise Exception
            return "No failed test cases to run"
        
        self.env_manager.logger.info(f"Running {len(self.failed_cases)} failed test cases")
        results = []
        for case_id in self.failed_cases:
            results.append(self.run_case(case_id))
        return "\n".join(results)


