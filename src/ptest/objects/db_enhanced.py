# ptest/objects/db_enhanced.py
"""
增强的数据库对象 - 正确的服务端/客户端分离架构
"""

from .base import BaseManagedObject
from .db_server import DatabaseServerComponent
from .db_client import DatabaseClientComponent
from typing import Dict, Any, Optional, Tuple

try:
    from ..utils import get_colored_text
except ImportError:

    def get_colored_text(text: Any, color_code: Any) -> str:
        return str(text)


class DatabaseServerObject(BaseManagedObject):
    """数据库服务端对象"""

    def __init__(self, name: str, env_manager):
        super().__init__(name, "database_server", env_manager)
        self.server_component: Optional[DatabaseServerComponent] = None

    def install(self, params: Dict[str, Any] = None) -> str:  # type: ignore
        """安装数据库服务端"""
        if not params:
            return "✗ Database server installation requires parameters"

        self.env_manager.logger.info(f"Installing database server: {self.name}")

        # 准备服务端配置
        server_config = {
            "db_type": params.get("db_type", "sqlite"),
            "host": params.get("server_host", "localhost"),
            "port": params.get(
                "server_port", self._get_default_port(params.get("db_type", "sqlite"))
            ),
            "data_dir": params.get("data_dir", f"/tmp/{self.name}_data"),
            "log_file": params.get("log_file", f"/tmp/{self.name}.log"),
            "pid_file": params.get("pid_file", f"/tmp/{self.name}.pid"),
        }

        # 添加数据库特定配置
        if "mysql_config" in params:
            server_config["mysql_config"] = params["mysql_config"]
        if "postgresql_config" in params:
            server_config["postgresql_config"] = params["postgresql_config"]
        if "mongodb_config" in params:
            server_config["mongodb_config"] = params["mongodb_config"]

        try:
            self.server_component = DatabaseServerComponent(server_config)
            self.installed = True
            self.status = "installed"

            db_type = server_config["db_type"]
            return f"✓ {get_colored_text('Database Server', 92)} object '{self.name}' ({db_type}) installed and ready"

        except Exception as e:
            return f"✗ Failed to install database server: {str(e)}"

    def start(self) -> str:
        """启动数据库服务端"""
        if not self.installed or not self.server_component:
            return f"✗ Database server '{self.name}' not installed"

        self.env_manager.logger.info(f"Starting database server: {self.name}")

        try:
            success, message = self.server_component.start()
            if success:
                self.status = "running"
                return f"✓ {get_colored_text('Database Server', 92)} '{self.name}' started: {message}"
            else:
                return f"✗ Failed to start database server: {message}"
        except Exception as e:
            return f"✗ Server start error: {str(e)}"

    def stop(self) -> str:
        """停止数据库服务端"""
        if self.status != "running":
            return f"✗ Database server '{self.name}' not running"

        self.env_manager.logger.info(f"Stopping database server: {self.name}")

        try:
            success, message = self.server_component.stop()  # type: ignore
            if success:
                self.status = "stopped"
                return f"✓ {get_colored_text('Database Server', 92)} '{self.name}' stopped: {message}"
            else:
                return f"✗ Failed to stop database server: {message}"
        except Exception as e:
            return f"✗ Server stop error: {str(e)}"

    def restart(self) -> str:
        """重启数据库服务端"""
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result

    def uninstall(self) -> str:
        """卸载数据库服务端"""
        if self.status == "running":
            self.stop()

        self.env_manager.logger.info(f"Removing database server: {self.name}")

        try:
            if self.server_component:
                if self.server_component.status == "running":
                    self.server_component.stop()
                self.server_component = None

            self.installed = False
            self.status = "removed"
            return (
                f"✓ {get_colored_text('Database Server', 92)} '{self.name}' uninstalled"
            )
        except Exception as e:
            return f"✗ Server uninstall error: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        """获取服务端状态"""
        if not self.server_component:
            return {
                "name": self.name,
                "type_name": self.type_name,
                "status": self.status,
                "installed": self.installed,
                "message": "Server component not initialized",
            }

        return self.server_component.get_status()

    def health_check(self) -> str:
        """健康检查"""
        if not self.server_component:
            return f"✗ Database server '{self.name}' not installed"

        try:
            success, message = self.server_component.health_check()
            if success:
                return f"✓ {get_colored_text('Database Server', 92)} '{self.name}' healthy: {message}"
            else:
                return f"✗ {get_colored_text('Database Server', 91)} '{self.name}' unhealthy: {message}"
        except Exception as e:
            return f"✗ Health check error: {str(e)}"

    def get_endpoint(self) -> str:
        """获取服务端点"""
        if self.server_component:
            return self.server_component.get_endpoint()
        return ""

    def _get_default_port(self, db_type: str) -> int:
        """获取数据库默认端口"""
        port_mapping = {
            "mysql": 3306,
            "postgresql": 5432,
            "postgres": 5432,
            "mongodb": 27017,
            "oracle": 1521,
            "sqlserver": 1433,
            "redis": 6379,
        }
        return port_mapping.get(db_type.lower(), 0)


class DatabaseClientObject(BaseManagedObject):
    """数据库客户端对象"""

    def __init__(self, name: str, env_manager):
        super().__init__(name, "database_client", env_manager)
        self.client_component: Optional[DatabaseClientComponent] = None

    def install(self, params: Dict[str, Any] = None) -> str:  # type: ignore
        """安装数据库客户端"""
        if not params:
            return "✗ Database client installation requires parameters"

        self.env_manager.logger.info(f"Installing database client: {self.name}")

        # 准备客户端配置
        client_config = {
            "db_type": params.get("db_type", "sqlite"),
            "server_host": params.get("server_host", "localhost"),
            "server_port": params.get(
                "server_port", self._get_default_port(params.get("db_type", "sqlite"))
            ),
            "database": params.get("database", ""),
            "username": params.get("username", ""),
            "password": params.get("password", ""),
            "timeout": params.get("timeout", 30),
            "connection_params": params.get("connection_params", {}),
        }

        try:
            self.client_component = DatabaseClientComponent(client_config)
            self.installed = True
            self.status = "installed"

            db_type = client_config["db_type"]
            return f"✓ {get_colored_text('Database Client', 92)} object '{self.name}' ({db_type}) installed and ready"

        except Exception as e:
            return f"✗ Failed to install database client: {str(e)}"

    def start(self) -> str:
        """启动数据库客户端（建立连接）"""
        if not self.installed or not self.client_component:
            return f"✗ Database client '{self.name}' not installed"

        self.env_manager.logger.info(f"Starting database client: {self.name}")

        try:
            success, message = self.client_component.start()
            if success:
                self.status = "running"
                return f"✓ {get_colored_text('Database Client', 92)} '{self.name}' connected: {message}"
            else:
                return f"✗ Failed to connect database client: {message}"
        except Exception as e:
            return f"✗ Client start error: {str(e)}"

    def stop(self) -> str:
        """停止数据库客户端（断开连接）"""
        if self.status != "running":
            return f"✗ Database client '{self.name}' not running"

        self.env_manager.logger.info(f"Stopping database client: {self.name}")

        try:
            success, message = self.client_component.stop()  # type: ignore
            if success:
                self.status = "stopped"
                return f"✓ {get_colored_text('Database Client', 92)} '{self.name}' disconnected: {message}"
            else:
                return f"✗ Failed to disconnect database client: {message}"
        except Exception as e:
            return f"✗ Client stop error: {str(e)}"

    def restart(self) -> str:
        """重启数据库客户端"""
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result

    def uninstall(self) -> str:
        """卸载数据库客户端"""
        if self.status == "running":
            self.stop()

        self.env_manager.logger.info(f"Removing database client: {self.name}")

        try:
            if self.client_component:
                if self.client_component.status == "running":
                    self.client_component.stop()
                self.client_component = None

            self.installed = False
            self.status = "removed"
            return (
                f"✓ {get_colored_text('Database Client', 92)} '{self.name}' uninstalled"
            )
        except Exception as e:
            return f"✗ Client uninstall error: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        if not self.client_component:
            return {
                "name": self.name,
                "type_name": self.type_name,
                "status": self.status,
                "installed": self.installed,
                "message": "Client component not initialized",
            }

        return self.client_component.get_status()

    def health_check(self) -> str:
        """健康检查"""
        if not self.client_component:
            return f"✗ Database client '{self.name}' not installed"

        try:
            success, message = self.client_component.health_check()
            if success:
                return f"✓ {get_colored_text('Database Client', 92)} '{self.name}' healthy: {message}"
            else:
                return f"✗ {get_colored_text('Database Client', 91)} '{self.name}' unhealthy: {message}"
        except Exception as e:
            return f"✗ Health check error: {str(e)}"

    def execute_query(self, query: str) -> Tuple[bool, Any]:  # type: ignore
        """执行数据库查询"""
        if not self.installed or not self.client_component:
            return False, f"Database client '{self.name}' not properly installed"

        try:
            return self.client_component.execute_query(query)
        except Exception as e:
            return False, f"Query execution error: {str(e)}"

    def get_server_endpoint(self) -> str:
        """获取服务端点"""
        if self.client_component:
            return self.client_component.server_endpoint
        return ""

    def _get_default_port(self, db_type: str) -> int:
        """获取数据库默认端口"""
        port_mapping = {
            "mysql": 3306,
            "postgresql": 5432,
            "postgres": 5432,
            "mongodb": 27017,
            "oracle": 1521,
            "sqlserver": 1433,
            "redis": 6379,
        }
        return port_mapping.get(db_type.lower(), 0)
