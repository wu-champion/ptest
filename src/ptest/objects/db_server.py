# ptest/objects/db_server.py
"""
数据库服务端组件
"""

from typing import Dict, Any, Tuple, Optional
import subprocess
import time
import os
import signal
from .service_base import ServiceServerComponent


class DatabaseServerComponent(ServiceServerComponent):
    """数据库服务端组件"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.db_type = config.get("db_type", "").lower()
        self.data_dir = config.get("data_dir", "/tmp/test_db_data")
        self.config_file = config.get("config_file", "")
        self.log_file = config.get("log_file", "/tmp/test_db.log")
        self.pid_file = config.get("pid_file", f"/tmp/test_db_{self.db_type}.pid")

        # 数据库特定配置
        self.mysql_config = config.get("mysql_config", {})
        self.postgresql_config = config.get("postgresql_config", {})
        self.mongodb_config = config.get("mongodb_config", {})

    def start(self) -> Tuple[bool, str]:
        """启动数据库服务端"""
        if self.status == "running":
            return True, f"Database server already running on {self.endpoint}"

        try:
            if self.db_type == "mysql":
                return self._start_mysql()
            elif self.db_type in ["postgresql", "postgres"]:
                return self._start_postgresql()
            elif self.db_type == "mongodb":
                return self._start_mongodb()
            elif self.db_type == "sqlite":
                return self._start_sqlite()
            else:
                return False, f"Unsupported database type: {self.db_type}"
        except Exception as e:
            return False, f"Failed to start database server: {str(e)}"

    def stop(self) -> Tuple[bool, str]:
        """停止数据库服务端"""
        if self.status != "running":
            return True, f"Database server not running"

        try:
            # 读取PID文件
            if os.path.exists(self.pid_file):
                with open(self.pid_file, "r") as f:
                    pid = int(f.read().strip())

                # 发送SIGTERM信号
                os.kill(pid, signal.SIGTERM)

                # 等待进程结束
                timeout = 30
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        os.kill(pid, 0)  # 检查进程是否存在
                        time.sleep(1)
                    except OSError:
                        break

                # 删除PID文件
                if os.path.exists(self.pid_file):
                    os.remove(self.pid_file)

            self.status = "stopped"
            return True, f"Database server stopped successfully"

        except Exception as e:
            return False, f"Failed to stop database server: {str(e)}"

    def restart(self) -> Tuple[bool, str]:
        """重启数据库服务端"""
        stop_result = self.stop()
        if not stop_result[0]:
            return stop_result

        time.sleep(2)  # 等待完全停止
        return self.start()

    def get_status(self) -> Dict[str, Any]:
        """获取服务端状态"""
        status_info = {
            "status": self.status,
            "endpoint": self.endpoint,
            "db_type": self.db_type,
            "pid": self._get_pid(),
            "uptime": self._get_uptime(),
            "data_dir": self.data_dir,
            "log_file": self.log_file,
        }

        return status_info

    def health_check(self) -> Tuple[bool, str]:
        """健康检查"""
        if self.status != "running":
            return False, f"Database server not running (status: {self.status})"

        try:
            # 检查进程是否存在
            pid = self._get_pid()
            if pid and self._is_process_running(pid):
                return True, f"Database server healthy (PID: {pid})"
            else:
                self.status = "stopped"
                return False, "Database server process not found"
        except Exception as e:
            return False, f"Health check failed: {str(e)}"

    def _start_mysql(self) -> Tuple[bool, str]:
        """启动MySQL服务端"""
        # 创建数据目录
        os.makedirs(self.data_dir, exist_ok=True)

        # 初始化数据库（如果需要）
        if not os.path.exists(f"{self.data_dir}/mysql"):
            init_cmd = [
                "mysqld",
                "--initialize-insecure",
                f"--datadir={self.data_dir}",
                f"--log-error={self.log_file}",
            ]
            subprocess.run(init_cmd, check=True)

        # 启动MySQL服务
        start_cmd = [
            "mysqld",
            "--daemonize",
            "--pid-file=" + self.pid_file,
            f"--datadir={self.data_dir}",
            f"--port={self.port}",
            f"--bind-address={self.host}",
            f"--log-error={self.log_file}",
        ]

        # 应用MySQL配置
        mysql_config = {
            "max_connections": 100,
            "innodb_buffer_pool_size": "256M",
            **self.mysql_config,
        }

        for key, value in mysql_config.items():
            start_cmd.append(f"--{key}={value}")

        result = subprocess.run(start_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            # 等待服务启动
            time.sleep(3)
            self.status = "running"
            return True, f"MySQL server started on {self.endpoint}"
        else:
            return False, f"MySQL server failed to start: {result.stderr}"

    def _start_postgresql(self) -> Tuple[bool, str]:
        """启动PostgreSQL服务端"""
        # 创建数据目录
        os.makedirs(self.data_dir, exist_ok=True)

        # 初始化数据库集群（如果需要）
        if not os.path.exists(f"{self.data_dir}/PG_VERSION"):
            init_cmd = ["initdb", "-D", self.data_dir, "-U", "postgres"]
            subprocess.run(init_cmd, check=True)

        # 启动PostgreSQL服务
        start_cmd = [
            "pg_ctl",
            "start",
            "-D",
            self.data_dir,
            "-l",
            self.log_file,
            "-o",
            f"-p {self.port} -h {self.host}",
        ]

        result = subprocess.run(start_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            # 等待服务启动
            time.sleep(3)
            self.status = "running"
            return True, f"PostgreSQL server started on {self.endpoint}"
        else:
            return False, f"PostgreSQL server failed to start: {result.stderr}"

    def _start_mongodb(self) -> Tuple[bool, str]:
        """启动MongoDB服务端"""
        # 创建数据目录
        os.makedirs(self.data_dir, exist_ok=True)

        # 启动MongoDB服务
        start_cmd = [
            "mongod",
            "--fork",
            "--logpath",
            self.log_file,
            "--dbpath",
            self.data_dir,
            "--bind_ip",
            self.host,
            "--port",
            str(self.port),
            "--pidfilepath",
            self.pid_file,
        ]

        # 应用MongoDB配置
        mongodb_config = {"journal": "true", "syncdelay": "60", **self.mongodb_config}

        for key, value in mongodb_config.items():
            start_cmd.extend(["--" + key, str(value)])

        result = subprocess.run(start_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            # 等待服务启动
            time.sleep(3)
            self.status = "running"
            return True, f"MongoDB server started on {self.endpoint}"
        else:
            return False, f"MongoDB server failed to start: {result.stderr}"

    def _start_sqlite(self) -> Tuple[bool, str]:
        """启动SQLite服务端（SQLite是文件数据库，不需要服务端）"""
        # SQLite是文件数据库，不需要服务端进程
        # 但我们可以创建一个简单的HTTP API服务来提供SQLite访问
        return self._start_sqlite_api_server()

    def _start_sqlite_api_server(self) -> Tuple[bool, str]:
        """启动SQLite API服务端"""
        # 创建简单的HTTP API服务器
        api_script = f"""
