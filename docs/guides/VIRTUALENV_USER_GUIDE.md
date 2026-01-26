# Virtualenv隔离引擎使用指南

## 概述

Virtualenv隔离引擎是pypj/ptest框架的核心组件之一，提供Python虚拟环境隔离功能。它支持创建独立的Python环境，用于隔离测试依赖和执行环境。

## 主要特性

- ✅ **完整的虚拟环境支持** - 基于Python标准库venv模块
- ✅ **包管理集成** - 支持pip安装、卸载、更新Python包
- ✅ **进程执行隔离** - 在隔离环境中执行命令
- ✅ **端口管理** - 自动分配和管理网络端口
- ✅ **资源监控** - 监控环境资源使用情况
- ✅ **事件系统** - 完整的环境生命周期事件通知

## 快速开始

### 1. 创建Virtualenv隔离引擎

```python
from isolation.virtualenv_engine import VirtualenvIsolationEngine
from pathlib import Path

# 创建引擎实例
engine = VirtualenvIsolationEngine({
    "python_path": "/usr/bin/python3",  # 可选，默认使用系统Python
    "system_site_packages": False,      # 是否包含系统包
    "command_timeout": 300,             # 命令执行超时
    "pip_timeout": 300,                 # pip操作超时
})
```

### 2. 创建隔离环境

```python
import tempfile

# 创建临时目录
temp_dir = Path(tempfile.mkdtemp())

# 创建隔离环境
env_id = "my_test_env"
env = engine.create_isolation(temp_dir, env_id, {
    "project_name": "test_project",
    "python_version": "3.9",
})

print(f"环境创建成功: {env.env_id}")
print(f"虚拟环境路径: {env.venv_path}")
```

### 3. 激活环境并安装包

```python
# 激活环境
if env.activate():
    print("环境激活成功")
    
    # 安装包
    if env.install_package("requests==2.28.1"):
        print("requests包安装成功")
    
    # 获取已安装的包
    packages = env.get_installed_packages()
    print(f"已安装的包: {packages}")
```

### 4. 在隔离环境中执行命令

```python
# 执行Python代码
result = env.execute_command([
    str(env.python_path), 
    "-c", 
    "import requests; print(f'requests version: {requests.__version__}')"
])

if result.success:
    print(f"输出: {result.stdout}")
else:
    print(f"错误: {result.stderr}")
```

### 5. 清理环境

```python
# 停用环境
env.deactivate()

# 清理环境
engine.cleanup_isolation(env)

# 或者清理所有环境
engine.cleanup_all_environments()
```

## 高级用法

### 自定义配置

```python
# 创建带自定义配置的引擎
custom_config = {
    "python_path": "/usr/bin/python3.9",
    "system_site_packages": True,  # 包含系统site-packages
    "clear": True,                 # 创建前清理目标目录
    "symlinks": True,              # 使用符号链接而不是复制
    "upgrade": True,               # 升级依赖
    "command_timeout": 600,        # 更长的命令超时
    "pip_timeout": 600,            # 更长的pip超时
    "max_env_size": "2GB",         # 环境最大大小
}

engine = VirtualenvIsolationEngine(custom_config)
```

### 错误处理和恢复

```python
# 环境创建失败处理
try:
    env = engine.create_isolation(temp_dir, env_id, config)
except RuntimeError as e:
    print(f"环境创建失败: {e}")
    # 使用备用配置或回退到基础隔离
    env = engine.create_isolation(temp_dir, env_id, {"fallback": True})

# 包安装冲突处理
success = env.install_package("conflicting-package")
if not success:
    print("包安装失败，尝试强制安装")
    # 或者卸载冲突包后重新安装
    env.uninstall_package("conflicting-package")
    env.install_package("conflicting-package", upgrade=True)
```

### 并发环境管理

