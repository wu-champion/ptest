# ptest/objects/db.py
from .base import BaseManagedObject
from typing import Dict, Any, Optional, Tuple

try:
    from ..utils import get_colored_text
except ImportError:

    def get_colored_text(text, color_code):
        return text


class DatabaseConnector:
    """数据库连接器基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def connect(self):
        """建立数据库连接"""
        raise NotImplementedError("Subclasses must implement connect method")

    def execute_query(self, query: str) -> Tuple[bool, Any]:
        """执行查询并返回结果"""
        raise NotImplementedError("Subclasses must implement execute_query method")

    def close(self):
        """关闭数据库连接"""
        raise NotImplementedError("Subclasses must implement close method")

    def test_connection(self) -> Tuple[bool, str]:
        """测试数据库连接"""
        raise NotImplementedError("Subclasses must implement test_connection method")


class DatabaseRegistry:
    """数据库连接器注册表，支持动态注册和发现数据库类型"""

    _connectors = {}

    @classmethod
    def register(cls, db_type: str, connector_class):
        """注册数据库连接器"""
        cls._connectors[db_type.lower()] = connector_class

    @classmethod
    def get_connector(cls, db_type: str):
        """获取数据库连接器类"""
        return cls._connectors.get(db_type.lower())

    @classmethod
    def list_supported_types(cls) -> list:
        """列出支持的数据库类型"""
        return list(cls._connectors.keys())

    @classmethod
    def create_connector(cls, db_type: str, config: Dict[str, Any]):
        """创建数据库连接器实例"""
        connector_class = cls.get_connector(db_type)
        if not connector_class:
            raise ValueError(
                f"Unsupported database type: {db_type}. Supported types: {cls.list_supported_types()}"
            )
        return connector_class(config)


class GenericDatabaseConnector(DatabaseConnector):
    """通用数据库连接器，支持通过配置自定义连接逻辑"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.connection_module = None
        self.connection = None
        self._setup_connection()

    def _setup_connection(self):
        """根据配置设置连接模块"""
        # 支持多种连接配置方式
        if "connection_module" in self.config:
            # 方式1：直接指定连接模块
            module_name = self.config["connection_module"]
            self.connection_module = self._import_module(module_name)
        elif "driver" in self.config:
            # 方式2：通过driver配置自动选择连接方式
            driver = self.config["driver"].lower()
            if driver == "sqlite":
                self._setup_sqlite()
            elif driver == "mysql":
                self._setup_mysql()
            elif driver == "postgresql" or driver == "postgres":
                self._setup_postgresql()
            elif driver == "oracle":
                self._setup_oracle()
            elif driver == "sqlserver":
                self._setup_sqlserver()
            elif driver == "mongodb":
                self._setup_mongodb()
            else:
                raise ValueError(f"Unsupported driver: {driver}")
        else:
            # 方式3：通过db_type自动推断
            db_type = self.config.get("db_type", "").lower()
            if db_type:
                self.config["driver"] = db_type
                self._setup_connection()
            else:
                raise ValueError(
                    "Must specify either 'connection_module', 'driver', or 'db_type' in config"
                )

    def _import_module(self, module_name: str):
        """动态导入模块"""
        try:
            import importlib

            return importlib.import_module(module_name)
        except ImportError as e:
            raise ImportError(f"Failed to import module '{module_name}': {str(e)}")

    def _setup_sqlite(self):
        """设置SQLite连接"""
        import sqlite3

        self.connection_module = sqlite3

    def _setup_mysql(self):
        """设置MySQL连接"""
        try:
            import pymysql

            self.connection_module = pymysql
        except ImportError:
            try:
                import mysql.connector  # type: ignore

                self.connection_module = mysql.connector
            except ImportError:
                raise ImportError(
                    "Neither pymysql nor mysql.connector is available. Install with: pip install pymysql"
                )

    def _setup_postgresql(self):
        """设置PostgreSQL连接"""
        try:
            import psycopg2  # type: ignore

            self.connection_module = psycopg2
        except ImportError:
            try:
                import pg8000  # type: ignore

                self.connection_module = pg8000
            except ImportError:
                raise ImportError(
                    "Neither psycopg2 nor pg8000 is available. Install with: pip install psycopg2-binary"
                )

    def _setup_oracle(self):
        """设置Oracle连接"""
        try:
            import cx_Oracle  # type: ignore

            self.connection_module = cx_Oracle
        except ImportError:
            try:
                import oracledb  # type: ignore

                self.connection_module = oracledb
            except ImportError:
                raise ImportError(
                    "Neither cx_Oracle nor oracledb is available. Install with: pip install cx_Oracle"
                )

    def _setup_sqlserver(self):
        """设置SQL Server连接"""
        try:
            import pyodbc  # type: ignore

            self.connection_module = pyodbc
        except ImportError:
            try:
                import pymssql  # type: ignore

                self.connection_module = pymssql
            except ImportError:
                raise ImportError(
                    "Neither pyodbc nor pymssql is available. Install with: pip install pyodbc"
                )

    def _setup_mongodb(self):
        """设置MongoDB连接"""
        try:
            import pymongo  # type: ignore

            self.connection_module = pymongo
        except ImportError:
            raise ImportError(
                "pymongo is not available. Install with: pip install pymongo"
            )

    def connect(self):
        """建立数据库连接"""
        driver = self.config.get("driver", "").lower()

        if driver == "sqlite":
            return self._connect_sqlite()
        elif driver == "mysql":
            return self._connect_mysql()
        elif driver in ["postgresql", "postgres"]:
            return self._connect_postgresql()
        elif driver == "oracle":
            return self._connect_oracle()
        elif driver == "sqlserver":
            return self._connect_sqlserver()
        elif driver == "mongodb":
            return self._connect_mongodb()
        elif "connection_module" in self.config:
            return self._connect_generic()
        else:
            raise ValueError(f"Unsupported driver: {driver}")

    def _connect_sqlite(self):
        """连接SQLite数据库"""
        database = self.config.get("database", self.config.get("db_file", ":memory:"))
        timeout = self.config.get("timeout", 30)

        self.connection = self.connection_module.connect(database, timeout=timeout)  # type: ignore
        if hasattr(self.connection, "row_factory"):
            self.connection.row_factory = self.connection_module.Row  # type: ignore
        return self.connection

    def _connect_mysql(self):
        """连接MySQL数据库"""
        self.connection = self.connection_module.connect(  # type: ignore
            host=self.config.get("host", "localhost"),
            port=self.config.get("port", 3306),
            user=self.config.get("username", self.config.get("user", "root")),
            password=self.config.get("password", ""),
            database=self.config.get("database", self.config.get("db", "")),
            charset=self.config.get("charset", "utf8mb4"),
            connect_timeout=self.config.get("timeout", 30),
            **self.config.get("connection_params", {}),
        )
        return self.connection

    def _connect_postgresql(self):
        """连接PostgreSQL数据库"""
        self.connection = self.connection_module.connect(  # type: ignore
            host=self.config.get("host", "localhost"),
            port=self.config.get("port", 5432),
            user=self.config.get("username", self.config.get("user", "postgres")),
            password=self.config.get("password", ""),
            database=self.config.get("database", self.config.get("db", "")),
            connect_timeout=self.config.get("timeout", 30),
            **self.config.get("connection_params", {}),
        )
        return self.connection

    def _connect_oracle(self):
        """连接Oracle数据库"""
        dsn = self.config.get(
            "dsn",
            f"{self.config.get('host', 'localhost')}/{self.config.get('service_name', 'ORCL')}",
        )

        self.connection = self.connection_module.connect(  # type: ignore
            user=self.config.get("username", self.config.get("user", "")),
            password=self.config.get("password", ""),
            dsn=dsn,
            **self.config.get("connection_params", {}),
        )
        return self.connection

    def _connect_sqlserver(self):
        """连接SQL Server数据库"""
        driver = self.config.get("odbc_driver", "{ODBC Driver 17 for SQL Server}")
        connection_string = (
            f"DRIVER={driver};"
            f"SERVER={self.config.get('host', 'localhost')};"
            f"DATABASE={self.config.get('database', '')};"
            f"UID={self.config.get('username', self.config.get('user', ''))};"
            f"PWD={self.config.get('password', '')}"
        )

        if self.connection_module.__name__ == "pyodbc":  # type: ignore
            self.connection = self.connection_module.connect(connection_string)  # type: ignore
        else:  # pymssql
            self.connection = self.connection_module.connect(  # type: ignore
                server=self.config.get("host", "localhost"),
                user=self.config.get("username", self.config.get("user", "")),
                password=self.config.get("password", ""),
                database=self.config.get("database", ""),
                port=self.config.get("port", 1433),
                **self.config.get("connection_params", {}),
            )
        return self.connection

    def _connect_mongodb(self):
        """连接MongoDB数据库"""
        connection_string = self.config.get(
            "connection_string",
            f"mongodb://{self.config.get('host', 'localhost')}:{self.config.get('port', 27017)}",
        )

        client = self.connection_module.MongoClient(  # type: ignore
            connection_string, **self.config.get("connection_params", {})
        )
        database_name = self.config.get("database", self.config.get("db", "test"))
        self.connection = client[database_name]
        return self.connection

    def _connect_generic(self):
        """通用连接方式"""
        connection_config = self.config.get("connection_config", {})
        if hasattr(self.connection_module, "connect"):
            self.connection = self.connection_module.connect(**connection_config)  # type: ignore
        elif hasattr(self.connection_module, "Connection"):
            self.connection = self.connection_module.Connection(**connection_config)  # type: ignore
        else:
            raise ValueError(
                f"Cannot determine how to connect using module {self.connection_module}"
            )
        return self.connection

    def execute_query(self, query: str) -> Tuple[bool, Any]:
        """执行查询并返回结果"""
        try:
            if not hasattr(self, "connection") or not self.connection:
                self.connect()

            driver = self.config.get("driver", "").lower()

            if driver == "mongodb":
                return self._execute_mongodb_query(query)
            else:
                return self._execute_sql_query(query)

        except Exception as e:
            return False, f"Database query error: {str(e)}"

    def _execute_sql_query(self, query: str) -> Tuple[bool, Any]:
        """执行SQL查询"""
        cursor = self.connection.cursor()  # type: ignore
        cursor.execute(query)

        if query.strip().upper().startswith("SELECT"):
            if hasattr(cursor, "fetchall"):
                result = cursor.fetchall()
                # 尝试转换为字典列表
                if result and hasattr(cursor, "description") and cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    if isinstance(result[0], (tuple, list)):
                        result = [dict(zip(columns, row)) for row in result]
            else:
                result = []
        else:
            if hasattr(self.connection, "commit"):
                self.connection.commit()  # type: ignore
            if hasattr(cursor, "rowcount"):
                result = (
                    f"Query executed successfully. Rows affected: {cursor.rowcount}"
                )
            else:
                result = "Query executed successfully"

        return True, result

    def _execute_mongodb_query(self, query: str) -> Tuple[bool, Any]:
        """执行MongoDB查询（查询应该是JSON格式或集合名）"""
        try:
            # 尝试解析为JSON查询
            import json

            query_data = json.loads(query)

            collection_name = query_data.get("collection")
            if not collection_name:
                return False, "MongoDB query must specify 'collection'"

            collection = self.connection[collection_name]  # type: ignore
            query_filter = query_data.get("filter", {})
            projection = query_data.get("projection", None)
            limit = query_data.get("limit", None)

            cursor = collection.find(query_filter, projection)
            if limit:
                cursor = cursor.limit(limit)

            result = list(cursor)
            # 将ObjectId转换为字符串
            for doc in result:
                if "_id" in doc and hasattr(doc["_id"], "str"):
                    doc["_id"] = str(doc["_id"])

            return True, result

        except json.JSONDecodeError:  # type: ignore
            # 如果不是JSON，当作集合名处理，返回所有文档
            if query in self.connection.list_collection_names():  # type: ignore
                collection = self.connection[query]  # type: ignore
                result = list(collection.find({}, {"_id": 0}))  # 排除_id字段
                return True, result
            else:
                return False, f"Collection '{query}' not found"
        except Exception as e:
            return False, f"MongoDB query error: {str(e)}"

    def close(self):
        """关闭数据库连接"""
        if hasattr(self, "connection") and self.connection:
            driver = self.config.get("driver", "").lower()

            if driver == "mongodb":
                # MongoDB需要关闭客户端连接
                if hasattr(self.connection, "client"):
                    self.connection.client.close()  # type: ignore
                elif hasattr(self.connection, "close"):
                    self.connection.close()
            else:
                # SQL数据库直接关闭连接
                if hasattr(self.connection, "close"):
                    self.connection.close()

    def test_connection(self) -> Tuple[bool, str]:
        """测试数据库连接"""
        try:
            conn = self.connect()
            driver = self.config.get("driver", "").lower()

            if driver == "mongodb":
                # MongoDB测试：运行一个简单的查询
                result = conn.command("ping")  # type: ignore
                if result.get("ok"):
                    return True, "MongoDB connection successful"
                else:
                    return False, f"MongoDB connection test failed: {result}"
            else:
                # SQL数据库测试：执行简单查询
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                return True, f"{driver.title()} connection successful"

        except Exception as e:
            return False, f"Connection test failed: {str(e)}"


