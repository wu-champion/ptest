# ptest/reports/generator.py
from pathlib import Path
import json
from datetime import datetime
from ..utils import get_colored_text

class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, env_manager, case_manager):
        self.env_manager = env_manager
        self.case_manager = case_manager
        
    def generate_html_report(self):
        """生成HTML报告"""
        total_cases = len(self.case_manager.cases)
        passed_count = len(self.case_manager.passed_cases)
        failed_count = len(self.case_manager.failed_cases)
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ptest - Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .summary-item {{ display: inline-block; margin-right: 20px; padding: 10px; border-radius: 5px; }}
        .passed {{ background-color: #d4edda; color: #155724; }}
        .failed {{ background-color: #f8d7da; color: #721c24; }}
        .results-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        .results-table th, .results-table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        .results-table th {{ background-color: #f2f2f2; }}
        .status-passed {{ color: green; }}
        .status-failed {{ color: red; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>ptest Test Report</h1>
        <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Test Environment: {self.env_manager.test_path}</p>
    </div>
    
    <div class="summary">
        <div class="summary-item passed">Total: {total_cases}</div>
        <div class="summary-item passed">Passed: {passed_count}</div>
        <div class="summary-item failed">Failed: {failed_count}</div>
    </div>
    
    <table class="results-table">
        <thead>
            <tr>
                <th>Test Case ID</th>
                <th>Status</th>
                <th>Duration (s)</th>
                <th>Error Message</th>
            </tr>
        </thead>
        <tbody>
"""
        
        for case_id, result in self.case_manager.results.items():
            status_class = "status-passed" if result.status == "passed" else "status-failed"
            error_msg = result.error_message or ""
            duration = f"{result.duration:.2f}" if result.duration > 0 else "N/A"
            
            html_content += f"""
            <tr>
                <td>{case_id}</td>
                <td class="{status_class}">{result.status.upper()}</td>
                <td>{duration}</td>
                <td>{error_msg}</td>
            </tr>
"""
        
        html_content += """
        </tbody>
    </table>
</body>
</html>
"""
        
        report_file = self.env_manager.report_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(report_file, 'w') as f:
            f.write(html_content)
        
        self.env_manager.logger.info(f"HTML report generated: {report_file}")
        return str(report_file)
    
    def generate_json_report(self):
        """生成JSON报告"""
        report_data = {
            "generated_at": datetime.now().isoformat(),
            "test_environment": str(self.env_manager.test_path),
            "summary": {
                "total_cases": len(self.case_manager.cases),
                "passed": len(self.case_manager.passed_cases),
                "failed": len(self.case_manager.failed_cases)
            },
            "results": {}
        }
        
        for case_id, result in self.case_manager.results.items():
            report_data["results"][case_id] = {
                "status": result.status,
                "duration": result.duration,
                "error_message": result.error_message,
                "start_time": result.start_time.isoformat() if result.start_time else None,
                "end_time": result.end_time.isoformat() if result.end_time else None
            }
        
        report_file = self.env_manager.report_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        self.env_manager.logger.info(f"JSON report generated: {report_file}")
        return str(report_file)
    
    def generate_report(self, format_type: str = "html"):
        """
        生成测试报告
        :param format_type: 报告格式，支持 "html" 和 "json"
        """
        if format_type.lower() == "html":
            return self.generate_html_report()
        elif format_type.lower() == "json":
            return self.generate_json_report()
        else:
            raise ValueError(f"Unsupported report format: {format_type}")