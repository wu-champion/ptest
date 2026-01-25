# ptest API 使用示例

## 📚 示例概述

本文档提供了 ptest Python API 的详细使用示例，涵盖从基础操作到高级功能的完整场景。

## 🚀 基础示例

### 示例1: 简单的API测试

```python
from ptest import TestFramework

# 创建框架实例
framework = TestFramework()

# 创建测试环境
env = framework.create_environment("./api_test", isolation="virtualenv")

# 添加API测试用例
env.add_case("jsonplaceholder_test", {
    "type": "api",
    "method": "GET",
    "url": "https://jsonplaceholder.typicode.com/users/1",
    "expected_status": 200,
    "assertions": [
        {"type": "json_path", "path": "$.name", "operator": "exists"},
        {"type": "json_path", "path": "$.email", "operator": "contains", "value": "@"}
    ]
})

# 运行测试
result = env.run_case("jsonplaceholder_test")

# 检查结果
if result.is_passed():
    print("✅ API测试通过")
    print(f"响应时间: {result.get_duration():.2f}秒")
else:
    print("❌ API测试失败")
    print(f"错误信息: {result.get_error()}")

# 生成报告
report = env.generate_report("html")
print(f"📊 报告已生成: {report}")

# 清理资源
framework.cleanup()
```

### 示例2: 数据库集成测试

```python
from ptest import TestFramework

framework = TestFramework()
env = framework.create_environment("./db_test", isolation="virtualenv")

# 安装数据库连接包
env.install_package("mysql-connector-python==8.0.0")

# 添加MySQL数据库对象
mysql = env.add_object("mysql", "test_db", 
                         version="8.0",
                         port=3306,
                         user="test_user",
                         password="test_pass",
                         database="test_db")

# 启动数据库
mysql.start()

# 等待数据库启动
import time
time.sleep(5)

# 添加数据库测试用例
env.add_case("mysql_connection_test", {
    "type": "database",
    "object": "test_db",
    "setup": [
        "CREATE TABLE test_users (id INT PRIMARY KEY, name VARCHAR(50), email VARCHAR(100))"
    ],
    "tests": [
        {
            "query": "INSERT INTO test_users (id, name, email) VALUES (1, 'John Doe', 'john@example.com')",
            "expected_affected_rows": 1
        },
        {
            "query": "SELECT * FROM test_users WHERE id = 1",
            "expected_results": [{"id": 1, "name": "John Doe", "email": "john@example.com"}]
        }
    ],
    "cleanup": [
        "DROP TABLE test_users"
    ]
})

# 运行测试
result = env.run_case("mysql_connection_test")
print(f"数据库测试结果: {'通过' if result.is_passed() else '失败'}")

# 停止数据库
mysql.stop()

framework.cleanup()
```

## 🔧 中级示例

### 示例3: 多环境并发测试

