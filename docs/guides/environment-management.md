# 环境管理指南

本文档描述当前 `1.4.0` 主线中的环境生命周期管理方式。这里的“环境”本质上是一个工作区和它对应的隔离上下文，而不是单纯的目录。

## 当前环境模型

环境管理围绕这几个动作展开：

1. 初始化工作区
2. 记录环境元数据
3. 附着或恢复隔离上下文
4. 承载对象、用例、执行记录和报告
5. 执行销毁和清理

当前主线通过 `WorkflowService` 和 CLI 共同完成这套流程。

## 当前支持的隔离级别

### `basic`

- 第一阶段默认隔离级别
- 适合本地快速开始和主线验证
- 工作区元数据、对象状态、执行记录都可落盘

### `virtualenv`

- 适合 Python 依赖隔离场景
- 依赖具体宿主机环境
- 当前文档只把它视为可选运行模式

### `docker`

- 适合更重的集成验证
- 本地真实 Docker 可用性受宿主机和网络影响
- 真实 Docker 校验以 CI 为准

## CLI 方式

### 初始化

```bash
uv run ptest init --path ./demo-workspace
```

### 查看状态

```bash
uv run ptest env status --path ./demo-workspace
uv run ptest --path ./demo-workspace status
```

### 销毁

```bash
uv run ptest env destroy --path ./demo-workspace
```

销毁会尝试做这些事：

- 停止并清理已记录的对象和工具
- 回收当前工作区对应的隔离环境
- 清空 `.ptest/artifacts/`
- 把环境状态标记为 `destroyed`

## Python API 方式

```python
from pathlib import Path

from ptest.api import PTestAPI

workspace = Path("./demo-workspace")
api = PTestAPI(work_path=workspace)

init_result = api.init_environment()
print(init_result["data"]["root_path"])

status = api.get_environment_status()
print(status["data"]["status"])

destroy_result = api.destroy_environment()
print(destroy_result["success"])
```

## 工作区结构

初始化后，工作区中最重要的目录和文件通常包括：

```text
demo-workspace/
├── .ptest/
│   ├── environment.json
│   ├── objects.json
│   ├── tools.json
│   ├── executions.json
│   └── artifacts/
├── cases/
├── reports/
└── logs/
```

其中：

- `.ptest/environment.json` 保存环境元数据
- `.ptest/artifacts/` 保存执行级 artifact 和索引
- `reports/` 保存报告输出
- `logs/` 保存工作区日志

## 环境恢复与状态语义

当前主线支持在重新进入同一工作区时恢复环境元数据，并尽量重新附着隔离上下文。

常见状态包括：

- `ready`: 工作区已初始化，可继续使用
- `destroyed`: 环境已销毁，需重新初始化
- `uninitialized`: 当前路径还不是工作区

对象和工具在恢复时也会带上恢复语义，例如：

- `rebuild_connector`
- `downgraded_nonrecoverable_runtime`
- `stale`

这些信息会体现在对象或 mock 的元数据中，用于帮助判断“是否真的恢复到了可运行状态”。

## 与执行记录的关系

环境不仅是运行上下文，也是执行产物的归属点。每次 case 执行后，主线会在：

```text
.ptest/artifacts/<execution_id>/
```

下保存：

- `context/environment.json`
- `context/objects.json`
- `case/case.json`
- `result/result.json`
- `result/execution.json`
- `indexes/artifact_index.json`
- `logs/log_index.json`

## 当前边界

- 当前文档以第一阶段 MVP 主线为准
- 更深的跨进程、多引擎恢复仍属于后续增强方向
- 本地真实 Docker 环境问题不应与主线功能问题混为一谈

## 相关文档

- 快速开始：[../user-guide/basic-usage.md](../user-guide/basic-usage.md)
- Python API：[../api/python-api-guide.md](../api/python-api-guide.md)
- 架构总览：[../architecture/system-overview.md](../architecture/system-overview.md)
# 获取所有已安装包
packages = env.get_installed_packages()
for name, version in packages.items():
    print(f"{name}: {version}")

# 获取特定包版本
version = env.get_package_version("requests")
print(f"requests版本: {version}")

