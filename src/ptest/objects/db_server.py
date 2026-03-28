# ptest/objects/db_server.py
"""
数据库服务端组件
"""

import re
from typing import Dict, Any, Tuple, Optional
import importlib.util
import socket
import subprocess
import time
import os
import signal
from pathlib import Path
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
        self.socket_file = config.get("socket_file", "")
        self.database_name = config.get("database_name", "")
        self.install_root = config.get("install_root", "")
        self.mysql_binary = config.get("mysql_binary", "")
        self.runtime_backend = str(config.get("runtime_backend", "host"))
        runtime_library_paths = config.get("runtime_library_paths", [])
        self.runtime_library_paths = (
            [str(item) for item in runtime_library_paths]
            if isinstance(runtime_library_paths, list)
            else []
        )

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
            return True, "Database server not running"

        try:
            pid = self._get_pid()
            if pid is not None:
                os.kill(pid, signal.SIGTERM)

                timeout = 30
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self._is_process_running(pid):
                        break
                    time.sleep(1)

                if self._is_process_running(pid):
                    return False, f"Database server process {pid} did not exit in time"
            elif self._is_port_open(self.host, self.port):
                return (
                    False,
                    "Database server pid file is missing while port remains reachable",
                )

            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)

            port_timeout = 10
            port_start = time.time()
            while time.time() - port_start < port_timeout:
                if not self._is_port_open(self.host, self.port):
                    break
                time.sleep(0.5)

            if self._is_port_open(self.host, self.port):
                return (
                    False,
                    f"Database server port {self.port} is still reachable after stop",
                )

            self.status = "stopped"
            return True, "Database server stopped successfully"

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
            "config_file": self.config_file,
            "log_file": self.log_file,
            "socket_file": self.socket_file,
            "install_root": self.config.get("install_root", ""),
            "managed_instance": self.config.get("managed_instance", {}),
            "staged_package_path": self.config.get("staged_package_path", ""),
            "mysql_binary": self.mysql_binary,
            "runtime_backend": self.runtime_backend,
            "runtime_library_paths": self.runtime_library_paths,
        }

        return status_info

    def health_check(self) -> Tuple[bool, str]:
        """健康检查"""
        if self.status != "running":
            return False, f"Database server not running (status: {self.status})"

        try:
            # 检查进程是否存在
            pid = self._get_pid()
            if not (pid and self._is_process_running(pid)):
                self.status = "stopped"
                return False, "Database server process not found"
            if self.db_type == "mysql":
                return self._mysql_health_check(pid)
            return True, f"Database server healthy (PID: {pid})"
        except Exception as e:
            return False, f"Health check failed: {str(e)}"

    def _start_mysql(self) -> Tuple[bool, str]:
        """启动MySQL服务端"""
        runtime_supported, runtime_message = self._check_runtime_backend_capabilities()
        if not runtime_supported:
            return False, runtime_message

        mysql_binary = self._resolve_mysql_binary()
        if not mysql_binary.exists():
            return False, f"MySQL binary not found: {mysql_binary}"
        process_env = self._build_mysql_process_env()
        missing_dependencies = self._check_binary_dependencies(
            mysql_binary, process_env
        )
        if missing_dependencies:
            missing_text = ", ".join(sorted(missing_dependencies))
            return (
                False,
                f"MySQL binary is missing required shared libraries: {missing_text}",
            )

        # 创建数据目录
        os.makedirs(self.data_dir, exist_ok=True)

        # 初始化数据库（如果需要）
        if not os.path.exists(f"{self.data_dir}/mysql"):
            init_cmd = [str(mysql_binary)]
            if self.config_file:
                init_cmd.append(f"--defaults-file={self.config_file}")
            init_cmd.extend(
                [
                    "--initialize-insecure",
                    f"--datadir={self.data_dir}",
                    f"--log-error={self.log_file}",
                ]
            )
            subprocess.run(init_cmd, check=True, env=process_env)

        # 启动MySQL服务
        start_cmd = [str(mysql_binary)]
        if self.config_file:
            start_cmd.append(f"--defaults-file={self.config_file}")
        start_cmd.extend(
            [
                "--daemonize",
                "--pid-file=" + self.pid_file,
                f"--datadir={self.data_dir}",
                f"--port={self.port}",
                f"--bind-address={self.host}",
                f"--log-error={self.log_file}",
            ]
        )
        # 应用MySQL配置
        mysql_config = {
            "max_connections": 100,
            "innodb_buffer_pool_size": "256M",
            **self.mysql_config,
        }
        mysql_runtime_options = self._filter_mysql_server_options(mysql_config)

        for key, value in mysql_runtime_options.items():
            start_cmd.append(f"--{key}={value}")

        result = subprocess.run(
            start_cmd,
            capture_output=True,
            text=True,
            env=process_env,
        )

        if result.returncode == 0:
            # 等待服务启动
            time.sleep(3)
            self.status = "running"
            healthy, message = self.health_check()
            if healthy:
                database_ready, database_message = self._ensure_mysql_database()
                if not database_ready:
                    self.status = "error"
                    return False, database_message
                return True, f"MySQL server started on {self.endpoint}"
            self.status = "error"
            return False, f"MySQL server started but health check failed: {message}"
        else:
            return False, f"MySQL server failed to start: {result.stderr}"

    def _check_runtime_backend_capabilities(self) -> Tuple[bool, str]:
        if self.runtime_backend != "host":
            return (
                False,
                "MySQL managed instance currently supports only the 'host' runtime "
                f"backend, got '{self.runtime_backend}'",
            )
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind((self.host, self.port))
        except PermissionError as exc:
            return (
                False,
                "Current runtime backend does not permit binding "
                f"{self.host}:{self.port}: {exc}",
            )
        except OSError as exc:
            return (
                False,
                "Current runtime backend cannot prepare a managed MySQL service on "
                f"{self.host}:{self.port}: {exc}",
            )
        return True, "host runtime backend preflight passed"

    def _resolve_mysql_binary(self) -> Path:
        if self.mysql_binary:
            configured = Path(self.mysql_binary).expanduser().resolve()
            if configured.exists():
                return configured
            for suffix in (".cmd", ".bat", ".exe"):
                candidate = Path(f"{configured}{suffix}")
                if candidate.exists():
                    return candidate
        if self.install_root:
            install_root = Path(self.install_root).expanduser().resolve()
            if os.name == "nt":
                relative_paths = (
                    Path("bin/mysqld.exe"),
                    Path("bin/mysqld.cmd"),
                    Path("bin/mysqld.bat"),
                    Path("bin/mysqld"),
                    Path("usr/sbin/mysqld.exe"),
                    Path("usr/sbin/mysqld.cmd"),
                    Path("usr/sbin/mysqld.bat"),
                    Path("usr/sbin/mysqld"),
                )
            else:
                relative_paths = (
                    Path("bin/mysqld"),
                    Path("bin/mysqld.exe"),
                    Path("bin/mysqld.cmd"),
                    Path("bin/mysqld.bat"),
                    Path("usr/sbin/mysqld"),
                    Path("usr/sbin/mysqld.exe"),
                    Path("usr/sbin/mysqld.cmd"),
                    Path("usr/sbin/mysqld.bat"),
                )
            for relative_path in relative_paths:
                managed_binary = install_root / relative_path
                if managed_binary.exists():
                    return managed_binary
        return Path("mysqld")

    def _build_mysql_process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if not self.runtime_library_paths:
            return env
        existing = env.get("LD_LIBRARY_PATH", "")
        paths = [path for path in self.runtime_library_paths if path]
        if existing:
            paths.append(existing)
        env["LD_LIBRARY_PATH"] = ":".join(paths)
        return env

    def _check_binary_dependencies(
        self, binary: Path, env: dict[str, str] | None = None
    ) -> list[str]:
        try:
            result = subprocess.run(
                ["ldd", str(binary)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        except FileNotFoundError:
            return []

        missing: list[str] = []
        for line in result.stdout.splitlines():
            if "=> not found" not in line:
                continue
            missing.append(line.split("=>", 1)[0].strip())
        return missing

    def _filter_mysql_server_options(
        self,
        mysql_config: dict[str, Any],
    ) -> dict[str, Any]:
        reserved_keys = {"health_check_mode"}
        return {
            key: value
            for key, value in mysql_config.items()
            if key not in reserved_keys
        }

    def _mysql_health_check(self, pid: int) -> Tuple[bool, str]:
        if not self._is_port_open(self.host, self.port):
            return False, f"MySQL port {self.port} is not reachable"
        mode = str(self.mysql_config.get("health_check_mode", "sql")).lower()
        if mode == "tcp":
            return True, f"MySQL server healthy (PID: {pid}, tcp reachable)"
        return self._mysql_sql_health_check(pid)

    def _mysql_sql_health_check(self, pid: int) -> Tuple[bool, str]:
        if importlib.util.find_spec("pymysql") is None:
            return True, (
                f"MySQL server healthy (PID: {pid}, tcp reachable, sql check skipped)"
            )
        try:
            import pymysql  # type: ignore[import-untyped]

            connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=str(self.mysql_config.get("username", "root")),
                password=str(self.mysql_config.get("password", "")),
                database=self.mysql_config.get("database") or None,
                connect_timeout=5,
                read_timeout=5,
                write_timeout=5,
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
            connection.close()
            if row and row[0] == 1:
                return True, f"MySQL server healthy (PID: {pid}, sql validated)"
            return False, "MySQL SQL health check returned unexpected result"
        except Exception as exc:
            return False, f"MySQL SQL health check failed: {exc}"

    def _ensure_mysql_database(self) -> Tuple[bool, str]:
        database_name = str(self.database_name or "").strip()
        if not database_name:
            return True, "MySQL scenario database not configured"
        if str(self.mysql_config.get("health_check_mode", "sql")).lower() == "tcp":
            return True, "MySQL scenario database creation skipped for tcp-only mode"
        if importlib.util.find_spec("pymysql") is None:
            return True, "PyMySQL unavailable; scenario database creation skipped"
        if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
            return False, f"Invalid MySQL database name: {database_name}"
        try:
            import pymysql  # type: ignore[import-untyped]

            connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=str(self.mysql_config.get("username", "root")),
                password=str(self.mysql_config.get("password", "")),
                connect_timeout=5,
                read_timeout=5,
                write_timeout=5,
                charset="utf8mb4",
                autocommit=True,
            )
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}`")
            connection.close()
            self.mysql_config.setdefault("database", database_name)
            return True, f"MySQL scenario database ready: {database_name}"
        except Exception as exc:
            return False, f"MySQL scenario database init failed: {exc}"

    def _is_port_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=3):
                return True
        except OSError:
            return False

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