```python
from ptest import TestFramework
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import shutil

def run_test_in_environment(env_name, test_config):
    """在独立环境中运行测试"""
    framework = TestFramework()
    
    try:
        # 创建临时环境
        temp_dir = tempfile.mkdtemp(prefix=f"ptest_{env_name}_")
        env = framework.create_environment(temp_dir, isolation="virtualenv")
        
        # 安装依赖包
        if "packages" in test_config:
            for package in test_config["packages"]:
                env.install_package(package)
        
        # 添加测试用例
        env.add_case(f"{env_name}_test", test_config["test_case"])
        
        # 运行测试
        result = env.run_case(f"{env_name}_test")
        
        return {
            "env_name": env_name,
            "success": result.is_passed(),
            "duration": result.get_duration(),
            "error": result.get_error() if not result.is_passed() else None
        }
        
    except Exception as e:
        return {
            "env_name": env_name,
            "success": False,
            "duration": 0,
            "error": str(e)
        }
    finally:
        # 清理资源
        if 'framework' in locals():
            framework.cleanup()
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

# 定义测试配置
test_configs = {
    "api_test": {
        "packages": ["requests==2.28.0"],
        "test_case": {
            "type": "api",
            "method": "GET",
            "url": "https://jsonplaceholder.typicode.com/users/1",
            "expected_status": 200
        }
    },
    "math_test": {
        "packages": ["numpy==1.24.0"],
        "test_case": {
            "type": "python",
            "code": "import numpy as np; result = np.array([1, 2, 3]).sum(); assert result == 6"
        }
    },
    "web_test": {
        "packages": ["flask==2.2.0"],
        "test_case": {
            "type": "web",
            "setup": "from flask import Flask; app = Flask(__name__)",
            "test": "with app.test_client() as client: response = client.get('/'); assert response.status_code == 200"
        }
    }
}

# 并发运行测试
with ThreadPoolExecutor(max_workers=3) as executor:
    # 提交所有测试任务
    futures = {
        executor.submit(run_test_in_environment, env_name, config): env_name
        for env_name, config in test_configs.items()
    }
    
    # 收集结果
    results = []
    for future in as_completed(futures):
        env_name = futures[future]
        try:
            result = future.result()
            results.append(result)
            status = "✅" if result["success"] else "❌"
            print(f"{status} {env_name}: {result['duration']:.2f}s")
            if not result["success"]:
                print(f"   错误: {result['error']}")
        except Exception as e:
            print(f"❌ {env_name}: 执行失败 - {e}")

# 统计结果
success_count = sum(1 for r in results if r["success"])
total_count = len(results)
avg_duration = sum(r["duration"] for r in results) / total_count

print(f"\n📊 测试统计:")
print(f"   总数: {total_count}")
print(f"   成功: {success_count}")
print(f"   失败: {total_count - success_count}")
print(f"   成功率: {success_count/total_count*100:.1f}%")
print(f"   平均耗时: {avg_duration:.2f}s")
```

### 示例4: 微服务集成测试

```python
from ptest import TestFramework
import time

framework = TestFramework()
env = framework.create_environment("./microservice_test", isolation="docker")

# 微服务配置
services = {
    "user_service": {
        "type": "web",
        "url": "http://localhost:8001",
        "port": 8001,
        "health_check": "/health"
    },
    "order_service": {
        "type": "web", 
        "url": "http://localhost:8002",
        "port": 8002,
        "health_check": "/health"
    },
    "payment_service": {
        "type": "web",
        "url": "http://localhost:8003", 
        "port": 8003,
        "health_check": "/health"
    }
}

# 启动所有服务
service_objects = {}
for service_name, config in services.items():
    service_obj = env.add_object("web", service_name, **config)
    service_obj.start()
    service_objects[service_name] = service_obj

# 等待服务启动
print("⏳ 等待服务启动...")
time.sleep(10)

# 健康检查
all_healthy = True
for service_name, service_obj in service_objects.items():
    is_healthy = service_obj.health_check()
    status = "✅" if is_healthy else "❌"
    print(f"{status} {service_name}: {'健康' if is_healthy else '不健康'}")
    if not is_healthy:
        all_healthy = False

if all_healthy:
    # 创建集成测试用例
    env.add_case("user_order_payment_flow", {
        "type": "integration",
        "description": "用户-订单-支付流程测试",
        "steps": [
            {
                "service": "user_service",
                "method": "POST",
                "path": "/users",
                "data": {"name": "John Doe", "email": "john@example.com"},
                "expected_status": 201,
                "extract": {"user_id": "$.id"}
            },
            {
                "service": "order_service", 
                "method": "POST",
                "path": "/orders",
                "data": {"user_id": "${user_id}", "items": [{"product_id": 1, "quantity": 2}]},
                "expected_status": 201,
                "extract": {"order_id": "$.id"}
            },
            {
                "service": "payment_service",
                "method": "POST", 
                "path": "/payments",
                "data": {"order_id": "${order_id}", "amount": 100.0, "method": "credit_card"},
                "expected_status": 200
            }
        ],
        "assertions": [
            {"step": 1, "status_code": 201},
            {"step": 2, "status_code": 201},
            {"step": 3, "status_code": 200}
        ]
    })
    
    # 运行集成测试
    result = env.run_case("user_order_payment_flow")
    
    if result.is_passed():
        print("✅ 微服务集成测试通过")
    else:
        print("❌ 微服务集成测试失败")
        print(f"错误: {result.get_error()}")
    
    # 生成详细的集成测试报告
    report = env.generate_report("html")
    print(f"📊 集成测试报告: {report}")
else:
    print("❌ 服务健康检查失败，跳过集成测试")

# 停止所有服务
for service_name, service_obj in service_objects.items():
    service_obj.stop()
    print(f"🛑 已停止 {service_name}")

framework.cleanup()
```