# 检查包是否安装
is_installed = env.is_package_installed("requests")
print(f"requests已安装: {is_installed}")
```

### 包卸载

```python
# 卸载单个包
success = env.uninstall_package("requests")

# 卸载多个包
for package in ["requests", "pandas"]:
    env.uninstall_package(package)

# 清理未使用的包
env.cleanup_unused_packages()
```

## 🌐 网络管理

### 端口管理

```python
# 分配端口范围
env.configure_port_range(start_port=20000, end_port=21000)

# 分配单个端口
port1 = env.allocate_port()
port2 = env.allocate_port()

# 检查端口可用性
is_available = env.is_port_available(8080)

# 释放端口
env.release_port(port1)
env.release_port(port2)
```

### 网络隔离

```python
# 配置网络隔离
env.configure_network_isolation(
    enabled=True,
    allowed_hosts=["localhost", "127.0.0.1"],
    blocked_ports=[22, 3389],
    firewall_rules=[
        {"action": "allow", "port": 8080, "protocol": "tcp"},
        {"action": "deny", "port": 22, "protocol": "tcp"}
    ]
)

# 测试网络连接
result = env.execute_in_isolation(["curl", "http://example.com"])
if result.returncode != 0:
    print("网络访问被阻止")
```

## 🔒 安全配置

### 权限控制

```python
# 配置文件权限
env.configure_file_permissions({
    "/logs": "read_write",
    "/data": "read_write", 
    "/bin": "read_only",
    "/lib": "read_only"
})

# 配置执行权限
env.configure_execute_permissions({
    "allow_python": True,
    "allow_shell": False,
    "allow_network": True,
    "allow_file_access": "restricted"
})
```

### 资源限制

```python
# 设置CPU限制
env.set_cpu_limit(cores=2, percentage=80.0)

# 设置内存限制
env.set_memory_limit(hard_limit="2g", soft_limit="1.5g")

# 设置磁盘限制
env.set_disk_limit(max_size="10g", max_files=1000)

# 设置进程限制
env.set_process_limit(max_processes=50, max_threads=200)
```

## 📊 监控和日志

### 环境监控

```python
# 启用监控
env.enable_monitoring(
    cpu_usage=True,
    memory_usage=True,
    disk_usage=True,
    network_usage=True,
    interval=5  # 5秒采样间隔
)

# 获取监控数据
monitoring_data = env.get_monitoring_data()
print(f"平均CPU使用率: {monitoring_data['cpu']['average']:.2f}%")
print(f"平均内存使用: {monitoring_data['memory']['average']:.2f}MB")

# 获取监控报告
report = env.generate_monitoring_report(format="json")
```

### 日志管理

```python
# 配置日志
env.configure_logging(
    level="INFO",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=["file", "console"],
    max_file_size="10MB",
    backup_count=5
)

# 获取日志
logs = env.get_logs(level="ERROR", lines=100)
for log in logs:
    print(log)

# 导出日志
env.export_logs("/path/to/logs.tar.gz")
```

## 🔄 环境模板

### 创建模板

```python
# 从现有环境创建模板
template_id = env.create_template(
    name="python_web_template",
    description="Python Web应用测试模板",
    include_packages=True,
    include_config=True,
    include_objects=False
)

# 手动创建模板
template = framework.create_environment_template(
    name="database_template",
    isolation="virtualenv",
    packages=["mysql-connector-python==8.0.0", "pytest==7.0.0"],
    config={
        "python_version": "3.9",
        "resource_limits": {
            "memory_mb": 1024
        }
    },
    objects=[
        {"type": "mysql", "name": "test_db", "version": "8.0"}
    ]
)
```

### 使用模板

```python
# 从模板创建环境
env = framework.create_environment_from_template(
    template_id="python_web_template",
    path="./web_test_env",
    custom_config={
        "resource_limits": {
            "memory_mb": 2048
        }
    }
)

# 列出可用模板
templates = framework.list_environment_templates()
for template in templates:
    print(f"{template['name']}: {template['description']}")
```

## 🚀 性能优化

### 环境复用

```python
# 启用环境复用
framework.enable_environment_reuse(max_reuse_count=5)

