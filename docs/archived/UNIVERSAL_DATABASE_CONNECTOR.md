# 通用数据库连接器使用指南

## 🎉 通用数据库连接器架构

实现了一个通用的数据库连接器架构，支持任意数据库类型！

## 📋 支持的数据库类型

### 内置支持
- **SQLite** - 通过内置sqlite3模块
- **MySQL** - 通过pymysql或mysql.connector
- **PostgreSQL** - 通过psycopg2或pg8000
- **Oracle** - 通过cx_Oracle或oracledb
- **SQL Server** - 通过pyodbc或pymssql
- **MongoDB** - 通过pymongo

### 自定义扩展
- **Redis** - 示例自定义连接器
- **任何数据库** - 通过配置或注册自定义连接器

## 🚀 使用方式

### 1. 基本配置

```python
# SQLite数据库
db_config = {
    'driver': 'sqlite',
    'database': '/path/to/database.db',
    'timeout': 30
}

# MySQL数据库
db_config = {
    'driver': 'mysql',
    'host': 'localhost',
    'port': 3306,
    'username': 'root',
    'password': 'password',
    'database': 'mydb',
    'charset': 'utf8mb4'
}

# MongoDB数据库
db_config = {
    'driver': 'mongodb',
    'host': 'localhost',
    'port': 27017,
    'database': 'mydb'
}

# PostgreSQL数据库
db_config = {
    'driver': 'postgresql',
    'host': 'localhost',
    'port': 5432,
    'username': 'postgres',
    'password': 'password',
    'database': 'mydb'
}
```

### 2. 高级配置

```python
# 使用自定义连接模块
db_config = {
    'connection_module': 'custom_db_module',
    'connection_config': {
        'host': 'localhost',
        'port': 1234,
        'custom_param': 'value'
    }
}

# 使用连接参数
db_config = {
    'driver': 'mysql',
    'host': 'localhost',
    'username': 'root',
    'password': 'password',
    'database': 'mydb',
    'connection_params': {
        'autocommit': True,
        'charset': 'utf8mb4',
        'connect_timeout': 30
    }
}
```

### 3. 创建数据库对象

```python
# 通过对象管理器创建
obj_manager.install("database", "my_sqlite_db", {
    'driver': 'sqlite',
    'database': 'test.db'
})

# 直接创建
db_object = DBObject("my_db", env_manager)
result = db_object.install({
    'driver': 'mysql',
    'host': 'localhost',
    'username': 'root',
    'password': 'password',
    'database': 'test'
})
```

### 4. 测试用例配置

```python
# SQL数据库测试用例
test_case = {
    "type": "database",
    "db_object": "my_mysql_db",
    "query": "SELECT COUNT(*) as count FROM users WHERE status = 'active'",
    "expected_result": {"count": 10}
}

# MongoDB测试用例
test_case = {
    "type": "database",
    "db_object": "my_mongodb_db",
    "query": '{"collection": "users", "filter": {"status": "active"}}',
    "expected_result": {"count": 10}
}

# 简单MongoDB查询
test_case = {
    "type": "database",
    "db_object": "my_mongodb_db",
    "query": 'users',  # 集合名
    "expected_result": {"count": 50}
}
```

## 📚 配置选项详解

### driver (必需)
指定数据库驱动类型：
- `sqlite` - SQLite数据库
- `mysql` - MySQL数据库  
- `postgresql` 或 `postgres` - PostgreSQL数据库
- `oracle` - Oracle数据库
- `sqlserver` - SQL Server数据库
- `mongodb` - MongoDB数据库
- `generic` - 通用数据库（需要其他配置）

### 数据库特定配置

#### SQLite
- `database` 或 `db_file` - 数据库文件路径
- `timeout` - 连接超时时间

#### MySQL
- `host` - 服务器地址
- `port` - 端口号（默认3306）
- `username` 或 `user` - 用户名
- `password` - 密码
- `database` 或 `db` - 数据库名
- `charset` - 字符集（默认utf8mb4）

