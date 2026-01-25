# ptest Python API 参考文档

## 📋 API 概述

ptest 提供了完整的 Python API，支持编程方式管理测试环境、对象、用例和报告生成。所有功能都通过面向对象的接口提供，易于集成到现有的开发流程中。

## 🔧 核心类

### TestFramework

框架的主要入口类，提供全局管理功能。

```python
from ptest import TestFramework, create_test_framework

# 方法1: 使用构造函数
framework = TestFramework()

# 方法2: 使用便捷函数
framework = create_test_framework()

# 创建测试环境
env = framework.create_environment("/path/to/test")

# 添加被测对象
mysql = env.add_object("mysql", "my_db", version="8.0")

# 添加测试用例
case = env.add_case("api_test", {
    "type": "api",
    "endpoint": "/api/users",
    "method": "GET",
    "assertions": [{"status_code": 200}]
})

# 运行测试
result = case.run()
print(f"测试结果: {result.status}, 耗时: {result.duration}s")

# 生成报告
report_path = framework.generate_report("html")
print(f"报告已生成: {report_path}")
```

### 上下文管理器使用

```python
from ptest import TestFramework

# 使用上下文管理器自动清理资源
with TestFramework() as framework:
    env = framework.create_environment("./test_env")
    
    # 对象也支持上下文管理器
    with env.add_object("mysql", "my_db", version="8.0") as mysql:
        # 对象会自动启动
        case = env.add_case("db_test", {
            "type": "database",
            "db_object": "my_db",
            "query": "SELECT COUNT(*) as count FROM users",
            "expected_result": {"count": 10}
        })
        
        result = case.run()
        print(f"数据库测试: {result.status}")
        
    # 对象会自动停止
```

## 📋 详细功能说明

### 1. 框架管理 (TestFramework)

```python
from ptest import TestFramework

# 创建框架
framework = TestFramework(config={
    "timeout": 300,
    "log_level": "INFO"
})

# 创建多个环境
dev_env = framework.create_environment("./dev_test", isolation="basic")
prod_env = framework.create_environment("./prod_test", isolation="basic")

# 获取环境
env = framework.get_environment("dev_test")  # 按名称
env = framework.get_environment("./dev_test")  # 按路径

# 框架状态
status = framework.get_status()
print(status)

# 列出所有环境
environments = framework.list_environments()
for env_info in environments:
    print(f"环境: {env_info['name']} - {env_info['path']}")

# 清理资源
framework.cleanup()
```

### 2. 环境管理 (TestEnvironment)

```python
# 创建环境
env = framework.create_environment("./test_env")

# 环境状态
status = env.get_status()
print(f"环境状态: {status}")

# 添加对象
mysql_obj = env.add_object("mysql", "my_mysql", version="8.0")
postgres_obj = env.add_object("postgresql", "my_pg", version="14")

# 添加测试用例
api_case = env.add_case("api_users", {
    "type": "api",
    "url": "https://jsonplaceholder.typicode.com/users",
    "method": "GET",
    "expected_status": 200
})

db_case = env.add_case("db_check", {
    "type": "database",
    "db_object": "my_mysql",
    "query": "SELECT 1 as test",
    "expected_result": {"test": 1}
})

# 运行测试
result1 = env.run_case("api_users")
result2 = env.run_case("db_check")

# 运行所有测试
all_results = env.run_all_cases()
for result in all_results:
    print(f"{result.case_id}: {result.status}")

# 生成报告
html_report = env.generate_report("html")
json_report = env.generate_report("json")
```

### 3. 对象管理 (ManagedObject)

```python
# 创建对象
mysql_obj = env.add_object("mysql", "my_db", version="8.0")

# 对象生命周期管理
success = mysql_obj.start()      # 启动
success = mysql_obj.stop()       # 停止
success = mysql_obj.restart()    # 重启
success = mysql_obj.uninstall()  # 卸载

# 获取对象状态
status = mysql_obj.get_status()
print(f"对象状态: {status}")

# 使用上下文管理器
with env.add_object("mysql", "temp_db") as mysql:
    # 对象已启动
    case = env.add_case("temp_test", {
        "type": "database",
        "db_object": "temp_db",
        "query": "SELECT VERSION()",
        "expected_result": {"version": "8.0"}
    })
    result = case.run()
    
# 对象已自动停止
```

### 4. 测试用例管理 (TestCase)

```python
# 创建测试用例
case = env.add_case("api_test", {
    "type": "api",
    "url": "https://api.example.com/users",
    "method": "GET",
    "headers": {"Authorization": "Bearer token"},
    "expected_status": 200,
    "expected_response": {"count": 10}
})

# 运行测试
result = case.run()
print(f"测试结果: {result.to_dict()}")

# 获取用例信息
case_data = case.get_data()
case_status = case.get_status()

# 删除用例
success = case.remove()
```

### 5. 测试结果 (TestResult)

```python
# 运行测试获取结果
result = case.run()

# 检查测试状态
if result.is_passed():
    print("✓ 测试通过")
elif result.is_failed():
    print(f"✗ 测试失败: {result.get_error()}")

# 获取详细信息
print(f"测试用例ID: {result.case_id}")
print(f"测试状态: {result.status}")
print(f"执行时间: {result.get_duration()}s")
print(f"开始时间: {result.start_time}")
print(f"结束时间: {result.end_time}")

# 转换为字典
result_dict = result.to_dict()
```

## 🔧 高级用法

### 数据库测试

