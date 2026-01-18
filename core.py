# ptest/core.py
'''
import os
import sys
import json
import argparse
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import time
import threading
from collections import defaultdict

class PTestFramework:
    """ptest框架核心类"""
    
    def __init__(self):
        self.config = {}
        self.test_path = Path.cwd()
        self.log_dir = Path.cwd()
        self.report_dir = Path.cwd()
        self.setup_logging()
        
    def setup_logging(self):
        """设置日志系统"""
        self.logger = logging.getLogger('ptest')
        self.logger.setLevel(logging.DEBUG)
        
        # 清除现有处理器
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # 文件处理器
        if hasattr(self, 'log_dir') and self.log_dir:
            log_file = self.log_dir / f"ptest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def init_environment(self, path: str):
        """初始化测试环境"""
        self.test_path = Path(path).resolve()
        if not self.test_path.exists():
            self.test_path.mkdir(parents=True, exist_ok=True)
            
        # 创建必要的目录结构
        dirs = ['objects', 'tools', 'cases', 'logs', 'reports', 'data', 'scripts']
        for dir_name in dirs:
            (self.test_path / dir_name).mkdir(exist_ok=True)
            
        self.log_dir = self.test_path / 'logs'
        self.report_dir = self.test_path / 'reports'
        
        # 更新日志系统
        self.setup_logging()
        
        # 创建默认配置文件
        config_file = self.test_path / 'ptest_config.json'
        default_config = {}
        if not config_file.exists():
            default_config = {
                "log_level": "INFO",
                "report_format": "html",
                "max_concurrent_tests": 5,
                "timeout_seconds": 300,
                "default_db_user": "root",
                "default_db_password": "",
                "default_db_host": "localhost",
                "default_db_port": 3306
            }
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
                
        self.config = default_config
        self.logger.info(f"Test environment initialized at: {self.test_path}")
        return f"✓ Test environment initialized at: {self.test_path}"
    
    def load_config(self, config_file: str = ''):
        """加载配置文件"""
        if config_file:
            config_path = Path(config_file)
        else:
            if not self.test_path:
                raise Exception("Environment not initialized")
            config_path = self.test_path / 'ptest_config.json'
            
        if config_path.exists():
            with open(config_path, 'r') as f:
                self.config.update(json.load(f))
        self.logger.info(f"Configuration loaded from: {config_path}")
        return f"✓ Configuration loaded from: {config_path}"

class BaseManagedObject:
    """被管理对象基类"""
    
    def __init__(self, name: str, type_name: str, framework: PTestFramework):
        self.name = name
        self.type_name = type_name
        self.status = 'stopped'
        self.installed = False
        self.framework = framework
        self.process = None
        self.pid = None
        
    def execute_command(self, cmd: List[str], timeout: int = 30):
        """执行系统命令"""
        try:
            self.framework.logger.debug(f"Executing command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.framework.test_path
            )
            if result.returncode == 0:
                self.framework.logger.debug(f"Command succeeded: {result.stdout}")
                return True, result.stdout
            else:
                self.framework.logger.error(f"Command failed: {result.stderr}")
                return False, result.stderr
        except subprocess.TimeoutExpired:
            self.framework.logger.error(f"Command timed out after {timeout}s")
            return False, f"Command timed out after {timeout}s"
        except Exception as e:
            self.framework.logger.error(f"Command execution error: {str(e)}")
            return False, str(e)
    
    def install(self, params: Dict[str, Any] = {}):
        """安装对象"""
        self.framework.logger.info(f"Installing {self.type_name} object: {self.name}")
        self.installed = True
        self.status = 'installed'
        return f"✓ {self.type_name} object '{self.name}' installed"
        
    def start(self):
        """启动对象"""
        if not self.installed:
            return f"✗ {self.type_name} object '{self.name}' not installed"
        self.framework.logger.info(f"Starting {self.type_name} object: {self.name}")
        self.status = 'running'
        return f"✓ {self.type_name} object '{self.name}' started"
        
    def stop(self):
        """停止对象"""
        if self.status != 'running':
            return f"✗ {self.type_name} object '{self.name}' not running"
        self.framework.logger.info(f"Stopping {self.type_name} object: {self.name}")
        self.status = 'stopped'
        return f"✓ {self.type_name} object '{self.name}' stopped"
        
    def restart(self):
        """重启对象"""
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result
        
    def uninstall(self):
        """卸载对象"""
        if self.status == 'running':
            self.stop()
        self.framework.logger.info(f"Removing {self.type_name} object: {self.name}")
        self.installed = False
        self.status = 'removed'
        return f"✓ {self.type_name} object '{self.name}' uninstalled"

class MySQLObject(BaseManagedObject):
    """MySQL对象实现"""
    def __init__(self, name: str, framework: PTestFramework):
        super().__init__(name, 'mysql', framework)
        self.version = '9.9.9'  # 版本参数
        self.port = 3306
        self.host = 'localhost'
        self.user = 'root'
        self.password = ''
        
    def install(self, params: Dict[str, Any] = {}):
        """安装MySQL对象"""
        self.framework.logger.info(f"Installing MySQL {self.version} object: {self.name}")
        
        # 模拟安装过程
        install_script = self.framework.test_path / 'scripts' / f'mysql_install_{self.name}.sh'
        install_script.write_text(f"""#!/bin/bash
echo "Installing MySQL {self.version} for {self.name}"
sleep 2
echo "Installation completed"
""")
        
        # 执行安装脚本
        success, output = self.execute_command(['bash', str(install_script)])
        if success:
            self.installed = True
            self.status = 'installed'
            self.framework.logger.info(f"MySQL {self.version} object '{self.name}' installed")
            return f"✓ MySQL {self.version} object '{self.name}' installed"
        else:
            self.framework.logger.error(f"Failed to install MySQL object: {output}")
            return f"✗ Failed to install MySQL object: {output}"
    
    def start(self):
        """启动MySQL对象"""
        if not self.installed:
            return f"✗ MySQL object '{self.name}' not installed"
        
        self.framework.logger.info(f"Starting MySQL {self.version} object: {self.name}")
        
        # 模拟启动过程
        start_script = self.framework.test_path / 'scripts' / f'mysql_start_{self.name}.sh'
        start_script.write_text(f"""#!/bin/bash
echo "Starting MySQL {self.version} server for {self.name}"
sleep 1
echo "MySQL server started on port {self.port}"
""")
        
        success, output = self.execute_command(['bash', str(start_script)])
        if success:
            self.status = 'running'
            self.framework.logger.info(f"MySQL {self.version} object '{self.name}' started")
            return f"✓ MySQL {self.version} object '{self.name}' started"
        else:
            self.framework.logger.error(f"Failed to start MySQL object: {output}")
            return f"✗ Failed to start MySQL object: {output}"
    
    def stop(self):
        """停止MySQL对象"""
        if self.status != 'running':
            return f"✗ MySQL object '{self.name}' not running"
        
        self.framework.logger.info(f"Stopping MySQL {self.version} object: {self.name}")
        
        # 模拟停止过程
        stop_script = self.framework.test_path / 'scripts' / f'mysql_stop_{self.name}.sh'
        stop_script.write_text("""#!/bin/bash
echo "Stopping MySQL server"
sleep 1
echo "MySQL server stopped"
""")
        
        success, output = self.execute_command(['bash', str(stop_script)])
        if success:
            self.status = 'stopped'
            self.framework.logger.info(f"MySQL {self.version} object '{self.name}' stopped")
            return f"✓ MySQL {self.version} object '{self.name}' stopped"
        else:
            self.framework.logger.error(f"Failed to stop MySQL object: {output}")
            return f"✗ Failed to stop MySQL object: {output}"

class WebObject(BaseManagedObject):
    """Web对象实现"""
    def __init__(self, name: str, framework: PTestFramework):
        super().__init__(name, 'web', framework)
        
class ServiceObject(BaseManagedObject):
    """服务对象实现"""
    def __init__(self, name: str, framework: PTestFramework):
        super().__init__(name, 'service', framework)
        
class DBObject(BaseManagedObject):
    """通用数据库对象实现"""
    def __init__(self, name: str, framework: PTestFramework):
        super().__init__(name, 'database', framework)

class ToolObject(BaseManagedObject):
    """工具对象实现"""
    def __init__(self, name: str, framework: PTestFramework):
        super().__init__(name, 'tool', framework)

class ObjectManager:
    """被测对象管理器"""
    
    def __init__(self, framework: PTestFramework):
        self.framework = framework
        self.objects: Dict[str, BaseManagedObject] = {}
        
    def create_object(self, obj_type: str, name: str):
        """创建对象实例"""
        if obj_type.lower() == 'mysql':
            obj = MySQLObject(name, self.framework)
        elif obj_type.lower() == 'web':
            obj = WebObject(name, self.framework)
        elif obj_type.lower() == 'service':
            obj = ServiceObject(name, self.framework)
        elif obj_type.lower() == 'db':
            obj = DBObject(name, self.framework)
        else:
            raise ValueError(f"Unknown object type: {obj_type}")
            
        self.objects[name] = obj
        return obj
        
    def install(self, obj_type: str, name: str, params: Dict[str, Any] = {}):
        """安装被测对象"""
        self.framework.logger.info(f"Installing test object: {name} ({obj_type})")
        obj = self.create_object(obj_type, name)
        result = obj.install(params)
        return result
        
    def start(self, name: str):
        """启动被测对象"""
        self.framework.logger.info(f"Starting test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"
        return self.objects[name].start()
        
    def stop(self, name: str):
        """停止被测对象"""
        self.framework.logger.info(f"Stopping test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"
        return self.objects[name].stop()
        
    def restart(self, name: str):
        """重启被测对象"""
        self.framework.logger.info(f"Restarting test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"
        return self.objects[name].restart()
        
    def uninstall(self, name: str):
        """卸载被测对象"""
        self.framework.logger.info(f"Uninstalling test object: {name}")
        if name not in self.objects:
            return f"✗ Object '{name}' does not exist"
        result = self.objects[name].uninstall()
        del self.objects[name]
        return result
        
    def list_objects(self):
        """列出所有对象"""
        if not self.objects:
            return "No objects found"
        
        result = "Test Objects:\n"
        for name, obj in self.objects.items():
            status = obj.status.upper()
            color = "\033[92m" if status == "RUNNING" else "\033[93m" if status == "STOPPED" else "\033[91m"
            result += f"{color}{obj.type_name}\033[0m - \033[94m{name}\033[0m [{status}]\n"
        return result.strip()

class ToolManager:
    """工具管理器"""
    
    def __init__(self, framework: PTestFramework):
        self.framework = framework
        self.tools: Dict[str, ToolObject] = {}
        
    def install(self, name: str, params: Dict[str, Any] = {}):
        """安装工具"""
        self.framework.logger.info(f"Installing tool: {name}")
        tool = ToolObject(name, self.framework)
        result = tool.install(params)
        self.tools[name] = tool
        return result
        
    def start(self, name: str):
        """启动工具"""
        self.framework.logger.info(f"Starting tool: {name}")
        if name not in self.tools:
            return f"✗ Tool '{name}' does not exist"
        return self.tools[name].start()
        
    def stop(self, name: str):
        """停止工具"""
        self.framework.logger.info(f"Stopping tool: {name}")
        if name not in self.tools:
            return f"✗ Tool '{name}' does not exist"
        return self.tools[name].stop()
        
    def uninstall(self, name: str):
        """卸载工具"""
        self.framework.logger.info(f"Uninstalling tool: {name}")
        if name not in self.tools:
            return f"✗ Tool '{name}' does not exist"
        result = self.tools[name].uninstall()
        del self.tools[name]
        return result
        
    def list_tools(self):
        """列出所有工具"""
        if not self.tools:
            return "No tools found"
        
        result = "Tools:\n"
        for name, tool in self.tools.items():
            status = tool.status.upper()
            color = "\033[92m" if status == "RUNNING" else "\033[93m" if status == "STOPPED" else "\033[91m"
            result += f"{color}{tool.type_name}\033[0m - \033[94m{name}\033[0m [{status}]\n"
        return result.strip()

class TestCaseResult:
    """测试用例结果类"""
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self.status         :str        = 'pending'
        self.start_time     :datetime   = datetime.now()
        self.end_time       :datetime   = datetime.now()
        self.duration       :int        = 0
        self.error_message  :str        = ''
        self.output = None

class CaseManager:
    """测试用例管理器"""
    
    def __init__(self, framework: PTestFramework):
        self.framework = framework
        self.cases: Dict[str, Dict[str, Any]] = {}
        self.results: Dict[str, TestCaseResult] = {}
        self.failed_cases = []
        self.passed_cases = []
        
    def add_case(self, case_id: str, case_data: Dict[str, Any]):
        """添加测试用例"""
        self.cases[case_id] = {
            'id': case_id,
            'data': case_data,
            'created_at': datetime.now().isoformat(),
            'last_run': None,
            'status': 'pending'
        }
        self.framework.logger.info(f"Test case '{case_id}' added")
        return f"✓ Test case '{case_id}' added"
        
    def remove_case(self, case_id: str):
        """删除测试用例"""
        if case_id in self.cases:
            del self.cases[case_id]
            if case_id in self.results:
                del self.results[case_id]
            self.framework.logger.info(f"Test case '{case_id}' removed")
            return f"✓ Test case '{case_id}' removed"
        return f"✗ Test case '{case_id}' does not exist"
        
    def list_cases(self):
        """列出所有测试用例"""
        if not self.cases:
            return "No test cases found"
        
        result = "Test Cases:\n"
        for case_id, case_info in self.cases.items():
            status = case_info['status'].upper()
            color = "\033[92m" if status == "PASSED" else "\033[91m" if status == "FAILED" else "\033[97m"
            result += f"{color}{case_id}\033[0m [{status}] - Created: {case_info['created_at']}\n"
        return result.strip()
        
    def run_case(self, case_id: str):
        """运行指定测试用例"""
        if case_id not in self.cases:
            return f"✗ Test case '{case_id}' does not exist"
        
        # 创建测试用例结果对象
        result_obj = TestCaseResult(case_id)
        self.results[case_id] = result_obj
        result_obj.start_time = datetime.now()
        
        self.framework.logger.info(f"Running test case: {case_id}")
        
        # 模拟测试执行
        time.sleep(0.5)  # 模拟执行时间
        
        # 模拟测试结果
        import random
        success = random.choice([True, False])
        
        result_obj.end_time = datetime.now()
        result_obj.duration = (result_obj.end_time - result_obj.start_time).total_seconds().__round__()
        
        if success:
            result_obj.status = 'passed'
            self.cases[case_id]['status'] = 'passed'
            self.passed_cases.append(case_id)
            self.framework.logger.info(f"Test case '{case_id}' PASSED")
            result = f"✓ Test case '{case_id}' PASSED ({result_obj.duration:.2f}s)"
        else:
            result_obj.status = 'failed'
            self.cases[case_id]['status'] = 'failed'
            self.failed_cases.append(case_id)
            result_obj.error_message = "Simulated test failure"
            self.framework.logger.error(f"Test case '{case_id}' FAILED: Simulated test failure")
            result = f"✗ Test case '{case_id}' FAILED ({result_obj.duration:.2f}s): Simulated test failure"
        
        self.cases[case_id]['last_run'] = result_obj.end_time.isoformat()
        return result
            
    def run_all_cases(self):
        """运行所有测试用例"""
        if not self.cases:
            return "No test cases to run"
        
        self.framework.logger.info(f"Running all {len(self.cases)} test cases")
        results = []
        for case_id in self.cases:
            results.append(self.run_case(case_id))
        return "\n".join(results)
        
    def run_failed_cases(self):
        """运行失败的测试用例"""
        if not self.failed_cases:
            return "No failed test cases to run"
        
        self.framework.logger.info(f"Running {len(self.failed_cases)} failed test cases")
        results = []
        for case_id in self.failed_cases:
            results.append(self.run_case(case_id))
        return "\n".join(results)

class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, framework: PTestFramework, case_manager: CaseManager):
        self.framework = framework
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
        <p>Test Environment: {self.framework.test_path}</p>
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
        
        report_file = self.framework.report_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(report_file, 'w') as f:
            f.write(html_content)
        
        self.framework.logger.info(f"HTML report generated: {report_file}")
        return str(report_file)
    
    def generate_json_report(self):
        """生成JSON报告"""
        report_data = {
            "generated_at": datetime.now().isoformat(),
            "test_environment": str(self.framework.test_path),
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
        
        report_file = self.framework.report_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        self.framework.logger.info(f"JSON report generated: {report_file}")
        return str(report_file)
    
    def generate_report(self, format_type: str = "html"):
        """生成测试报告"""
        if format_type.lower() == "html":
            return self.generate_html_report()
        elif format_type.lower() == "json":
            return self.generate_json_report()
        else:
            raise ValueError(f"Unsupported report format: {format_type}")

def setup_cli():
    """设置命令行界面"""
    parser = argparse.ArgumentParser(
        prog='ptest',
        description='ptest - A comprehensive testing framework',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ptest init --path ./my_test_env
  ptest obj install mysql my_mysql_db --version 9.9.9
  ptest obj start my_mysql_db
  ptest case add my_test_case '{"type": "api", "endpoint": "/api/test"}'
  ptest run all
  ptest obj status
        """
    )
    
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--version', action='version', version='ptest v1.0.0')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # init command
    init_parser = subparsers.add_parser('init', help='Initialize test environment')
    init_parser.add_argument('--path', required=True, help='Path for test environment')
    
    # config command
    config_parser = subparsers.add_parser('config', help='Configuration management')
    config_parser.add_argument('--file', help='Configuration file path')
    
    # obj commands
    obj_parser = subparsers.add_parser('obj', help='Manage test objects')
    obj_subparsers = obj_parser.add_subparsers(dest='obj_action', help='Object actions')
    
    install_obj_parser = obj_subparsers.add_parser('install', help='Install a test object')
    install_obj_parser.add_argument('type', choices=['mysql', 'web', 'service', 'db'], help='Object type')
    install_obj_parser.add_argument('name', help='Object name')
    install_obj_parser.add_argument('--version', help='Version for specific object types like MySQL')
    
    start_obj_parser = obj_subparsers.add_parser('start', help='Start a test object')
    start_obj_parser.add_argument('name', help='Object name')
    
    stop_obj_parser = obj_subparsers.add_parser('stop', help='Stop a test object')
    stop_obj_parser.add_argument('name', help='Object name')
    
    restart_obj_parser = obj_subparsers.add_parser('restart', help='Restart a test object')
    restart_obj_parser.add_argument('name', help='Object name')
    
    uninstall_obj_parser = obj_subparsers.add_parser('uninstall', help='Uninstall a test object')
    uninstall_obj_parser.add_argument('name', help='Object name')
    
    status_obj_parser = obj_subparsers.add_parser('status', help='Show object status')
    list_obj_parser = obj_subparsers.add_parser('list', help='List all objects')
    
    # tool commands
    tool_parser = subparsers.add_parser('tool', help='Manage tools')
    tool_subparsers = tool_parser.add_subparsers(dest='tool_action', help='Tool actions')
    
    install_tool_parser = tool_subparsers.add_parser('install', help='Install a tool')
    install_tool_parser.add_argument('name', help='Tool name')
    
    start_tool_parser = tool_subparsers.add_parser('start', help='Start a tool')
    start_tool_parser.add_argument('name', help='Tool name')
    
    stop_tool_parser = tool_subparsers.add_parser('stop', help='Stop a tool')
    stop_tool_parser.add_argument('name', help='Tool name')
    
    uninstall_tool_parser = tool_subparsers.add_parser('uninstall', help='Uninstall a tool')
    uninstall_tool_parser.add_argument('name', help='Tool name')
    
    status_tool_parser = tool_subparsers.add_parser('status', help='Show tool status')
    list_tool_parser = tool_subparsers.add_parser('list', help='List all tools')
    
    # case commands
    case_parser = subparsers.add_parser('case', help='Manage test cases')
    case_subparsers = case_parser.add_subparsers(dest='case_action', help='Case actions')
    
    add_case_parser = case_subparsers.add_parser('add', help='Add a test case')
    add_case_parser.add_argument('id', help='Test case ID')
    add_case_parser.add_argument('data', help='Test case data (JSON string)')
    
    remove_case_parser = case_subparsers.add_parser('remove', help='Remove a test case')
    remove_case_parser.add_argument('id', help='Test case ID')
    
    list_cases_parser = case_subparsers.add_parser('list', help='List all test cases')
    
    run_case_parser = case_subparsers.add_parser('run', help='Run test cases')
    run_case_parser.add_argument('id', nargs='?', default='all', help='Test case ID or "all"')
    
    # run command
    run_parser = subparsers.add_parser('run', help='Run tests')
    run_parser.add_argument('type', choices=['all', 'failed'], default='all', nargs='?', 
                           help='Type of tests to run')
    
    # report command
    report_parser = subparsers.add_parser('report', help='Generate test reports')
    report_parser.add_argument('--format', choices=['html', 'json'], default='html', 
                              help='Report format')
    
    # status command
    subparsers.add_parser('status', help='Show overall status')
    
    return parser

def main():
    """主入口函数"""
    parser = setup_cli()
    args = parser.parse_args()
    
    framework = PTestFramework()
    obj_manager = ObjectManager(framework)
    tool_manager = ToolManager(framework)
    case_manager = CaseManager(framework)
    
    result = ""
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'init':
            result = framework.init_environment(args.path)
            print(result)
            
        elif args.command == 'config':
            result = framework.load_config(args.file)
            print(result)
            
        elif args.command == 'obj':
            if args.obj_action == 'install':
                params = {'version': args.version} if hasattr(args, 'version') and args.version else {}
                result = obj_manager.install(args.type, args.name, params)
                print(result)
            elif args.obj_action == 'start':
                result = obj_manager.start(args.name)
                print(result)
            elif args.obj_action == 'stop':
                result = obj_manager.stop(args.name)
                print(result)
            elif args.obj_action == 'restart':
                result = obj_manager.restart(args.name)
                print(result)
            elif args.obj_action == 'uninstall':
                result = obj_manager.uninstall(args.name)
                print(result)
            elif args.obj_action == 'list':
                result = obj_manager.list_objects()
                print(result)
            elif args.obj_action == 'status':
                result = obj_manager.list_objects()
                print(result)
                
        elif args.command == 'tool':
            if args.tool_action == 'install':
                result = tool_manager.install(args.name)
                print(result)
            elif args.tool_action == 'start':
                result = tool_manager.start(args.name)
                print(result)
            elif args.tool_action == 'stop':
                result = tool_manager.stop(args.name)
                print(result)
            elif args.tool_action == 'uninstall':
                result = tool_manager.uninstall(args.name)
                print(result)
            elif args.tool_action == 'list':
                result = tool_manager.list_tools()
                print(result)
            elif args.tool_action == 'status':
                result = tool_manager.list_tools()
                print(result)
                
        elif args.command == 'case':
            if args.case_action == 'add':
                try:
                    data = json.loads(args.data)
                except json.JSONDecodeError:
                    print("✗ Invalid JSON format for test case data")
                    return
                result = case_manager.add_case(args.id, data)
                print(result)
            elif args.case_action == 'remove':
                result = case_manager.remove_case(args.id)
                print(result)
            elif args.case_action == 'list':
                result = case_manager.list_cases()
                print(result)
            elif args.case_action == 'run':
                if args.id == 'all':
                    result = case_manager.run_all_cases()
                else:
                    result = case_manager.run_case(args.id)
                print(result)
                
        elif args.command == 'run':
            if args.type == 'all':
                result = case_manager.run_all_cases()
            elif args.type == 'failed':
                result = case_manager.run_failed_cases()
            print(result)
            
        elif args.command == 'report':
            report_gen = ReportGenerator(framework, case_manager)
            report_path = report_gen.generate_report(args.format)
            print(f"✓ Report generated: {report_path}")
            
        elif args.command == 'status':
            print("=== ptest Framework Status ===")
            print(f"Test Environment: {framework.test_path or 'Not initialized'}")
            print(f"Objects: {len(obj_manager.objects)} managed")
            print(f"Tools: {len(tool_manager.tools)} managed")
            print(f"Test Cases: {len(case_manager.cases)} registered")
            print(f"Passed Cases: {len(case_manager.passed_cases)}")
            print(f"Failed Cases: {len(case_manager.failed_cases)}")
            
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        if args.debug:
            import traceback
            traceback.print_exc()
'''