#### PostgreSQL
- `host` - 服务器地址
- `port` - 端口号（默认5432）
- `username` 或 `user` - 用户名
- `password` - 密码
- `database` 或 `db` - 数据库名

#### MongoDB
- `host` - 服务器地址
- `port` - 端口号（默认27017）
- `database` 或 `db` - 数据库名
- `connection_string` - 完整连接字符串

#### Oracle
- `host` - 服务器地址
- `service_name` - 服务名
- `username` 或 `user` - 用户名
- `password` - 密码
- `dsn` - 完整DSN字符串

#### SQL Server
- `host` - 服务器地址
- `database` - 数据库名
- `username` 或 `user` - 用户名
- `password` - 密码
- `odbc_driver` - ODBC驱动名称

### 通用配置
- `connection_params` - 额外的连接参数字典
- `connection_module` - 自定义连接模块名
- `connection_config` - 自定义连接配置

## 🔧 自定义数据库连接器

### 创建自定义连接器

```python
from ptest.objects.db import DatabaseConnector, DatabaseRegistry

class CustomDBConnector(DatabaseConnector):
    def __init__(self, config):
        super().__init__(config)
        # 初始化自定义连接
    
    def connect(self):
        # 建立连接逻辑
        pass
    
    def execute_query(self, query):
        # 执行查询逻辑
        pass
    
    def close(self):
        # 关闭连接逻辑
        pass
    
    def test_connection(self):
        # 测试连接逻辑
        pass

# 注册自定义连接器
DatabaseRegistry.register('custom_db', CustomDBConnector)
```

### 使用自定义连接器

```python
# 创建自定义数据库对象
obj_manager.install("database", "my_custom_db", {
    'driver': 'custom_db',
    'custom_param1': 'value1',
    'custom_param2': 'value2'
})
```

## 📝 MongoDB查询格式

MongoDB支持两种查询格式：

### 1. JSON格式（推荐）
```python
# 简单查询
query = '{"collection": "users", "filter": {"status": "active"}}'

# 复杂查询
query = '''
{
    "collection": "users",
    "filter": {
        "age": {"$gt": 18},
        "status": "active"
    },
    "projection": {"name": 1, "email": 1},
    "limit": 10
}
'''
```

### 2. 简单集合名
```python
# 查询整个集合
query = 'users'
```

## 🎯 测试用例示例

### 多数据库测试场景

```python
# 1. SQLite测试
sqlite_test = {
    "type": "database",
    "db_object": "app_sqlite",
    "query": "SELECT COUNT(*) as bug_count FROM bugs WHERE status = 'open'",
    "expected_result": {"count": 5}
}

# 2. MySQL测试  
mysql_test = {
    "type": "database",
    "db_object": "analytics_mysql",
    "query": "SELECT DATE(created_at) as date, COUNT(*) as orders FROM orders GROUP BY DATE(created_at)",
    "expected_result": {"count": 30}
}

# 3. MongoDB测试
mongodb_test = {
    "type": "database",
    "db_object": "logs_mongodb",
    "query": '{"collection": "logs", "filter": {"level": "ERROR", "timestamp": {"$gte": "2024-01-01"}}, "limit": 100}',
    "expected_result": {"count": 10}
}

# 4. Redis测试（自定义）
redis_test = {
    "type": "database", 
    "db_object": "cache_redis",
    "query": "GET user_session_123",
    "expected_result": "active"
}
```

## 🏆 总结

通用数据库连接器架构的优势：

✅ **无限扩展** - 支持任意数据库类型  
✅ **灵活配置** - 多种配置方式满足不同需求  
✅ **动态注册** - 运行时注册新的数据库类型  
✅ **统一接口** - 所有数据库使用相同的API  
✅ **向后兼容** - 现有测试用例无需修改  
✅ **专业架构** - 符合企业级应用标准  

现在ptest框架支持**任何数据库**！🚀