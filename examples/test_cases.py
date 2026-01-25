# ptest/examples/test_cases.py
"""
测试用例示例
展示如何定义不同类型的测试用例
"""

# API测试用例示例
api_test_cases = {
    "api_get_users": {
        "type": "api",
        "method": "GET",
        "url": "https://jsonplaceholder.typicode.com/users",
        "expected_status": 200,
        "expected_response": {
            "count": 10  # 预期返回10个用户
        },
        "timeout": 30,
    },
    "api_create_post": {
        "type": "api",
        "method": "POST",
        "url": "https://jsonplaceholder.typicode.com/posts",
        "headers": {"Content-Type": "application/json"},
        "body": {"title": "Test Post", "body": "This is a test post", "userId": 1},
        "expected_status": 201,
        "timeout": 30,
    },
}

# 数据库测试用例示例（使用数据库对象架构）
database_test_cases = {
    "mysql_user_count": {
        "type": "database",
        "db_object": "my_mysql_db",  # 指向数据库对象
        "query": "SELECT COUNT(*) as user_count FROM users",
        "expected_result": {
            "count": 5  # 预期返回5个用户
        },
    },
    "sqlite_select_data": {
        "type": "database",
        "db_object": "my_sqlite_db",  # 指向数据库对象
        "query": "SELECT * FROM test_table WHERE status = 'active'",
        "expected_result": {
            "count": 3  # 预期返回3条记录
        },
    },
}

# 数据库对象配置示例
database_objects_config = {
    "my_mysql_db": {
        "type": "database",
        "db_type": "mysql",
        "host": "localhost",
        "port": 3306,
        "database": "test_db",
        "username": "root",
        "password": "",
        "timeout": 30,
    },
    "my_sqlite_db": {
        "type": "database",
        "db_type": "sqlite",
        "database": "/path/to/test.db",
        "timeout": 30,
    },
    "my_postgresql_db": {
        "type": "database",
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database": "test_db",
        "username": "postgres",
        "password": "",
        "timeout": 30,
    },
}

# Web测试用例示例
web_test_cases = {
    "website_homepage": {
        "type": "web",
        "url": "https://example.com",
        "expected_title": "Example Domain",
        "expected_content": "This domain is for use in illustrative examples",
        "timeout": 30,
    }
}

# 服务测试用例示例
service_test_cases = {
    "web_service_port": {
        "type": "service",
        "service_name": "web_service",
        "check_type": "port",
        "host": "localhost",
        "port": 8080,
        "timeout": 10,
    }
}

# 合并所有测试用例
all_test_cases = {
    **api_test_cases,
    **database_test_cases,
    **web_test_cases,
    **service_test_cases,
}

if __name__ == "__main__":
    # 打印测试用例示例
    import json

    print("=== Test Case Examples ===")
    print(json.dumps(all_test_cases, indent=2))
