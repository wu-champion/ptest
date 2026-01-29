# ptest/objects/db_client.py
"""
数据库客户端组件
"""

from typing import Dict, Any, Tuple, Optional
from .service_base import ServiceClientComponent
from .db import DatabaseRegistry, GenericDatabaseConnector


class DatabaseClientComponent(ServiceClientComponent):
    """数据库客户端组件"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.db_type = config.get("db_type", "").lower()
        self.db_name = config.get("database", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.connection_params = config.get("connection_params", {})
        self.connector = None

        # 创建数据库连接器
        self._create_connector()

    def _create_connector(self):
        """创建数据库连接器"""
        try:
            client_config = {
                "driver": self.db_type,
                "host": self.server_host,
                "port": self.server_port,
                "username": self.username,
                "password": self.password,
                "database": self.db_name,
                "timeout": self.config.get("timeout", 30),
                **self.connection_params,
            }

            self.connector = DatabaseRegistry.create_connector(
                self.db_type, client_config
            )

        except Exception as e:
            raise Exception(f"Failed to create database connector: {str(e)}")

    def start(self) -> Tuple[bool, str]:
        """启动客户端（建立连接）"""
        if self.status == "running":
            return True, f"Database client already connected to {self.server_endpoint}"

        try:
            # 测试连接
            success, message = self.test_connection()
            if success:
                self.status = "running"
                return True, f"Database client connected to {self.server_endpoint}"
            else:
                return False, f"Failed to connect to database: {message}"
        except Exception as e:
            return False, f"Database client connection failed: {str(e)}"

    def stop(self) -> Tuple[bool, str]:
        """停止客户端（断开连接）"""
        if self.status != "running":
            return True, f"Database client not connected"

        try:
            if self.connector:
                self.connector.close()
            self.status = "stopped"
            return True, f"Database client disconnected from {self.server_endpoint}"
        except Exception as e:
            return False, f"Failed to disconnect database client: {str(e)}"

    def restart(self) -> Tuple[bool, str]:
        """重启客户端"""
        stop_result = self.stop()
        if not stop_result[0]:
            return stop_result

        return self.start()

    def get_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        status_info = {
            "status": self.status,
            "server_endpoint": self.server_endpoint,
            "db_type": self.db_type,
            "database": self.db_name,
            "username": self.username,
            "connected": self.status == "running",
            "connection_details": self._get_connection_details(),
        }

        return status_info

    def health_check(self) -> Tuple[bool, str]:
        """健康检查"""
        if self.status != "running":
            return False, f"Database client not connected (status: {self.status})"

        try:
            # 执行简单的查询测试连接
            success, result = self.execute_query("SELECT 1 as health_check")
            if success:
                return (
                    True,
                    f"Database client healthy, connected to {self.server_endpoint}",
                )
            else:
                return False, f"Database client health check failed: {result}"
        except Exception as e:
            return False, f"Database client health check error: {str(e)}"

    def connect_to_server(self) -> Tuple[bool, str]:
        """连接到服务端"""
        return self.start()

    def disconnect_from_server(self) -> Tuple[bool, str]:
        """断开与服务端的连接"""
        return self.stop()

    def test_connection(self) -> Tuple[bool, str]:
        """测试与服务端的连接"""
        if not self.connector:
            return False, "Database connector not initialized"

        try:
            return self.connector.test_connection()
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    def execute_query(self, query: str) -> Tuple[bool, Any]:
        """执行数据库查询"""
        if not self.connector:
            return False, "Database connector not available"

        try:
            return self.connector.execute_query(query)
        except Exception as e:
            return False, f"Query execution failed: {str(e)}"

    def execute_batch_queries(self, queries: list) -> Tuple[bool, list]:
        """批量执行查询"""
        if not self.connector:
            return False, ["Database connector not available"]

        results = []
        for query in queries:
            success, result = self.execute_query(query)
            results.append({"query": query, "success": success, "result": result})

        return all(r["success"] for r in results), results

    def get_connection_details(self) -> Dict[str, Any]:
        """获取详细连接信息"""
        if not self.connector:
            return {}

        return {
            "server_host": self.server_host,
            "server_port": self.server_port,
            "server_endpoint": self.server_endpoint,
            "database": self.db_name,
            "username": self.username,
            "db_type": self.db_type,
            "connector_type": type(self.connector).__name__,
            "connection_params": self.connection_params,
        }

    def _get_connection_details(self) -> Dict[str, Any]:
        """内部方法：获取连接详情"""
        return self.get_connection_details()

    def get_database_info(self) -> Tuple[bool, Dict[str, Any]]:
        """获取数据库信息"""
        if self.status != "running":
            return False, {"error": "Client not connected"}

        try:
            # 根据数据库类型获取信息
            if self.db_type == "mysql":
                return self._get_mysql_info()
            elif self.db_type in ["postgresql", "postgres"]:
                return self._get_postgresql_info()
            elif self.db_type == "sqlite":
                return self._get_sqlite_info()
            elif self.db_type == "mongodb":
                return self._get_mongodb_info()
            else:
                return True, {
                    "db_type": self.db_type,
                    "message": "Database info not implemented for this type",
                }
        except Exception as e:
            return False, {"error": f"Failed to get database info: {str(e)}"}

    def _get_mysql_info(self) -> Tuple[bool, Dict[str, Any]]:
        """获取MySQL数据库信息"""
        queries = [
            "SELECT VERSION() as version",
            "SELECT DATABASE() as current_database",
            "SELECT USER() as current_user",
            "SHOW STATUS LIKE 'Threads_connected'",
        ]

        success, results = self.execute_batch_queries(queries)
        if not success:
            return False, {"error": "Failed to get MySQL info"}

        info = {
            "db_type": "MySQL",
            "version": results[0]["result"] if results[0]["success"] else "Unknown",
            "current_database": results[1]["result"]
            if results[1]["success"]
            else "Unknown",
            "current_user": results[2]["result"]
            if results[2]["success"]
            else "Unknown",
            "connected_threads": results[3]["result"]
            if results[3]["success"]
            else "Unknown",
        }

        return True, info

    def _get_postgresql_info(self) -> Tuple[bool, Dict[str, Any]]:
        """获取PostgreSQL数据库信息"""
        queries = [
            "SELECT version()",
            "SELECT current_database()",
            "SELECT current_user",
        ]

        success, results = self.execute_batch_queries(queries)
        if not success:
            return False, {"error": "Failed to get PostgreSQL info"}

        info = {
            "db_type": "PostgreSQL",
            "version": results[0]["result"] if results[0]["success"] else "Unknown",
            "current_database": results[1]["result"]
            if results[1]["success"]
            else "Unknown",
            "current_user": results[2]["result"]
            if results[2]["success"]
            else "Unknown",
        }

        return True, info

    def _get_sqlite_info(self) -> Tuple[bool, Dict[str, Any]]:
        """获取SQLite数据库信息"""
        queries = [
            "SELECT sqlite_version()",
            "PRAGMA database_list",
            "PRAGMA table_info(test_table)",
        ]

        success, results = self.execute_batch_queries(queries)
        if not success:
            return False, {"error": "Failed to get SQLite info"}

        info = {
            "db_type": "SQLite",
            "version": results[0]["result"] if results[0]["success"] else "Unknown",
            "database_list": results[1]["result"] if results[1]["success"] else [],
            "table_info": results[2]["result"] if results[2]["success"] else [],
        }

        return True, info

    def _get_mongodb_info(self) -> Tuple[bool, Dict[str, Any]]:
        """获取MongoDB数据库信息"""
        try:
            # MongoDB需要特殊处理
            if hasattr(self.connector, "connection") and self.connector.connection:
                db = self.connector.connection

                info = {
                    "db_type": "MongoDB",
                    "database_name": db.name,
                    "server_info": self._get_mongodb_server_info(db),
                    "collections": self._get_mongodb_collections(db),
                }

                return True, info
            else:
                return False, {"error": "MongoDB connection not available"}
        except Exception as e:
            return False, {"error": f"Failed to get MongoDB info: {str(e)}"}

    def _get_mongodb_server_info(self, db) -> Dict[str, Any]:
        """获取MongoDB服务器信息"""
        try:
            if hasattr(db, "client") and db.client:
                # 获取服务器状态
                server_status = db.client.admin.command("serverStatus")
                return {
                    "version": server_status.get("version", "Unknown"),
                    "uptime": server_status.get("uptime", 0),
                    "connections": server_status.get("connections", {}),
                }
        except:
            pass
        return {}

    def _get_mongodb_collections(self, db) -> list:
        """获取MongoDB集合列表"""
        try:
            return db.list_collection_names()
        except:
            return []

    def backup_database(self, backup_path: str) -> Tuple[bool, str]:
        """备份数据库"""
        if self.status != "running":
            return False, "Database client not connected"

        try:
            if self.db_type == "mysql":
                return self._backup_mysql(backup_path)
            elif self.db_type in ["postgresql", "postgres"]:
                return self._backup_postgresql(backup_path)
            elif self.db_type == "sqlite":
                return self._backup_sqlite(backup_path)
            elif self.db_type == "mongodb":
                return self._backup_mongodb(backup_path)
            else:
                return False, f"Backup not implemented for {self.db_type}"
        except Exception as e:
            return False, f"Database backup failed: {str(e)}"

    def _backup_mysql(self, backup_path: str) -> Tuple[bool, str]:
        """备份MySQL数据库"""
        # 这里可以实现mysqldump调用
        return False, "MySQL backup not implemented yet"

    def _backup_postgresql(self, backup_path: str) -> Tuple[bool, str]:
        """备份PostgreSQL数据库"""
        # 这里可以实现pg_dump调用
        return False, "PostgreSQL backup not implemented yet"

    def _backup_sqlite(self, backup_path: str) -> Tuple[bool, str]:
        """备份SQLite数据库"""
        # SQLite可以直接复制文件
        try:
            if self.db_name and os.path.exists(self.db_name):
                import shutil

                shutil.copy2(self.db_name, backup_path)
                return True, f"SQLite database backed up to {backup_path}"
            else:
                return False, f"SQLite database file not found: {self.db_name}"
        except Exception as e:
            return False, f"SQLite backup failed: {str(e)}"

    def _backup_mongodb(self, backup_path: str) -> Tuple[bool, str]:
        """备份MongoDB数据库"""
        # 这里可以实现mongodump调用
        return False, "MongoDB backup not implemented yet"