```python
import threading
from concurrent.futures import ThreadPoolExecutor

def create_test_env(env_id_suffix):
    temp_dir = Path(tempfile.mkdtemp())
    env_id = f"concurrent_test_{env_id_suffix}"
    
    engine = VirtualenvIsolationEngine({})
    env = engine.create_isolation(temp_dir, env_id, {})
    
    # 激活并测试
    env.activate()
    env.install_package("numpy")
    
    return env

# 创建多个并发环境
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(create_test_env, i) for i in range(3)]
    environments = [f.result() for f in futures]

# 清理所有环境
for env in environments:
    env.get_isolation_engine().cleanup_isolation(env)
```

### 事件监听

```python
from isolation.enums import IsolationEvent

def on_env_created(env, event, *args, **kwargs):
    print(f"环境 {env.env_id} 已创建")

def on_package_installed(env, event, package=None, *args, **kwargs):
    print(f"包 {package} 已安装到环境 {env.env_id}")

def on_env_error(env, event, error=None, *args, **kwargs):
    print(f"环境 {env.env_id} 发生错误: {error}")

# 添加事件监听器
env.add_event_listener(IsolationEvent.ENVIRONMENT_CREATED, on_env_created)
env.add_event_listener(IsolationEvent.PACKAGE_INSTALLED, on_package_installed)
env.add_event_listener(IsolationEvent.ERROR_OCCURRED, on_env_error)
```

## 环境状态查询

```python
# 获取环境状态
status = env.get_status()
print(f"环境状态: {status['status']}")
print(f"创建时间: {status['created_at']}")
print(f"激活时间: {status['activated_at']}")
print(f"进程数量: {status['process_count']}")
print(f"分配的端口: {status['allocated_ports']}")

# 获取引擎状态
engine_status = engine.get_isolation_status(env.env_id)
print(f"引擎状态: {engine_status}")

# 获取引擎信息
engine_info = engine.get_engine_info()
print(f"引擎信息: {engine_info}")
```

## 资源管理

```python
# 端口分配
port = env.allocate_port()
print(f"分配的端口: {port}")

# 释放端口
env.release_port(port)

# 更新资源使用情况
env.update_resource_usage()
usage = env.resource_usage
print(f"CPU使用率: {usage.cpu_percent}%")
print(f"内存使用: {usage.memory_mb}MB")
print(f"磁盘使用: {usage.disk_mb}MB")
```

## 最佳实践

### 1. 资源管理
- 及时清理不再使用的环境
- 设置合理的超时时间
- 监控磁盘空间使用

### 2. 错误处理
- 始终检查操作返回值
- 实现适当的错误恢复机制
- 记录详细的错误日志

### 3. 并发安全
- 避免在多线程间共享环境实例
- 使用线程安全的引擎实例
- 实现适当的锁机制

### 4. 配置优化
- 根据项目需求调整配置
- 使用环境特定的配置
- 考虑性能和安全的平衡

## 故障排除

### 常见问题

1. **虚拟环境创建失败**
   ```
   错误: The virtual environment was not created successfully because ensurepip is not available
   解决: 安装 python3-venv 包
   ```

2. **包安装超时**
   ```
   解决: 增加 pip_timeout 配置值
   ```

3. **权限错误**
   ```
   解决: 确保目录有写权限
   ```

4. **端口占用**
   ```
   解决: 检查端口是否被其他进程占用
   ```

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 验证环境隔离
is_valid = env.validate_isolation()
print(f"环境隔离验证: {is_valid}")

# 检查环境文件
print(f"Python可执行文件: {env.python_path.exists()}")
print(f"Pip可执行文件: {env.pip_path.exists()}")
print(f"激活脚本: {env.activate_script.exists()}")
```

## 性能优化

1. **缓存虚拟环境** - 复用基础环境
2. **并发安装** - 并行安装依赖包
3. **预安装常用包** - 减少重复安装时间
4. **使用本地pip源** - 加速包下载

## 示例项目

完整的示例项目请参考：
- `examples/api_examples.py` - API使用示例
- `examples/test_cases.py` - 测试用例示例
- `tests/unit/isolation/test_virtualenv_isolation.py` - 完整测试套件

---

*本文档将持续更新，请关注最新版本。*