```python
# 添加数据库对象
mysql_obj = env.add_object("mysql", "my_mysql", version="8.0")
mysql_obj.start()

# 数据库测试用例
db_test = env.add_case("mysql_connection", {
    "type": "database",
    "db_object": "my_mysql",
    "query": "SELECT COUNT(*) as user_count FROM users",
    "expected_result": {"user_count": 100}
})

# 运行数据库测试
result = db_test.run()
```

### API 测试

```python
# API 测试用例
api_test = env.add_case("api_user_list", {
    "type": "api",
    "method": "GET",
    "url": "https://jsonplaceholder.typicode.com/users",
    "headers": {"Content-Type": "application/json"},
    "expected_status": 200,
    "expected_response": {"count": 10},  # 可选的响应验证
    "timeout": 30
})

result = api_test.run()
```

### Web 测试

```python
# Web 测试用例
web_test = env.add_case("web_homepage", {
    "type": "web",
    "url": "https://example.com",
    "expected_title": "Example Domain",
    "expected_content": "This domain is for use in illustrative examples",
    "timeout": 10
})

result = web_test.run()
```

### 服务测试

```python
# 服务测试用例
service_test = env.add_case("web_service_check", {
    "type": "service",
    "host": "localhost",
    "port": 8080,
    "timeout": 5
})

result = service_test.run()
```

## 🎯 实际应用示例

### 完整的Web应用测试流程

```python
from ptest import TestFramework

def test_web_application():
    """完整的Web应用测试示例"""
    
    with TestFramework() as framework:
        # 创建测试环境
        env = framework.create_environment("./web_app_test")
        
        # 添加数据库
        with env.add_object("mysql", "app_db", version="8.0") as db:
            # 添加Web应用
            with env.add_object("web", "app_web") as web_app:
                
                # 数据库准备测试
                db_setup = env.add_case("db_setup", {
                    "type": "database",
                    "db_object": "app_db",
                    "query": """
                    CREATE TABLE IF NOT EXISTS users (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        name VARCHAR(100),
                        email VARCHAR(100)
                    )
                    """
                })
                
                # API接口测试
                api_test = env.add_case("api_users", {
                    "type": "api",
                    "method": "GET",
                    "url": "http://localhost:8080/api/users",
                    "expected_status": 200
                })
                
                # Web页面测试
                web_test = env.add_case("web_homepage", {
                    "type": "web",
                    "url": "http://localhost:8080/",
                    "expected_title": "My App"
                })
                
                # 服务连通性测试
                service_test = env.add_case("service_check", {
                    "type": "service",
                    "host": "localhost",
                    "port": 8080
                })
                
                # 运行所有测试
                results = env.run_all_cases()
                
                # 分析结果
                passed = sum(1 for r in results if r.is_passed())
                failed = sum(1 for r in results if r.is_failed())
                
                print(f"测试完成: {passed} 通过, {failed} 失败")
                
                # 生成报告
                report_path = framework.generate_report("html")
                print(f"详细报告: {report_path}")
                
                return all(r.is_passed() for r in results)

# 运行测试
if __name__ == "__main__":
    success = test_web_application()
    print(f"测试结果: {'全部通过' if success else '存在失败'}")
```

### 数据驱动的批量测试

```python
from ptest import TestFramework
import json

def data_driven_test():
    """数据驱动的批量测试示例"""
    
    # 测试数据
    test_cases = [
        {
            "id": "api_get_users",
            "type": "api",
            "method": "GET",
            "url": "https://jsonplaceholder.typicode.com/users",
            "expected_status": 200
        },
        {
            "id": "api_get_posts", 
            "type": "api",
            "method": "GET",
            "url": "https://jsonplaceholder.typicode.com/posts",
            "expected_status": 200
        },
        {
            "id": "api_create_user",
            "type": "api",
            "method": "POST",
            "url": "https://jsonplaceholder.typicode.com/users",
            "data": {"name": "Test User", "email": "test@example.com"},
            "expected_status": 201
        }
    ]
    
    with TestFramework() as framework:
        env = framework.create_environment("./api_tests")
        
        # 批量添加测试用例
        for test_case in test_cases:
            case_id = test_case.pop("id")
            env.add_case(case_id, test_case)
        
        # 运行所有测试
        results = env.run_all_cases()
        
        # 保存测试结果
        results_data = [r.to_dict() for r in results]
        with open("./test_results.json", "w") as f:
            json.dump(results_data, f, indent=2, default=str)
        
        return results

if __name__ == "__main__":
    results = data_driven_test()
    for result in results:
        print(f"{result.case_id}: {result.status}")
```

## 🔍 调试和故障排除

### 启用详细日志

```python
import logging

# 设置日志级别
logging.basicConfig(level=logging.DEBUG)

framework = TestFramework(config={
    "log_level": "DEBUG",
    "timeout": 60
})
```

### 错误处理

```python
from ptest import TestFramework

try:
    with TestFramework() as framework:
        env = framework.create_environment("./test")
        
        # 尝试添加不存在的对象类型
        obj = env.add_object("invalid_type", "test")
        
except ValueError as e:
    print(f"参数错误: {e}")
except Exception as e:
    print(f"执行错误: {e}")
```

### 检查对象状态

```python
# 检查对象状态
obj = env.add_object("mysql", "test_db")
status = obj.get_status()

if status["status"] == "running":
    print("对象正在运行")
elif status["installed"]:
    print("对象已安装但未运行")
else:
    print("对象未安装")
```

## 📚 更多资源

- [完整API文档](../api/README.md)
- [架构设计文档](../architecture/)
- [开发指南](../development/AGENTS.md)
- [测试用例示例](../../examples/test_cases.py)