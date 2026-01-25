# ptest 快速开始指南

## 🚀 概述

ptest 是一个企业级的综合测试框架，提供完整的环境隔离、对象管理和测试执行能力。本指南将帮助您快速上手 ptest 的基本功能。

## 📋 系统要求

### 基础要求
- **Python**: 3.8+
- **操作系统**: Linux, macOS, Windows
- **内存**: 最少 4GB RAM(待后续详细计算)
- **磁盘空间**: 最少 10GB 可用空间

### 可选依赖
- **Docker**: 用于容器隔离 (推荐)
- **Git**: 用于版本控制集成

## 🔧 安装方式

### 方式一：直接安装
```bash
# 克隆项目
git clone https://github.com/your-org/ptest.git
cd ptest

# 安装依赖
pip install -r requirements.txt

# 安装框架
pip install -e .
```

### 方式二：开发环境安装
```bash
# 克隆项目
git clone https://github.com/your-org/ptest.git
cd ptest

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\\Scripts\\activate  # Windows

# 安装开发依赖
pip install -r requirements-dev.txt
pip install -e .
```

## 🎯 第一个测试

### 1. 初始化测试环境

```bash
# 使用默认配置创建测试环境
ptest init --path ./my_test_env

# 或使用自定义隔离级别
ptest init --path ./my_test_env --isolation virtualenv
```

### 2. 创建数据库对象

```python
# Python API 方式
from ptest import TestFramework

# 创建框架实例
framework = TestFramework()

# 创建测试环境
env = framework.create_environment("./my_test_env", isolation="virtualenv")

# 添加 MySQL 数据库
mysql_db = env.add_object("mysql", "test_mysql", 
                         version="8.0", 
                         port=3306,
                         user="test_user",
                         password="test_pass")

# 启动数据库
mysql_db.start()
```

### 3. 添加测试用例

```python
# 创建 API 测试用例
api_test = env.add_case("user_api_test", {
    "type": "api",
    "method": "GET",
    "url": "https://jsonplaceholder.typicode.com/users/1",
    "expected_status": 200,
    "assertions": [
        {"type": "json_path", "path": "$.name", "operator": "exists"},
        {"type": "json_path", "path": "$.email", "operator": "contains", "value": "@"}
    ]
})

# 创建数据库测试用例
db_test = env.add_case("mysql_connection_test", {
    "type": "database",
    "object": "test_mysql",
    "query": "SELECT 1 as test_value",
    "expected_results": [{"test_value": 1}]
})
```

### 4. 执行测试

```python
# 执行单个测试用例
result1 = env.run_case("user_api_test")
result2 = env.run_case("mysql_connection_test")

# 执行所有测试用例
results = env.run_all_cases()

# 检查结果
for case_id, result in results.items():
    print(f"测试 {case_id}: {'通过' if result.is_passed() else '失败'}")
```

### 5. 生成测试报告

```python
# 生成 HTML 报告
html_report = env.generate_report("html")
print(f"HTML 报告: {html_report}")

# 生成 JSON 报告
json_report = env.generate_report("json")
print(f"JSON 报告: {json_report}")

# 生成 PDF 报告（需要额外依赖）
pdf_report = env.generate_report("pdf")
print(f"PDF 报告: {pdf_report}")
```

## 💻 CLI 使用示例

### 环境管理

```bash
# 创建新环境
ptest env create --path ./test_env --isolation virtualenv

# 列出所有环境
ptest env list

# 获取环境状态
ptest env status --path ./test_env

# 清理环境
ptest env cleanup --path ./test_env
```

### 对象管理

```bash
# 安装数据库
ptest obj install mysql mydb --version 8.0 --port 3306

# 安装 Web 服务
ptest obj install web myapp --port 8080 --url http://localhost:8080

# 启动对象
ptest obj start mydb

# 停止对象
ptest obj stop mydb

# 查看对象状态
ptest obj status mydb
```

### 测试管理

```bash
# 添加测试用例
ptest case add api_test '{"type": "api", "url": "http://example.com/api"}'

# 运行单个测试
ptest case run api_test

# 运行所有测试
ptest case run all

# 查看测试结果
ptest case results
```

### 报告生成

```bash
# 生成 HTML 报告
ptest report --format html --output ./report.html

# 生成 JSON 报告
ptest report --format json --output ./report.json

# 生成趋势报告（需要历史数据）
ptest report --trend --days 7
```

## 🔧 配置管理

### 配置文件结构

