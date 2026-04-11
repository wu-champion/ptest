# Virtualenv 隔离引擎参考

本文档面向开发者，说明 `VirtualenvIsolationEngine` 这一类底层隔离引擎的当前可用能力。

它不是当前 `ptest` 产品主线的首选使用入口。
如果你是在正常使用 `ptest` 做工作区、对象、用例和报告管理，优先使用：

- CLI
- `PTestAPI`
- `WorkflowService`

只有当你确实要直接调用底层隔离引擎时，才建议阅读本页。

## 当前定位

`VirtualenvIsolationEngine` 提供的是“Python 虚拟环境级隔离能力”，适合：

- 为开发中的功能验证虚拟环境隔离行为
- 直接测试隔离引擎本身
- 在较低层做包安装、命令执行和基础状态检查

当前可以认为它稳定具备这些能力：

- 创建和清理 virtualenv 环境
- 激活 / 停用环境
- 在环境中执行命令
- 安装、卸载、查询 Python 包
- 分配和释放端口
- 获取环境状态和引擎信息
- 使用基础事件监听机制

当前不应把它理解成：

- 完整的产品级环境管理 API
- 完整的网络隔离 / 权限控制 / 资源限制平台
- 当前主线对外承诺的首选集成方式

## 快速开始

### 1. 创建引擎

```python
from pathlib import Path

from ptest.isolation import VirtualenvIsolationEngine

engine = VirtualenvIsolationEngine(
    {
        "python_path": "/usr/bin/python3",
        "command_timeout": 300,
        "pip_timeout": 300,
    }
)
```

当前更值得依赖的配置项主要是：

- `python_path`
- `command_timeout`
- `pip_timeout`

### 2. 创建隔离环境

```python
import tempfile

temp_dir = Path(tempfile.mkdtemp())
env = engine.create_isolation(
    temp_dir,
    "my_test_env",
    {
        "project_name": "test_project",
    },
)

print(env.env_id)
print(env.venv_path)
```

### 3. 激活环境并安装包

```python
if env.activate():
    print("环境激活成功")

    installed = env.install_package("requests", version="2.32.3")
    print(installed)

    packages = env.get_installed_packages()
    print(packages)
```

### 4. 在隔离环境中执行命令

```python
result = env.execute_command(
    [
        str(env.python_path),
        "-c",
        "import requests; print(requests.__version__)",
    ]
)

if result.returncode == 0:
    print(result.stdout)
else:
    print(result.stderr)
```

### 5. 清理环境

```python
env.deactivate()
engine.cleanup_isolation(env)

# 如需清理该引擎创建的全部环境：
engine.cleanup_all_environments()
```

## 事件监听

```python
from ptest.isolation import IsolationEvent


def on_env_created(env, event, *args, **kwargs):
    print(f"环境 {env.env_id} 已创建")


def on_package_installed(env, event, package=None, *args, **kwargs):
    print(f"包 {package} 已安装到环境 {env.env_id}")


env.add_event_listener(IsolationEvent.ENVIRONMENT_CREATED, on_env_created)
env.add_event_listener(IsolationEvent.PACKAGE_INSTALLED, on_package_installed)
```

当前事件机制适合开发和调试用途，但不应直接等同于产品级审计或监控体系。

## 状态与基础资源信息

```python
status = env.get_status()
print(status["status"])
print(status["created_at"])
print(status["allocated_ports"])

engine_status = engine.get_isolation_status(env.env_id)
print(engine_status["isolation_type"])

engine_info = engine.get_engine_info()
print(engine_info["name"])
print(engine_info["supported_features"])
```

资源使用摘要目前是基础结构：

```python
env.update_resource_usage()
usage = env.resource_usage

print(usage["cpu"])
print(usage["memory"])
print(usage["disk"])
print(usage["network"])
```

这里的 `resource_usage` 更适合作为“基础状态摘要”，而不是完整监控能力。

## 端口管理

```python
port = env.allocate_port()
print(port)

released = env.release_port(port)
print(released)
```

这适合引擎级测试和受管命令执行场景。
如果后续产品层需要更完整的网络约束、能力声明或端口策略，应由更高层 backend 模型统一承接。

## 故障排查

### virtualenv 创建失败

```text
The virtual environment was not created successfully because ensurepip is not available
```

通常需要检查：

- Python 运行时是否完整
- `virtualenv` 依赖是否已安装
- 当前目录是否可写

### 包安装超时

可以适当调大：

- `pip_timeout`
- `command_timeout`

### 状态不符合预期

优先检查：

- `env.get_status()`
- `engine.get_isolation_status(env.env_id)`
- `env.validate_isolation()`

## 使用建议

- 如果你要做产品级测试流程编排，优先使用 `PTestAPI`
- 如果你要做工作区级生命周期管理，优先使用 CLI 或工作流服务
- 如果你要做引擎级验证、诊断或底层扩展，再直接使用 `VirtualenvIsolationEngine`
