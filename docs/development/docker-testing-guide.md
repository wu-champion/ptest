# Docker 测试指南

本文档说明如何在本地开发和 CI/CD 环境中运行 Docker 相关测试。

---

## 📋 测试策略

ptest 采用**分层测试策略**：

| 测试类型 | 环境 | 触发时机 | 目的 |
|---------|------|---------|------|
| **模拟测试** | 模拟 Docker 环境 | PR 检查、日常开发 | 快速反馈 |
| **真实 Docker 测试** | 真实 Docker daemon | Nightly、发布前 | 真实环境验证 |

---

## 🚀 快速开始

### 1. 运行模拟测试（推荐）

模拟测试使用 `simulation_mode`，不依赖真实 Docker 环境：

```bash
# 运行所有集成测试（使用模拟环境）
pytest tests/integration/ -v

# 仅运行 Docker 相关测试（模拟环境）
pytest tests/integration/test_docker_complete.py -v

# 运行单元测试
pytest tests/unit/ -v
```

**特点**:
- ✅ 快速（< 30 秒）
- ✅ 无需 Docker
- ✅ 适合日常开发

---

### 2. 运行真实 Docker 测试

#### 前提条件

确保本地已安装并运行 Docker：

```bash
# 检查 Docker 状态
docker --version
docker info

# 测试 Docker 是否正常工作
docker run hello-world
```

#### 运行测试

```bash
# 运行真实 Docker 集成测试
pytest tests/integration/docker/ -v

# 运行特定真实 Docker 测试
pytest tests/integration/docker/test_real_docker.py::TestRealDockerEnvironment -v

# 运行完整的 Docker 测试套件（包括模拟和真实）
pytest tests/integration/ -v --ignore=none
```

**特点**:
- 🐳 需要真实 Docker 环境
- ⏱️ 较慢（2-5 分钟，取决于网络）
- ✅ 覆盖真实场景

---

## 🔧 测试环境配置

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DOCKER_HOST` | Docker daemon 地址 | `unix:///var/run/docker.sock` |
| `SKIP_DOCKER_TESTS` | 是否跳过 Docker 测试 | `false` |

### 在代码中指定测试模式

```python
from ptest.isolation.docker_engine import DockerIsolationEngine

# 模拟模式（默认）
engine = DockerIsolationEngine({
    "simulation_mode": True,
    "default_image": "python:3.9-slim",
})

# 真实 Docker 模式
engine = DockerIsolationEngine({
    "simulation_mode": False,  # 或省略
    "default_image": "python:3.9-slim",
})
```

---

## 📊 CI/CD 配置

### PR 检查（模拟环境）

`.github/workflows/ci.yml`:

```yaml
- name: 运行集成测试
  run: |
    # 使用模拟环境，快速完成
    pytest tests/integration/ -v \
      --ignore=tests/integration/docker/test_real_docker.py
```

### Nightly 测试（真实环境）

`.github/workflows/nightly.yml`:

```yaml
jobs:
  real-docker-tests:
    runs-on: ubuntu-latest
    services:
      docker:
        image: docker:25-dind
        options: --privileged
    
    steps:
      - name: 运行真实 Docker 测试
        run: pytest tests/integration/docker/ -v
```

**运行时间**:
- 每天凌晨 2 点（UTC）
- 可手动触发

---

## 🐛 常见问题

### Q1: 测试提示 "Docker 环境不可用"

**原因**: Docker daemon 未运行或无法连接

**解决**:
```bash
# 启动 Docker（macOS/Windows）
open -a Docker  # macOS

# 或 Linux
sudo systemctl start docker

# 验证
docker info
```

### Q2: 真实 Docker 测试太慢

**原因**: 需要拉取 Docker 镜像

**解决**:
```bash
# 预拉取常用镜像
docker pull python:3.9-slim
docker pull python:3.9-alpine

# 然后再运行测试
pytest tests/integration/docker/ -v
```

### Q3: 权限错误 "permission denied"

**原因**: 当前用户不在 docker 组

**解决**:
```bash
# Linux: 将用户添加到 docker 组
sudo usermod -aG docker $USER
newgrp docker

# 验证
docker run hello-world
```

### Q4: CI 中 Docker 测试失败

**原因**: CI 环境可能没有 Docker 服务

**解决**:
- 在 CI 配置中添加 Docker-in-Docker 服务
- 或仅运行模拟测试（推荐）

---

## 📝 测试分类

### 模拟测试文件

| 文件 | 说明 |
|------|------|
| `tests/integration/test_docker_complete.py` | Docker 引擎完整功能（模拟） |
| `tests/integration/test_docker_complete_fixed.py` | 修复版 Docker 测试（模拟） |
| `tests/integration/test_docker_basic_final.py` | Docker 基础功能（模拟） |

### 真实 Docker 测试文件

| 文件 | 说明 |
|------|------|
| `tests/integration/docker/test_real_docker.py` | 真实 Docker 环境测试 |

---

## 🎯 最佳实践

### 开发流程

1. **日常开发**: 使用模拟测试
   ```bash
   pytest tests/unit/ tests/integration/ -v
   ```

2. **提交前**: 确保模拟测试通过
   ```bash
   pytest tests/ -v --ignore=tests/integration/docker/
   ```

3. **发布前**: 运行真实 Docker 测试
   ```bash
   # 本地验证
   pytest tests/integration/docker/ -v
   
   # 或触发 nightly build
   gh workflow run nightly.yml
   ```

### 编写新测试

为测试添加 Docker 可用性检查：

```python
import unittest

def is_docker_available():
    """检查 Docker 是否可用"""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False

@unittest.skipUnless(
    is_docker_available(), 
    "Docker 不可用，跳过测试"
)
class TestMyDockerFeature(unittest.TestCase):
    def test_feature(self):
        # 测试代码
        pass
```

---

## 📚 相关文档

- [系统架构](../architecture/system-overview.md)
- [隔离引擎](../architecture/ISOLATION_ARCHITECTURE.md)
- [CI/CD 配置](../../.github/workflows/ci.yml)
- [Nightly 配置](../../.github/workflows/nightly.yml)

---

**维护者**: cp  
**最后更新**: 2026-02-07