# 注册预定义的数据库连接器
DatabaseRegistry.register("generic", GenericDatabaseConnector)
DatabaseRegistry.register("sqlite", GenericDatabaseConnector)
DatabaseRegistry.register("mysql", GenericDatabaseConnector)
DatabaseRegistry.register("postgresql", GenericDatabaseConnector)
DatabaseRegistry.register("oracle", GenericDatabaseConnector)
DatabaseRegistry.register("sqlserver", GenericDatabaseConnector)
DatabaseRegistry.register("mongodb", GenericDatabaseConnector)


class DBObject(BaseManagedObject):
    """通用数据库对象实现"""

    def __init__(self, name: str, env_manager):
        super().__init__(name, "database", env_manager)
        self.connector = None
        self.db_config = {}

    def install(self, params=None):
        if not params:
            return "✗ Database installation requires parameters"

        self.env_manager.logger.info(f"Installing database object: {self.name}")
        self.db_config = params.copy() if params else {}  # type: ignore
        # 使用通用数据库连接器
        try:
            self.connector = DatabaseRegistry.create_connector(
                self.db_config.get("driver", self.db_config.get("db_type", "generic")),
                self.db_config,
            )
        except ValueError as e:
            return f"✗ {str(e)}"

        # 测试连接
        success, message = self.connector.test_connection()
        if not success:
            return f"✗ Database connection test failed: {message}"

        self.installed = True
        self.status = "installed"
        driver = self.db_config.get("driver", self.db_config.get("db_type", "generic"))
        return f"✓ {get_colored_text('Database', 92)} object '{self.name}' ({driver}) installed and connected"

    def start(self):
        if not self.installed:
            return f"✗ Database object '{self.name}' not installed"
        self.env_manager.logger.info(f"Starting database object: {self.name}")
        self.status = "running"
        return f"✓ {get_colored_text('Database', 92)} object '{self.name}' started"

    def stop(self):
        if self.status != "running":
            return f"✗ Database object '{self.name}' not running"
        self.env_manager.logger.info(f"Stopping database object: {self.name}")

        if self.connector:
            self.connector.close()

        self.status = "stopped"
        return f"✓ {get_colored_text('Database', 92)} object '{self.name}' stopped"

    def restart(self):
        result = self.stop()
        if "✓" in result:
            return self.start()
        return result

    def uninstall(self):
        if self.status == "running":
            self.stop()
        self.env_manager.logger.info(f"Removing database object: {self.name}")

        if self.connector:
            self.connector.close()
            self.connector = None

        self.installed = False
        self.status = "removed"
        self.db_config = {}
        return f"✓ {get_colored_text('Database', 92)} object '{self.name}' uninstalled"

    def execute_query(self, query: str) -> Tuple[bool, Any]:
        """执行数据库查询"""
        if not self.installed or not self.connector:
            return False, f"Database '{self.name}' not properly installed"

        return self.connector.execute_query(query)

    def get_connector(self) -> Optional[DatabaseConnector]:
        """获取数据库连接器"""
        return self.connector if self.installed else None

    def get_config(self) -> Dict[str, Any]:
        """获取数据库配置"""
        return dict(self.db_config) if self.db_config else {}
