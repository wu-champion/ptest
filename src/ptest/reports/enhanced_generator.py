# -*- coding: utf-8 -*-
"""ptest 增强版报告生成器

提供美观的HTML报告，包含趋势图表和统计分析。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ptest.core import get_logger

logger = get_logger("reports")


@dataclass
class TestResult:
    """测试结果数据类"""

    case_id: str
    status: str  # passed, failed, skipped
    duration: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    error_message: str = ""
    screenshot: str = ""
    log_file: str = ""


@dataclass
class ReportData:
    """报告数据"""

    title: str = "Test Report"
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration: float = 0.0
    results: list[TestResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class EnhancedReportGenerator:
    """增强版报告生成器"""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def generate(self, data: ReportData) -> Path:
        """生成HTML报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.output_dir / f"ptest_report_{timestamp}.html"

        html_content = self._generate_html(data)
        report_path.write_text(html_content, encoding="utf-8")

        logger.info(f"Report generated: {report_path}")
        return report_path

    def _generate_html(self, data: ReportData) -> str:
        """生成HTML内容"""
        pass_rate = (data.passed / data.total * 100) if data.total > 0 else 0

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{data.title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            margin-bottom: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #333;
            margin-bottom: 20px;
            font-size: 2.5em;
        }}
        
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-value {{
            font-size: 3em;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 1.1em;
        }}
        
        .passed {{ color: #10b981; }}
        .failed {{ color: #ef4444; }}
        .skipped {{ color: #f59e0b; }}
        .total {{ color: #3b82f6; }}
        
        .charts {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }}
        
        .chart-container {{
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }}
        
        .results-table {{
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            overflow-x: auto;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        
        th {{
            background: #f8f9fa;
            font-weight: 600;
            color: #333;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .status-badge {{
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        
        .status-passed {{
            background: #d1fae5;
            color: #065f46;
        }}
        
        .status-failed {{
            background: #fee2e2;
            color: #991b1b;
        }}
        
        .status-skipped {{
            background: #fef3c7;
            color: #92400e;
        }}
        
        .attachment-link {{
            color: #3b82f6;
            text-decoration: none;
            margin-right: 10px;
        }}
        
        .attachment-link:hover {{
            text-decoration: underline;
        }}
        
        @media (max-width: 768px) {{
            .charts {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 {data.title}</h1>
            <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>Duration: {data.duration:.2f}s | Pass Rate: {pass_rate:.1f}%</p>
        </div>
        
        <div class="summary">
            <div class="stat-card">
                <div class="stat-value total">{data.total}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-value passed">{data.passed}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value failed">{data.failed}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value skipped">{data.skipped}</div>
                <div class="stat-label">Skipped</div>
            </div>
        </div>
        
        <div class="charts">
            <div class="chart-container">
                <h3>Test Results Distribution</h3>
                <canvas id="resultChart"></canvas>
            </div>
            <div class="chart-container">
                <h3>Test Duration Trend</h3>
                <canvas id="durationChart"></canvas>
            </div>
        </div>
        
        <div class="results-table">
            <h3>Detailed Results</h3>
            <table>
                <thead>
                    <tr>
                        <th>Test Case</th>
                        <th>Status</th>
                        <th>Duration</th>
                        <th>Attachments</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_table_rows(data.results)}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        // Results distribution chart
        const resultCtx = document.getElementById('resultChart').getContext('2d');
        new Chart(resultCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['Passed', 'Failed', 'Skipped'],
                datasets: [{{
                    data: [{data.passed}, {data.failed}, {data.skipped}],
                    backgroundColor: ['#10b981', '#ef4444', '#f59e0b'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'bottom'
                    }}
                }}
            }}
        }});
        
        // Duration trend chart
        const durationData = {json.dumps([r.duration for r in data.results[:20]])};
        const durationLabels = {json.dumps([f"Test {i + 1}" for i in range(min(20, len(data.results)))])};
        
        const durationCtx = document.getElementById('durationChart').getContext('2d');
        new Chart(durationCtx, {{
            type: 'line',
            data: {{
                labels: durationLabels,
                datasets: [{{
                    label: 'Duration (s)',
                    data: durationData,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4,
                    fill: true
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""

        return html

    def _generate_table_rows(self, results: list[TestResult]) -> str:
        """生成表格行"""
        rows = []
        for result in results:
            attachments = []
            if result.screenshot:
                attachments.append(
                    f'<a href="{result.screenshot}" class="attachment-link">📷 Screenshot</a>'
                )
            if result.log_file:
                attachments.append(
                    f'<a href="{result.log_file}" class="attachment-link">📄 Log</a>'
                )

            rows.append(f"""
                <tr>
                    <td>{result.case_id}</td>
                    <td><span class="status-badge status-{result.status}">{result.status.upper()}</span></td>
                    <td>{result.duration:.3f}s</td>
                    <td>{"".join(attachments)}</td>
                </tr>
            """)

        return "\n".join(rows)

    def save_history(self, data: ReportData) -> None:
        """保存测试历史"""
        history_file = self.output_dir / "history.json"

        history = []
        if history_file.exists():
            history = json.loads(history_file.read_text())

        history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "total": data.total,
                "passed": data.passed,
                "failed": data.failed,
                "duration": data.duration,
            }
        )

        # 只保留最近50条记录
        history = history[-50:]
        history_file.write_text(json.dumps(history, indent=2))

    def compare_with_previous(self, current: ReportData) -> dict[str, Any]:
        """与上一次测试对比"""
        history_file = self.output_dir / "history.json"

        if not history_file.exists():
            return {"has_previous": False}

        history = json.loads(history_file.read_text())
        if len(history) < 2:
            return {"has_previous": False}

        previous = history[-2]

        return {
            "has_previous": True,
            "total_diff": current.total - previous["total"],
            "passed_diff": current.passed - previous["passed"],
            "failed_diff": current.failed - previous["failed"],
            "duration_diff": current.duration - previous["duration"],
        }


def generate_sample_report():
    """生成示例报告"""
    generator = EnhancedReportGenerator()

    # 创建示例数据
    results = [
        TestResult(f"test_{i:03d}", "passed" if i % 3 != 0 else "failed", 0.5 + i * 0.1)
        for i in range(20)
    ]

    data = ReportData(
        title="Sample Test Report",
        total=len(results),
        passed=sum(1 for r in results if r.status == "passed"),
        failed=sum(1 for r in results if r.status == "failed"),
        duration=sum(r.duration for r in results),
        results=results,
    )

    # 保存历史
    generator.save_history(data)

    # 生成报告
    report_path = generator.generate(data)
    print(f"Report generated: {report_path}")

    # 对比
    comparison = generator.compare_with_previous(data)
    if comparison["has_previous"]:
        print(f"Compared with previous: {comparison}")


if __name__ == "__main__":
    generate_sample_report()
