# ptest/objects/db_v2.py
"""
数据库对象 v2.0 - 支持服务端和客户端分离管理
"""

from .base import BaseManagedObject
from .db_server import DatabaseServerComponent
from .db_client import DatabaseClientComponent
from typing import Dict, Any, Optional, Tuple


try:
    from ..utils import get_colored_text
except ImportError:

    def get_colored_text(text, color_code):
        return text


class EnhancedDBObject(BaseManagedObject):
    """增强的数据库对象，支持服务端和客户端管理"""

    def __init__(self, name: str, env_manager):
        super().__init__(name, "database", env_manager)
        self.server_component: Optional[DatabaseServerComponent] = None
        self.client_component: Optional[DatabaseClientComponent] = None
        self.mode = "client_only"  # client_only, server_only, full_stack

    def install(self, params: Dict[str, Any] = None) -> str:  # type: ignore
        """安装数据库对象"""
        if not params:
            return f"✗ Database installation requires parameters"

        self.env_manager.logger.info(
            f"Installing enhanced database object: {self.name}"
        )

        # 确定部署模式
        self.mode = params.get("mode", "client_only")

        # 安装服务端组件（如果需要）
        if self.mode in ["server_only", "full_stack"]:
            server_config = self._prepare_server_config(params)
            try:
                self.server_component = DatabaseServerComponent(server_config)
                self.env_manager.logger.info(
                    f"Server component initialized for {self.name}"
                )
            except Exception as e:
                return f"✗ Failed to initialize server component: {str(e)}"

        # 安装客户端组件
        if self.mode in ["client_only", "full_stack"]:
            client_config = self._prepare_client_config(params)
            try:
                self.client_component = DatabaseClientComponent(client_config)
                self.env_manager.logger.info(
                    f"Client component initialized for {self.name}"
                )
            except Exception as e:
                return f"✗ Failed to initialize client component: {str(e)}"

        # 测试客户端连接
        if self.client_component:
            success, message = self.client_component.test_connection()
            if not success:
                return f"✗ Database connection test failed: {message}"

        self.installed = True
        self.status = "installed"

        mode_desc = self._get_mode_description()
        return f"✓ {get_colored_text('Enhanced Database', 92)} object '{self.name}' ({mode_desc}) installed and ready"

    def start(self) -> str:
        """启动数据库对象"""
        if not self.installed:
            return f"✗ Database object '{self.name}' not installed"

        self.env_manager.logger.info(f"Starting enhanced database object: {self.name}")

        results = []

        # 启动服务端（如果有）
        if self.server_component:
            success, message = self.server_component.start()
            if success:
                results.append(f"Server: {message}")
            else:
                return f"✗ Failed to start server: {message}"

        # 启动客户端（建立连接）
        if self.client_component:
            success, message = self.client_component.start()
            if success:
                results.append(f"Client: {message}")
            else:
                return f"✗ Failed to start client: {message}"

        self.status = "running"
        return (
            f"✓ {get_colored_text('Enhanced Database', 92)} object '{self.name}' started:\n"
            + "\n".join(results)
        )

    def stop(self) -> str:
        """停止数据库对象"""
        if self.status != "running":
            return f"✗ Database object '{self.name}' not running"

        self.env_manager.logger.info(f"Stopping enhanced database object: {self.name}")

        results = []

        # 停止客户端
        if self.client_component:
            success, message = self.client_component.stop()
            if success:
                results.append(f"Client: {message}")
            else:
                results.append(f"Client: {message}")

        # 停止服务端
        if self.server_component:
            success, message = self.server_component.stop()
            if success:
                results.append(f"Server: {message}")
            else:
                results.append(f"Server: {message}")

        self.status = "stopped"
        return (
            f"✓ {get_colored_text('Enhanced Database', 92)} object '{self.name}' stopped:\n"
            + "\n".join(results)
        )

    def restart(self) -> str:
        """重启数据库对象"""
        result = self.stop()
        if "✓" not in result:
            return result

        return self.start()

    def uninstall(self) -> str:
        """卸载数据库对象"""
        if self.status == "running":
            self.stop()

        self.env_manager.logger.info(f"Removing enhanced database object: {self.name}")

        # 清理服务端
        if self.server_component:
            try:
                if self.server_component.status == "running":
                    self.server_component.stop()
                self.server_component = None
            except Exception as e:
                self.env_manager.logger.warning(
                    f"Error cleaning server component: {str(e)}"
                )

        # 清理客户端
        if self.client_component:
            try:
                if self.client_component.status == "running":
                    self.client_component.stop()
                self.client_component = None
            except Exception as e:
                self.env_manager.logger.warning(
                    f"Error cleaning client component: {str(e)}"
                )

        self.installed = False
        self.status = "removed"
        return f"✓ {get_colored_text('Enhanced Database', 92)} object '{self.name}' uninstalled"

    def get_status(self) -> Dict[str, Any]:
        """获取数据库对象状态"""
        status = {
            "name": self.name,
            "type_name": self.type_name,
            "mode": self.mode,
            "status": self.status,
            "installed": self.installed,
            "server_status": None,
            "client_status": None,
            "overall_health": "unknown",
        }

        # 获取服务端状态
        if self.server_component:
            status["server_status"] = self.server_component.get_status()

        # 获取客户端状态
        if self.client_component:
            status["client_status"] = self.client_component.get_status()

        # 评估整体健康状态
        status["overall_health"] = self._evaluate_health(status)

        return status

    def health_check(self) -> Tuple[bool, str]:
        """执行健康检查"""
        if not self.installed:
            return False, "Database object not installed"

        health_results = []

        # 检查服务端健康状态
        if self.server_component:
            success, message = self.server_component.health_check()
            health_results.append(
                {"component": "server", "healthy": success, "message": message}
            )

        # 检查客户端健康状态
        if self.client_component:
            success, message = self.client_component.health_check()
            health_results.append(
                {"component": "client", "healthy": success, "message": message}
            )

        # 评估整体健康状态
        all_healthy = all(result["healthy"] for result in health_results)
        messages = [result["message"] for result in health_results]

        if all_healthy:
            return True, f"All components healthy: {'; '.join(messages)}"
        else:
            return False, f"Health issues detected: {'; '.join(messages)}"

    def execute_query(self, query: str) -> Tuple[bool, Any]:
        """执行数据库查询（通过客户端）"""
        if not self.installed or not self.client_component:
            return False, f"Database '{self.name}' client not properly installed"

        return self.client_component.execute_query(query)

    def get_server_component(self) -> Optional[DatabaseServerComponent]:
        """获取服务端组件"""
        return self.server_component if self.installed else None

    def get_client_component(self) -> Optional[DatabaseClientComponent]:
        """获取客户端组件"""
        return self.client_component if self.installed else None

    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        info = {
            "name": self.name,
            "mode": self.mode,
            "has_server": self.server_component is not None,
            "has_client": self.client_component is not None,
        }

        if self.server_component:
            info["server_info"] = self.server_component.get_status()
            info["server_endpoint"] = self.server_component.get_endpoint()
            info["connection_info"] = self.server_component.get_connection_info()

        if self.client_component:
            info["client_info"] = self.client_component.get_status()
            info["connection_details"] = self.client_component.get_connection_details()

        return info

    def _prepare_server_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """准备服务端配置"""
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

        return server_config

    def _prepare_client_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """准备客户端配置"""
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

        return client_config

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

    def _get_mode_description(self) -> str:
        """获取模式描述"""
        mode_descriptions = {
            "client_only": "Client Only",
            "server_only": "Server Only",
            "full_stack": "Full Stack (Server + Client)",
        }
        return mode_descriptions.get(self.mode, "Unknown")

    def _evaluate_health(self, status: Dict[str, Any]) -> str:
        """评估整体健康状态"""
        server_healthy = True
        client_healthy = True

        if status["server_status"]:
            server_healthy = status["server_status"].get("status") == "running"

        if status["client_status"]:
            client_healthy = status["client_status"].get("connected", False)

        if server_healthy and client_healthy:
            return "healthy"
        elif server_healthy or client_healthy:
            return "degraded"
        else:
            return "unhealthy"


# 向后兼容的DBObject别名
DBObject = EnhancedDBObject
