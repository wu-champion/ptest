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
from ptest.cases.manager import CaseManager
from ptest.cases.result import TestCaseResult
from ptest.environment import EnvironmentManager


class MockCaseManager:
    """模拟CaseManager用于测试"""

    def __init__(self):
        self.cases = []
        self.passed_cases = []
        self.failed_cases = []
        self.results = {}

    def add_case(self, case_id: str, data: dict):
        self.cases.append(case_id)

    def add_passed(self, case_id: str):
        self.passed_cases.append(case_id)

    def add_failed(self, case_id: str):
        self.failed_cases.append(case_id)

    def add_result(self, case_id: str, result: TestCaseResult):
        self.results[case_id] = result


class MockEnvManager:
    """模拟EnvironmentManager用于测试"""

    def __init__(self):
        self.test_path = Path("/tmp/test_env")
        self.logger = None


class TestReportGenerator(unittest.TestCase):
    """报告生成器测试"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.case_manager = MockCaseManager()
        self.env_manager = MockEnvManager()
        self.report_generator = ReportGenerator(self.env_manager, self.case_manager)

        # 添加一些测试用例
        self.case_manager.add_case("test_001", {"type": "unit"})
        self.case_manager.add_case("test_002", {"type": "integration"})
        self.case_manager.add_case("test_003", {"type": "e2e"})

        # 添加测试结果
        self.case_manager.add_result(
            "test_001",
            TestCaseResult(
                status="passed",
                duration=1.5,
                error_message="",
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(seconds=1.5),
            ),
        )
        self.case_manager.add_result(
            "test_002",
            TestCaseResult(
                status="failed",
                duration=2.3,
                error_message="Assertion failed",
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(seconds=2.3),
            ),
        )
        self.case_manager.add_result(
            "test_003",
            TestCaseResult(
                status="passed",
                duration=0.8,
                error_message="",
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(seconds=0.8),
            ),
        )

        # 标记通过/失败
        self.case_manager.add_passed("test_001")
        self.case_manager.add_passed("test_003")
        self.case_manager.add_failed("test_002")

    def tearDown(self):
        """清理测试环境"""
        if hasattr(self, "temp_dir"):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_html_report(self):
        """测试HTML报告生成"""
        report_path = self.report_generator.generate_report(
            format_type="html", output_path=Path(self.temp_dir) / "test_report.html"
        )

        # 验证报告文件存在
        self.assertTrue(Path(report_path).exists())

        # 验证报告文件内容包含关键元素
        with open(report_path, "r") as f:
            content = f.read()

        self.assertIn("ptest - Test Report", content)
        self.assertIn("Test Summary", content)
        self.assertIn("Total Test Cases", content)
        self.assertIn("Total: 3", content)
        self.assertIn("Passed: 2", content)
        self.assertIn("Failed: 1", content)

    def test_generate_json_report(self):
        """测试JSON报告生成"""
        report_path = self.report_generator.generate_report(
            format_type="json", output_path=Path(self.temp_dir) / "test_report.json"
        )

        # 验证报告文件存在
        self.assertTrue(Path(report_path).exists())

        # 验证JSON格式
        with open(report_path, "r") as f:
            data = json.load(f)

        self.assertIsInstance(data, dict)
        self.assertIn("generated_at", data)
        self.assertIn("test_environment", data)
        self.assertIn("summary", data)
        self.assertIn("results", data)

        # 验证摘要数据
        summary = data["summary"]
        self.assertEqual(summary["total_cases"], 3)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["failed"], 1)

        # 验证结果数据
        results = data["results"]
        self.assertEqual(len(results), 3)
        self.assertIn("test_001", results)
        self.assertIn("test_002", results)
        self.assertIn("test_003", results)

    def test_generate_markdown_report(self):
        """测试Markdown报告生成"""
        report_path = self.report_generator.generate_report(
            format_type="markdown", output_path=Path(self.temp_dir) / "test_report.md"
        )

        # 验证报告文件存在
        self.assertTrue(Path(report_path).exists())

        # 验证Markdown格式
        with open(report_path, "r") as f:
            content = f.read()

        self.assertIn("ptest Test Report", content)
        self.assertIn("## 📊 Test Summary", content)
        self.assertIn("| **Total Test Cases** | 3 |", content)
        self.assertIn("| **Passed** | 2 |", content)
        self.assertIn("| **Failed** | 1 |", content)

    def test_unsupported_format(self):
        """测试不支持的格式"""
        with self.assertRaises(ValueError) as context:
            self.report_generator.generate_report(format_type="xml")

        self.assertIn("Unsupported report format", str(context.exception))

    def test_default_output_path(self):
        """测试默认输出路径"""
        report_path = self.report_generator.generate_report(format_type="html")

        # 验证报告在当前工作目录
        self.assertTrue(Path(report_path).exists())
        self.assertTrue(Path(report_path).parent == Path.cwd())


if __name__ == "__main__":
    unittest.main()
