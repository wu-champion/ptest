# ptest/reports/generator.py
from pathlib import Path
import json
from datetime import datetime
from typing import Optional
from .templates import (
    TEST_SUMMARY_TEMPLATE,
    TEST_RESULTS_TABLE_TEMPLATE,
    TEST_RESULT_ROW_TEMPLATE,
    ENVIRONMENT_INFO_TEMPLATE,
    REPORT_STYLES,
    FULL_REPORT_TEMPLATE,
    MARKDOWN_REPORT_TEMPLATE,
)


class ReportGenerator:
    """报告生成器 - 支持HTML、JSON、Markdown格式"""

    def __init__(self, env_manager, case_manager, version: str = "1.0.1"):
        self.env_manager = env_manager
        self.case_manager = case_manager
        self.version = version

    def generate_report(
        self, format_type: str = "html", output_path: Optional[Path] = None
    ) -> str:
        """生成测试报告（支持HTML、JSON、Markdown格式）"""

        format_lower = format_type.lower()

        if format_lower == "html":
            return self._generate_html_report(output_path)
        elif format_lower == "json":
            return self._generate_json_report(output_path)
        elif format_lower == "markdown" or format_lower == "md":
            return self._generate_markdown_report(output_path)
        else:
            raise ValueError(f"Unsupported report format: {format_type}")

    def _generate_html_report(self, output_path: Optional[Path] = None) -> str:
        """生成HTML格式报告"""

        # 收集测试数据
        test_data = self._collect_test_data()

        # 生成摘要部分
        summary_html = TEST_SUMMARY_TEMPLATE.format(
            total_cases=test_data["total_cases"],
            passed_count=test_data["passed_count"],
            failed_count=test_data["failed_count"],
            success_rate=test_data["success_rate"],
            failure_rate=test_data["failure_rate"],
            total_duration=test_data["total_duration"],
        )

        # 生成结果表格
        results_rows = ""
        for case_id, result in self.case_manager.results.items():
            status_class = "passed" if result.status == "passed" else "failed"
            status_text = "PASSED" if result.status == "passed" else "FAILED"
            error_msg = result.error_message or ""
            duration = f"{result.duration:.2f}" if result.duration > 0 else "N/A"

            results_rows += TEST_RESULT_ROW_TEMPLATE.format(
                case_id=case_id,
                status_class=status_class,
                status_text=status_text,
                duration_text=duration,
                error_msg=error_msg,
            )

        results_html = TEST_RESULTS_TABLE_TEMPLATE.format(results_rows=results_rows)

        # 生成环境信息
        env_html = ENVIRONMENT_INFO_TEMPLATE.format(
            env_path=str(self.env_manager.test_path),
            isolation_engine=test_data["isolation_engine"],
            test_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            python_version=test_data["python_version"],
        )

        # 组合完整报告
        full_html = FULL_REPORT_TEMPLATE.format(
            styles=REPORT_STYLES,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            test_env=test_data["test_environment"],
            version=self.version,
            summary_section=summary_html,
            environment_section=env_html,
            results_section=results_html,
        )

        # 保存报告
        if not output_path:
            output_path = (
                Path.cwd()
                / f"ptest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(full_html)

        self.env_manager.logger.info(f"HTML report generated: {output_path}")
        return str(output_path)

    def _generate_json_report(self, output_path: Optional[Path] = None) -> str:
        """生成JSON格式报告"""

        report_data = {
            "generated_at": datetime.now().isoformat(),
            "ptest_version": self.version,
            "test_environment": str(self.env_manager.test_path),
            "summary": self._collect_summary_data(),
            "results": self._collect_results_data(),
        }

        if not output_path:
            output_path = (
                Path.cwd()
                / f"ptest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        self.env_manager.logger.info(f"JSON report generated: {output_path}")
        return str(output_path)

    def _generate_markdown_report(self, output_path: Optional[Path] = None) -> str:
        """生成Markdown格式报告"""

        test_data = self._collect_test_data()

        # 生成结果表格
        results_table = ""
        for case_id, result in self.case_manager.results.items():
            status_icon = "[PASS]" if result.status == "passed" else "[FAIL]"
            duration = f"{result.duration:.2f}s" if result.duration > 0 else "N/A"
            error_msg = result.error_message or ""
            results_table += f"| {case_id} | {status_icon} {result.status.upper()} | {duration} | {error_msg} |\n"

        markdown_content = MARKDOWN_REPORT_TEMPLATE.format(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            test_env=str(self.env_manager.test_path),
            total_duration=test_data["total_duration"],
            total_cases=test_data["total_cases"],
            passed_count=test_data["passed_count"],
            failed_count=test_data["failed_count"],
            success_rate=test_data["success_rate"],
            env_path=str(self.env_manager.test_path),
            isolation_engine=test_data["isolation_engine"],
            test_date=datetime.now().strftime("%Y-%m-%d"),
            python_version=test_data["python_version"],
            results_table=results_table,
            version=self.version,
        )

        if not output_path:
            output_path = (
                Path.cwd()
                / f"ptest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(markdown_content)

        self.env_manager.logger.info(f"Markdown report generated: {output_path}")
        return str(output_path)

    def _collect_test_data(self) -> dict:
        """收集测试数据"""
        isolation_engine = "basic"
        if hasattr(self.env_manager, "config") and self.env_manager.config:
            config_isolation = getattr(
                self.env_manager.config, "isolation_level", "basic"
            )
            isolation_engine = str(config_isolation)

        return {
            "total_cases": len(self.case_manager.cases),
            "passed_count": len(self.case_manager.passed_cases),
            "failed_count": len(self.case_manager.failed_cases),
            "success_rate": 0,
            "failure_rate": 0,
            "total_duration": 0,
            "test_environment": str(self.env_manager.test_path),
            "isolation_engine": isolation_engine,
            "python_version": "3.12",
        }

    def _collect_summary_data(self) -> dict:
        """收集摘要数据"""
        return {
            "total_cases": len(self.case_manager.cases),
            "passed": len(self.case_manager.passed_cases),
            "failed": len(self.case_manager.failed_cases),
            "success_rate": 0,
            "total_duration": 0,
        }

    def _collect_results_data(self) -> dict:
        """收集结果数据"""
        results = {}
        for case_id, result in self.case_manager.results.items():
            results[case_id] = {
                "status": result.status,
                "duration": result.duration,
                "error_message": result.error_message,
                "start_time": result.start_time.isoformat()
                if result.start_time
                else None,
                "end_time": result.end_time.isoformat() if result.end_time else None,
            }
        return results

    def generate_json_report(self):
        """生成JSON报告"""
        report_data = {
            "generated_at": datetime.now().isoformat(),
            "test_environment": str(self.env_manager.test_path),
            "summary": {
                "total_cases": len(self.case_manager.cases),
                "passed": len(self.case_manager.passed_cases),
                "failed": len(self.case_manager.failed_cases),
            },
            "results": {},
        }

        for case_id, result in self.case_manager.results.items():
            report_data["results"][case_id] = {
                "status": result.status,
                "duration": result.duration,
                "error_message": result.error_message,
                "start_time": result.start_time.isoformat()
                if result.start_time
                else None,
                "end_time": result.end_time.isoformat() if result.end_time else None,
            }

        report_file = (
            self.env_manager.report_dir
            / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w") as f:
            json.dump(report_data, f, indent=2)

        self.env_manager.logger.info(f"JSON report generated: {report_file}")
        return str(report_file)