## 🚀 高级示例

### 示例5: 性能基准测试

```python
from ptest import TestFramework
import time
import statistics
from concurrent.futures import ThreadPoolExecutor

class PerformanceBenchmark:
    def __init__(self, framework, env):
        self.framework = framework
        self.env = env
        self.results = []
    
    def run_load_test(self, test_case, concurrent_users=10, duration=30):
        """运行负载测试"""
        print(f"🚀 开始负载测试: {concurrent_users} 并发用户, {duration}秒")
        
        def single_user_test():
            """单个用户测试"""
            start_time = time.time()
            result = self.env.run_case("load_test_case")
            end_time = time.time()
            
            return {
                "success": result.is_passed(),
                "duration": end_time - start_time,
                "timestamp": start_time
            }
        
        # 添加负载测试用例
        self.env.add_case("load_test_case", test_case)
        
        # 执行负载测试
        start_time = time.time()
        end_time = start_time + duration
        
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = []
            
            while time.time() < end_time:
                # 提交测试任务
                future = executor.submit(single_user_test)
                futures.append(future)
                
                # 控制提交频率
                time.sleep(0.1)
            
            # 收集结果
            for future in futures:
                try:
                    result = future.result()
                    self.results.append(result)
                except Exception as e:
                    print(f"测试执行失败: {e}")
        
        return self.analyze_results()
    
    def analyze_results(self):
        """分析测试结果"""
        if not self.results:
            return {"error": "没有测试结果"}
        
        successful_results = [r for r in self.results if r["success"]]
        durations = [r["duration"] for r in successful_results]
        
        if not durations:
            return {"error": "没有成功的测试结果"}
        
        analysis = {
            "total_requests": len(self.results),
            "successful_requests": len(successful_results),
            "success_rate": len(successful_results) / len(self.results) * 100,
            "avg_response_time": statistics.mean(durations),
            "min_response_time": min(durations),
            "max_response_time": max(durations),
            "median_response_time": statistics.median(durations),
            "p95_response_time": self.percentile(durations, 95),
            "p99_response_time": self.percentile(durations, 99),
            "requests_per_second": len(successful_results) / (max(r["timestamp"] for r in self.results) - min(r["timestamp"] for r in self.results))
        }
        
        return analysis
    
    @staticmethod
    def percentile(data, percentile):
        """计算百分位数"""
        sorted_data = sorted(data)
        index = (percentile / 100) * len(sorted_data)
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))

# 使用示例
framework = TestFramework()
env = framework.create_environment("./performance_test", isolation="virtualenv")

# 安装性能测试依赖
env.install_package("requests==2.28.0")
env.install_package("locust==2.15.0")

# 定义API测试用例
api_test_case = {
    "type": "api",
    "method": "GET",
    "url": "https://jsonplaceholder.typicode.com/users",
    "expected_status": 200,
    "timeout": 10
}

# 运行性能基准测试
benchmark = PerformanceBenchmark(framework, env)
results = benchmark.run_load_test(api_test_case, concurrent_users=5, duration=15)

# 输出结果
print("📊 性能测试结果:")
print(f"   总请求数: {results['total_requests']}")
print(f"   成功请求数: {results['successful_requests']}")
print(f"   成功率: {results['success_rate']:.2f}%")
print(f"   平均响应时间: {results['avg_response_time']:.3f}s")
print(f"   最小响应时间: {results['min_response_time']:.3f}s")
print(f"   最大响应时间: {results['max_response_time']:.3f}s")
print(f"   95%响应时间: {results['p95_response_time']:.3f}s")
print(f"   99%响应时间: {results['p99_response_time']:.3f}s")
print(f"   RPS: {results['requests_per_second']:.2f}")

framework.cleanup()
```