# 创建可复用环境
env = framework.create_reusable_environment(
    path="./reusable_env",
    isolation="virtualenv",
    reuse_key="python_base"
)

# 清理复用环境
framework.cleanup_reusable_environments(older_than_days=7)
```

### 预热机制

```python
# 预热常用环境类型
framework.prewarm_environments([
    {"isolation": "virtualenv", "packages": ["requests", "pytest"]},
    {"isolation": "virtualenv", "packages": ["pandas", "numpy"]},
    {"isolation": "docker", "image": "python:3.9-slim"}
])

# 获取预热环境状态
prewarm_status = framework.get_prewarm_status()
```

### 缓存策略

```python
# 配置缓存策略
framework.configure_cache({
    "package_cache": {
        "enabled": True,
        "max_size": "1GB",
        "ttl": "7d"
    },
    "image_cache": {
        "enabled": True,
        "max_count": 10,
        "cleanup_policy": "lru"
    }
})
```

## 🛠️ 故障排除

### 常见问题

#### 环境创建失败
```bash
# 检查磁盘空间
df -h

# 检查权限
ls -la /path/to/env

# 检查Python环境
python --version
which python
```

#### Virtualenv创建失败
```python
# 诊断virtualenv问题
import venv
import sys

print(f"Python版本: {sys.version}")
print(f"venv模块可用: {hasattr(venv, 'EnvBuilder')}")

# 尝试手动创建
try:
    venv.EnvBuilder(with_pip=True).create("/tmp/test_venv")
    print("Virtualenv创建成功")
except Exception as e:
    print(f"Virtualenv创建失败: {e}")
```

#### Docker环境问题
```bash
# 检查Docker状态
docker --version
docker info

# 检查镜像
docker images python:3.9-slim

# 清理Docker资源
docker system prune -f
```

### 调试技巧

#### 启用详细日志
```python
import logging

# 启用ptest调试日志
logging.getLogger("ptest").setLevel(logging.DEBUG)

# 启用环境调试日志
env.enable_debug_logging()

# 查看环境创建日志
creation_logs = env.get_creation_logs()
print(creation_logs)
```

#### 环境验证
```python
# 验证环境完整性
validation_result = env.validate_environment()
if not validation_result.is_valid:
    print(f"环境验证失败: {validation_result.errors}")
    for error in validation_result.errors:
        print(f"  - {error}")

# 修复环境问题
if not validation_result.is_valid:
    repair_result = env.repair_environment()
    print(f"修复结果: {repair_result.success}")
```

## 📚 最佳实践

### 环境命名
```python
# 使用描述性的环境名称
env_names = [
    "api_test_env_v1",           # API测试环境v1
    "db_integration_mysql80",     # MySQL 8.0集成测试
    "web_e2e_chrome_latest",    # 最新Chrome的E2E测试
    "performance_load_test_10x"  # 10倍负载的性能测试
]
```

### 资源管理
```python
# 根据测试类型配置合适的资源
test_configs = {
    "unit_test": {
        "isolation": "basic",
        "resource_limits": {"memory_mb": 256, "max_processes": 10}
    },
    "integration_test": {
        "isolation": "virtualenv", 
        "resource_limits": {"memory_mb": 512, "max_processes": 25}
    },
    "e2e_test": {
        "isolation": "docker",
        "resource_limits": {"memory_mb": 1024, "max_processes": 50}
    }
}
```

### 清理策略
```python
# 自动清理策略
framework.configure_auto_cleanup({
    "enabled": True,
    "idle_timeout": 3600,        # 1小时未使用自动清理
    "max_age_days": 7,          # 7天后强制清理
    "cleanup_policy": "soft"     # 软清理，保留重要环境
})
```

---

## 🔗 相关文档

- [系统架构总览](../architecture/system-overview.md)
- [环境隔离架构](../architecture/ISOLATION_ARCHITECTURE.md)
- [API 文档入口](../api/README.md)
- [专题指南入口](README.md)
- [用户文档入口](../user-guide/README.md)

---

**文档版本**: 1.0  
**最后更新**: 2026-01-25  
**维护者**: cp