import http.server
import socketserver
import sqlite3
import json
import urllib.parse
from pathlib import Path

class SQLiteAPIHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/'):
            self.handle_api_request()
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        if self.path.startswith('/api/'):
            self.handle_api_request()
        else:
            self.send_error(404, "Not Found")
    
    def handle_api_request(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ''
            
            # 解析请求
            path_parts = self.path.split('/')
            if len(path_parts) >= 3:
                operation = path_parts[2]
                
                # 这里可以添加SQLite操作逻辑
                response_data = {{"message": "SQLite API server running", "operation": operation}}
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
            else:
                self.send_error(400, "Bad Request")
        except Exception as e:
            self.send_error(500, f"Internal Server Error: {{str(e)}}")

# 启动服务器
PORT = {self.port}
Handler = SQLiteAPIHandler
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    with open('{self.pid_file}', 'w') as f:
        f.write(str(os.getpid()))
    httpd.serve_forever()
        """

        # 写入API脚本
        api_script_path = f"/tmp/sqlite_api_server_{self.port}.py"
        with open(api_script_path, "w") as f:
            f.write(api_script)

        # 启动API服务
        start_cmd = ["python3", api_script_path]
        result = subprocess.run(
            start_cmd,
            capture_output=True,
            text=True,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        if result.returncode == 0:
            time.sleep(2)
            self.status = "running"
            return True, f"SQLite API server started on {self.endpoint}"
        else:
            return False, f"SQLite API server failed to start: {result.stderr}"

    def _get_pid(self) -> Optional[int]:
        """获取进程PID"""
        try:
            if os.path.exists(self.pid_file):
                with open(self.pid_file, "r") as f:
                    return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            pass
        return None

    def _is_process_running(self, pid: int) -> bool:
        """检查进程是否运行"""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _get_uptime(self) -> str:
        """获取运行时间"""
        if self.status != "running":
            return "0s"

        try:
            if os.path.exists(self.pid_file):
                stat_time = os.stat(self.pid_file).st_mtime
                uptime_seconds = time.time() - stat_time
                return f"{int(uptime_seconds)}s"
        except Exception:
            pass
        return "unknown"