### 示例6: 自定义测试框架扩展

```python
from ptest import TestFramework, TestEnvironment, TestResult
from ptest.isolation import IsolationEngine, IsolatedEnvironment
import json
import time

class CustomTestEnvironment(TestEnvironment):
    """自定义测试环境，添加额外功能"""
    
    def __init__(self, path, isolation="basic", framework=None):
        super().__init__(path, isolation, framework)
        self.custom_data = {}
        self.start_time = None
        self.end_time = None
    
    def start_timing(self):
        """开始计时"""
        self.start_time = time.time()
    
    def end_timing(self):
        """结束计时"""
        self.end_time = time.time()
    
    def get_duration(self):
        """获取执行时长"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0
    
    def set_custom_data(self, key, value):
        """设置自定义数据"""
        self.custom_data[key] = value
    
    def get_custom_data(self, key):
        """获取自定义数据"""
        return self.custom_data.get(key)
    
    def export_metrics(self):
        """导出测试指标"""
        return {
            "duration": self.get_duration(),
            "custom_data": self.custom_data,
            "environment_info": self.get_status()
        }

class CustomTestFramework(TestFramework):
    """自定义测试框架，扩展基础功能"""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.test_metrics = []
        self.global_hooks = {
            "before_test": [],
            "after_test": [],
            "before_suite": [],
            "after_suite": []
        }
    
    def add_hook(self, event, callback):
        """添加钩子函数"""
        if event in self.global_hooks:
            self.global_hooks[event].append(callback)
    
    def run_hooks(self, event, *args, **kwargs):
        """执行钩子函数"""
        for hook in self.global_hooks.get(event, []):
            try:
                hook(*args, **kwargs)
            except Exception as e:
                print(f"钩子执行失败 ({event}): {e}")
    
    def create_custom_environment(self, path, isolation="basic"):
        """创建自定义测试环境"""
        env = CustomTestEnvironment(path, isolation, self)
        self.environments[path] = env
        return env
    
    def run_test_suite(self, test_configs):
        """运行测试套件"""
        self.run_hooks("before_suite")
        
        suite_results = []
        suite_start_time = time.time()
        
        for test_config in test_configs:
            self.run_hooks("before_test", test_config)
            
            try:
                # 创建测试环境
                env = self.create_custom_environment(
                    f"./test_{test_config['name']}", 
                    test_config.get("isolation", "basic")
                )
                
                # 开始计时
                env.start_timing()
                
                # 设置自定义数据
                env.set_custom_data("test_name", test_config["name"])
                env.set_custom_data("test_config", test_config)
                
                # 执行测试
                if test_config["type"] == "api":
                    result = self._run_api_test(env, test_config)
                elif test_config["type"] == "database":
                    result = self._run_database_test(env, test_config)
                else:
                    result = self._run_generic_test(env, test_config)
                
                # 结束计时
                env.end_timing()
                
                # 收集指标
                metrics = env.export_metrics()
                self.test_metrics.append(metrics)
                
                suite_results.append({
                    "test_name": test_config["name"],
                    "success": result.is_passed(),
                    "duration": metrics["duration"],
                    "metrics": metrics
                })
                
            except Exception as e:
                suite_results.append({
                    "test_name": test_config["name"],
                    "success": False,
                    "duration": 0,
                    "error": str(e)
                })
            
            finally:
                self.run_hooks("after_test", test_config)
        
        suite_end_time = time.time()
        suite_duration = suite_end_time - suite_start_time
        
        self.run_hooks("after_suite")
        
        return {
            "results": suite_results,
            "duration": suite_duration,
            "metrics": {
                "total_tests": len(test_configs),
                "passed_tests": sum(1 for r in suite_results if r["success"]),
                "failed_tests": sum(1 for r in suite_results if not r["success"]),
                "success_rate": sum(1 for r in suite_results if r["success"]) / len(suite_results) * 100
            }
        }
    
    def _run_api_test(self, env, config):
        """运行API测试"""
        env.add_case("api_test", config["test_case"])
        return env.run_case("api_test")
    
    def _run_database_test(self, env, config):
        """运行数据库测试"""
        env.add_case("db_test", config["test_case"])
        return env.run_case("db_test")
    
    def _run_generic_test(self, env, config):
        """运行通用测试"""
        env.add_case("generic_test", config["test_case"])
        return env.run_case("generic_test")
    
    def generate_custom_report(self, results, format="json"):
        """生成自定义报告"""
        if format == "json":
            return json.dumps(results, indent=2)
        elif format == "html":
            return self._generate_html_report(results)
        else:
            return str(results)
    
    def _generate_html_report(self, results):
        """生成HTML报告"""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>ptest 自定义报告</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { background: #f0f0f0; padding: 20px; border-radius: 5px; }
                .test-result { margin: 10px 0; padding: 10px; border-left: 4px solid #ccc; }
                .success { border-left-color: #4CAF50; }
                .failure { border-left-color: #f44336; }
                .metrics { background: #f9f9f9; padding: 10px; margin: 10px 0; border-radius: 3px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>ptest 测试报告</h1>
                <p>总测试数: {total_tests}</p>
                <p>通过数: {passed_tests}</p>
                <p>失败数: {failed_tests}</p>
                <p>成功率: {success_rate:.1f}%</p>
                <p>总耗时: {duration:.2f}秒</p>
            </div>
        """.format(**results["metrics"])
        
        for result in results["results"]:
            css_class = "success" if result["success"] else "failure"
            html += f"""
            <div class="test-result {css_class}">
                <h3>{result['test_name']}</h3>
                <p>状态: {'通过' if result['success'] else '失败'}</p>
                <p>耗时: {result['duration']:.3f}秒</p>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        return html

# 使用示例
def before_test_hook(test_config):
    print(f"🚀 开始测试: {test_config['name']}")

def after_test_hook(test_config):
    print(f"✅ 测试完成: {test_config['name']}")

# 创建自定义框架
framework = CustomTestFramework()

# 添加钩子
framework.add_hook("before_test", before_test_hook)
framework.add_hook("after_test", after_test_hook)

# 定义测试配置
test_configs = [
    {
        "name": "api_test_1",
        "type": "api",
        "isolation": "virtualenv",
        "test_case": {
            "type": "api",
            "method": "GET",
            "url": "https://jsonplaceholder.typicode.com/users/1",
            "expected_status": 200
        }
    },
    {
        "name": "api_test_2", 
        "type": "api",
        "isolation": "basic",
        "test_case": {
            "type": "api",
            "method": "GET",
            "url": "https://jsonplaceholder.typicode.com/posts/1",
            "expected_status": 200
        }
    }
]

# 运行测试套件
results = framework.run_test_suite(test_configs)

# 生成自定义报告
json_report = framework.generate_custom_report(results, "json")
html_report = framework.generate_custom_report(results, "html")

# 保存报告
with open("custom_report.json", "w") as f:
    f.write(json_report)

with open("custom_report.html", "w") as f:
    f.write(html_report)

print("📊 自定义报告已生成:")
print(f"   JSON: custom_report.json")
print(f"   HTML: custom_report.html")

framework.cleanup()
```

## 📋 最佳实践

### 1. 资源管理
```python
# 使用上下文管理器确保资源清理
with TestFramework() as framework:
    env = framework.create_environment("./test")
    # 测试代码
# 自动清理
```

### 2. 错误处理
```python
try:
    result = env.run_case("test")
    if result.is_passed():
        print("测试通过")
    else:
        print(f"测试失败: {result.get_error()}")
except Exception as e:
    print(f"测试执行异常: {e}")
```

### 3. 配置管理
```python
# 使用配置文件
import json

with open("test_config.json", "r") as f:
    config = json.load(f)

framework = TestFramework(config)
```

### 4. 日志记录
```python
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ptest")

# 在测试中使用日志
logger.info("开始测试执行")
```

---

## 🔗 相关文档

- [Python API 参考](python-api.md)
- [环境管理指南](../guides/environment-management.md)
- [测试用例编写](../guides/test-case-writing.md)
- [对象管理指南](../guides/object-management.md)

---

**示例版本**: 1.0  
**最后更新**: 2026-01-25  
**维护者**: cp