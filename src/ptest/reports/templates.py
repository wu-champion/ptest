"""
ptest 报告模板

提供美观、专业的HTML报告模板
"""

TEST_SUMMARY_TEMPLATE = """
<div class="summary-section">
    <h2>📊 Test Summary</h2>
    <div class="summary-grid">
        <div class="summary-card">
            <div class="summary-icon">📋</div>
            <div class="summary-content">
                <div class="summary-label">Total Test Cases</div>
                <div class="summary-value">{total_cases}</div>
            </div>
        </div>
        <div class="summary-card success">
            <div class="summary-icon">✅</div>
            <div class="summary-content">
                <div class="summary-label">Passed</div>
                <div class="summary-value">{passed_count}</div>
                <div class="summary-percentage">{success_rate:.1f}%</div>
            </div>
        </div>
        <div class="summary-card failure">
            <div class="summary-icon">❌</div>
            <div class="summary-content">
                <div class="summary-label">Failed</div>
                <div class="summary-value">{failed_count}</div>
                <div class="summary-percentage">{failure_rate:.1f}%</div>
            </div>
        </div>
        <div class="summary-card">
            <div class="summary-icon">⏱️</div>
            <div class="summary-content">
                <div class="summary-label">Total Duration</div>
                <div class="summary-value">{total_duration:.2f}s</div>
            </div>
        </div>
    </div>
</div>
"""


TEST_RESULTS_TABLE_TEMPLATE = """
<div class="results-section">
    <h2>📋 Test Results</h2>
    <table class="results-table">
        <thead>
            <tr>
                <th class="sortable">Test Case ID</th>
                <th class="sortable">Status</th>
                <th class="sortable">Duration (s)</th>
                <th class="sortable">Error Message</th>
            </tr>
        </thead>
        <tbody>
            {results_rows}
        </tbody>
    </table>
</div>
"""


TEST_RESULT_ROW_TEMPLATE = """
<tr class="result-row {status_class}">
    <td class="result-id">{case_id}</td>
    <td class="result-status">
        <span class="status-badge {status_class}">{status_text}</span>
    </td>
    <td class="result-duration">{duration_text}</td>
    <td class="result-error">{error_msg}</td>
</tr>
"""


ENVIRONMENT_INFO_TEMPLATE = """
<div class="environment-section">
    <h2>🖥️ Test Environment</h2>
    <table class="info-table">
        <tbody>
            <tr>
                <td><strong>Environment Path</strong></td>
                <td>{env_path}</td>
            </tr>
            <tr>
                <td><strong>Isolation Engine</strong></td>
                <td>{isolation_engine}</td>
            </tr>
            <tr>
                <td><strong>Test Date</strong></td>
                <td>{test_date}</td>
            </tr>
            <tr>
                <td><strong>Python Version</strong></td>
                <td>{python_version}</td>
            </tr>
        </tbody>
    </table>
</div>
"""


