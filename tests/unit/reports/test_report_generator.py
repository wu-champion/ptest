"""
报告生成器测试

测试报告生成器的HTML、JSON、Markdown格式生成功能
"""

import unittest
from pathlib import Path
import tempfile
import json
import shutil
from datetime import datetime, timedelta

import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ptest.reports.generator import ReportGenerator
from ptest.cases.result import TestCaseResult


class MockEnvManager:
    """模拟EnvironmentManager用于测试"""

    def __init__(self, temp_dir):
        self.test_path = Path(temp_dir)
        self.config = None
        self.logger = MockLogger()


class MockLogger:
    """模拟Logger用于测试"""

    def info(self, msg):
        pass

    def error(self, msg):
        pass

    def warning(self, msg):
        pass

    def debug(self, msg):
        pass


class MockCaseManager:
    """模拟CaseManager用于测试"""

    def __init__(self, env_manager):
        self.env_manager = env_manager
        self.cases = {}
        self.results = {}
        self.failed_cases = []
        self.passed_cases = []

    def add_case(self, case_id: str, case_data: dict):
        self.cases[case_id] = {
            "id": case_id,
            "data": case_data,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "status": "pending",
        }

    def remove_case(self, case_id: str):
        if case_id in self.cases:
            del self.cases[case_id]
            if case_id in self.results:
                del self.results[case_id]


class TestReportGenerator(unittest.TestCase):
    """报告生成器测试"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.env_manager = MockEnvManager(self.temp_dir)
        self.case_manager = MockCaseManager(self.env_manager)
        self.report_generator = ReportGenerator(self.env_manager, self.case_manager)

        # 添加测试用例
        self.case_manager.add_case("test_001", {"type": "unit"})
        self.case_manager.add_case("test_002", {"type": "integration"})
        self.case_manager.add_case("test_003", {"type": "e2e"})

        # 添加测试结果
        result1 = TestCaseResult("test_001")
        result1.status = "passed"
        result1.duration = 1.5
        result1.error_message = ""
        result1.start_time = datetime.now()
        result1.end_time = datetime.now() + timedelta(seconds=1.5)
        self.case_manager.results["test_001"] = result1

        result2 = TestCaseResult("test_002")
        result2.status = "failed"
        result2.duration = 2.3
        result2.error_message = "Assertion failed"
        result2.start_time = datetime.now()
        result2.end_time = datetime.now() + timedelta(seconds=2.3)
        self.case_manager.results["test_002"] = result2

        result3 = TestCaseResult("test_003")
        result3.status = "passed"
        result3.duration = 0.8
        result3.error_message = ""
        result3.start_time = datetime.now()
        result3.end_time = datetime.now() + timedelta(seconds=0.8)
        self.case_manager.results["test_003"] = result3

        # 标记通过/失败
        self.case_manager.passed_cases.append("test_001")
        self.case_manager.passed_cases.append("test_003")
        self.case_manager.failed_cases.append("test_002")

    def tearDown(self):
        """清理测试环境"""
        if hasattr(self, "temp_dir") and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_html_report(self):
        """测试HTML报告生成"""
        report_path = self.report_generator.generate_report(
            format_type="html", output_path=Path(self.temp_dir) / "test_report.html"
        )

        # 验证报告文件存在
        self.assertTrue(Path(report_path).exists())

        # 验证报告文件内容包含关键元素
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("ptest - Test Report", content)
            self.assertIn("Test Summary", content)
            self.assertIn("Test Results", content)

    def test_generate_json_report(self):
        """测试JSON报告生成"""
        report_path = self.report_generator.generate_report(
            format_type="json", output_path=Path(self.temp_dir) / "test_report.json"
        )

        # 验证报告文件存在
        self.assertTrue(Path(report_path).exists())

        # 验证JSON内容格式正确
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            data = json.loads(content)
            self.assertIn("summary", data)
            self.assertIn("results", data)

    def test_generate_markdown_report(self):
        """测试Markdown报告生成"""
        report_path = self.report_generator.generate_report(
            format_type="markdown", output_path=Path(self.temp_dir) / "test_report.md"
        )

        # 验证报告文件存在
        self.assertTrue(Path(report_path).exists())

        # 验证Markdown内容包含关键元素
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("ptest Test Report", content)
            self.assertIn("Test Summary", content)
            self.assertIn("Test Results", content)

    def test_default_output_path(self):
        """测试默认输出路径"""
        report_path = self.report_generator.generate_report(format_type="html")

        # 验证报告文件存在
        self.assertTrue(Path(report_path).exists())
        self.assertTrue(str(report_path).startswith(str(Path.cwd())))

    def test_unsupported_format(self):
        """测试不支持的格式"""
        with self.assertRaises(ValueError):
            self.report_generator.generate_report(format_type="unsupported")