```json
{
  "default_isolation_level": "virtualenv",
  "max_environments": 10,
  "log_level": "INFO",
  "report_format": "html",
  "isolation": {
    "virtualenv": {
      "base_packages": ["setuptools", "wheel", "pip"],
      "clear_cache": true,
      "system_site_packages": false
    },
    "docker": {
      "default_image": "python:3.9-slim",
      "default_resource_limits": {
        "memory_limit": "512m",
        "cpu_limit": 1.0
      }
    }
  },
  "network": {
    "default_port_range": "20000-21000",
    "network_isolation": true
  }
}
```

### 环境变量配置

```bash
# 设置配置文件路径
export PTEST_CONFIG_FILE=/path/to/config.json

# 设置日志级别
export PTEST_LOG_LEVEL=DEBUG

# 设置默认隔离级别
export PTEST_DEFAULT_ISOLATION=docker
```

## 🎯 常见使用场景

### 场景1: API 测试

```python
from ptest import TestFramework

framework = TestFramework()
env = framework.create_environment("./api_test", isolation="virtualenv")

# 添加多个 API 测试
tests = [
    ("users_list", {"url": "/api/users", "method": "GET"}),
    ("create_user", {"url": "/api/users", "method": "POST", "data": {"name": "test"}}),
    ("update_user", {"url": "/api/users/1", "method": "PUT", "data": {"name": "updated"}}),
    ("delete_user", {"url": "/api/users/1", "method": "DELETE"})
]

for test_name, test_config in tests:
    env.add_case(test_name, test_config)

# 执行所有测试
results = env.run_all_cases()
```

### 场景2: 数据库集成测试

```python
framework = TestFramework()
env = framework.create_environment("./db_test", isolation="virtualenv")

# 设置数据库
mysql = env.add_object("mysql", "test_db", version="8.0")
mysql.start()

# 添加数据库测试
env.add_case("db_connection", {
    "type": "database",
    "object": "test_db",
    "query": "SELECT VERSION()",
    "expected_results": [{"VERSION": lambda x: "8." in x}]
})

env.add_case("db_operations", {
    "type": "database",
    "object": "test_db",
    "setup": ["CREATE TABLE test_table (id INT, name VARCHAR(50))"],
    "tests": [
        {"query": "INSERT INTO test_table VALUES (1, 'test')"},
        {"query": "SELECT * FROM test_table WHERE id = 1", "expected": [{"id": 1, "name": "test"}]}
    ],
    "cleanup": ["DROP TABLE test_table"]
})
```

### 场景3: 微服务测试

```python
framework = TestFramework()
env = framework.create_environment("./microservice_test", isolation="docker")

# 添加多个服务
user_service = env.add_object("web", "user-service", port=8001, url="http://localhost:8001")
order_service = env.add_object("web", "order-service", port=8002, url="http://localhost:8002")
payment_service = env.add_object("web", "payment-service", port=8003, url="http://localhost:8003")

# 启动所有服务
user_service.start()
order_service.start()
payment_service.start()

# 添加集成测试
env.add_case("user_order_flow", {
    "type": "integration",
    "steps": [
        {"service": "user-service", "method": "POST", "path": "/users", "data": {"name": "test"}},
        {"service": "order-service", "method": "POST", "path": "/orders", "data": {"user_id": 1, "items": []}},
        {"service": "payment-service", "method": "POST", "path": "/payments", "data": {"order_id": 1, "amount": 100}}
    ],
    "assertions": [
        {"step": 1, "status_code": 201},
        {"step": 2, "status_code": 201},
        {"step": 3, "status_code": 200}
    ]
})
```

## 🔍 故障排除

### 常见问题

1. **环境创建失败**
   ```bash
   # 检查磁盘空间
   df -h
   
   # 检查权限
   ls -la /path/to/env
   
   # 检查 Python 版本
   python --version
   ```

2. **端口冲突**
   ```bash
   # 查看端口占用
   netstat -tulpn | grep <port>
   
   # 杀死占用进程
   kill -9 <pid>
   ```

3. **依赖包问题**
   ```bash
   # 重新安装依赖
   pip install -r requirements.txt
   
   # 清理缓存
   pip cache purge
   ```

### 调试模式

```bash
# 启用调试日志
export PTEST_LOG_LEVEL=DEBUG

# 或在代码中设置
import logging
logging.getLogger("ptest").setLevel(logging.DEBUG)
```

## 📚 下一步

- [基础使用教程](basic-usage.md) - 深入学习基础功能
- [高级功能指南](advanced-features.md) - 探索高级特性
- [环境管理指南](../guides/environment-management.md) - 环境管理详细说明
- [API 参考](../api/python-api.md) - 完整的 API 文档
- [常见问题解答](faq.md) - 更多问题解决方案

---

**需要帮助？** 
- 查看 [FAQ](faq.md)
- 提交 [Issue](https://github.com/wu_champion/ptest/issues)
- 加入讨论社区