REPORT_STYLES = """
/* Global Styles */
* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    background: #f5f7fa;
    padding: 20px;
}}

/* Header */
.header {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 20px;
    margin-bottom: 30px;
    border-radius: 10px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
}}

.header h1 {{
    margin: 0;
    font-size: 28px;
    font-weight: 600;
}}

.header-meta {{
    margin-top: 10px;
    font-size: 14px;
    opacity: 0.9;
}}

/* Sections */
section {{
    background: white;
    padding: 30px;
    margin-bottom: 30px;
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
}}

section h2 {{
    margin-top: 0;
    margin-bottom: 20px;
    font-size: 20px;
    font-weight: 600;
    color: #2c3e50;
    display: flex;
    align-items: center;
    gap: 10px;
}}

/* Summary Section */
.summary-section {{
    margin-bottom: 30px;
}}

.summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-top: 20px;
}}

.summary-card {{
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    padding: 25px;
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    box-shadow: 0 4px 15px rgba(240, 84, 53, 0.1);
}}

.summary-card.success {{
    background: linear-gradient(135deg, #4caf50 0%, #45a049 100%);
}}

.summary-card.failure {{
    background: linear-gradient(135deg, #f44336 0%, #da190b 100%);
}}

.summary-icon {{
    font-size: 40px;
    margin-bottom: 10px;
}}

.summary-content {{
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    color: white;
}}

.summary-label {{
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.9;
    margin-bottom: 5px;
}}

.summary-value {{
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 5px;
}}

.summary-percentage {{
    font-size: 14px;
    opacity: 0.9;
}}

/* Tables */
.results-table, .info-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 20px;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}}

.results-table thead, .info-table thead {{
    background: #f8f9fa;
}}

.results-table th, .info-table th {{
    padding: 15px;
    text-align: left;
    font-weight: 600;
    color: #374151;
    border-bottom: 2px solid #e2e8f0;
    cursor: pointer;
    user-select: none;
    transition: background-color 0.2s;
}}

.results-table th:hover {{
    background: #e8eaf6;
}}

.results-table th.sortable:hover {{
    color: #667eea;
}}

.results-table tbody, .info-table tbody {{
    background: white;
}}

.results-table tr, .info-table tr {{
    border-bottom: 1px solid #f1f5f9;
    transition: background-color 0.2s;
}}

.results-table tr:hover, .info-table tr:hover {{
    background: #f8f9fa;
}}

.results-table td, .info-table td {{
    padding: 12px 15px;
    font-size: 14px;
}}

.result-row.passed {{
    border-left: 4px solid #4caf50;
}}

.result-row.failed {{
    border-left: 4px solid #f44336;
}}

.result-row.skipped {{
    border-left: 4px solid #ff9800;
}}

.result-id {{
    font-family: 'Courier New', monospace;
    font-weight: 600;
}}

.result-status {{
    text-align: center;
}}

.status-badge {{
    display: inline-block;
    padding: 6px 12px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

.status-badge.passed {{
    background: #4caf50;
    color: white;
}}

.status-badge.failed {{
    background: #f44336;
    color: white;
}}

.status-badge.skipped {{
    background: #ff9800;
    color: white;
}}

.result-duration {{
    font-family: 'Courier New', monospace;
    text-align: center;
}}

.result-error {{
    color: #f44336;
    font-size: 13px;
    font-family: 'Courier New', monospace;
    word-break: break-word;
    max-width: 400px;
}}

.info-table td {{
    color: #555;
}}

.info-table strong {{
    color: #374151;
}}

/* Responsive */
@media (max-width: 768px) {{
    .summary-grid {{
        grid-template-columns: 1fr;
    }}
    
    body {{
        padding: 10px;
    }}
    
    .results-table, .info-table {{
        font-size: 12px;
    }}
    
    .results-table th, .info-table th,
    .results-table td, .info-table td {{
        padding: 8px 10px;
    }}
}}
"""


FULL_REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ptest - Test Report</title>
    <style>
        {styles}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧪 ptest Test Report</h1>
            <div class="header-meta">
                <div>Generated: {generated_at}</div>
                <div>Test Environment: {test_env}</div>
            </div>
        </div>

        {summary_section}

        {environment_section}

        {results_section}

        <div class="footer">
            <p>Generated by <strong>ptest v{version}</strong></p>
        </div>
    </div>
</body>
</html>
"""


MARKDOWN_REPORT_TEMPLATE = """
# 🧪 ptest Test Report

**Generated:** {generated_at}
**Test Environment:** {test_env}
**Test Duration:** {total_duration:.2f}s

## 📊 Test Summary

| Metric | Value |
|--------|--------|
| **Total Test Cases** | {total_cases} |
| **Passed** | {passed_count} |
| **Failed** | {failed_count} |
| **Success Rate** | {success_rate:.1f}% |
| **Total Duration** | {total_duration:.2f}s |

## 🖥️ Test Environment

| Property | Value |
|----------|--------|
| **Environment Path** | {env_path} |
| **Isolation Engine** | {isolation_engine} |
| **Test Date** | {test_date} |
| **Python Version** | {python_version} |

## 📋 Test Results

| Test Case | Status | Duration | Error |
|-----------|--------|---------|
{results_table}

---
*Generated by ptest v{version}*
"""
