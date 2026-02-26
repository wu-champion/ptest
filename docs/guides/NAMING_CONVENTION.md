# 项目命名规范

## 概述

本文档定义 ptest 项目的命名规范，确保内部开发与外部发布的一致性。

## 命名规则

| 场景 | 名称 | 说明 |
|------|------|------|
| **内部/CLI** | `ptest` | 用户运行命令、代码导入 |
| **PyPI 发布** | `ptestx` | 因 `ptest` 已被占用 |

## 使用场景

### 1. 用户安装
```bash
pip install ptestx
```

### 2. 用户运行
```bash
ptest --version
p --help
```

### 3. 代码导入
```python
import ptest
from ptest import PTestAPI
```

### 4. 配置文件
```toml
# pyproject.toml
name = "ptestx"           # PyPI 包名
version = "1.3.0"

[project.scripts]
ptest = "ptest.cli:main"   # CLI 入口
```

## GitHub Actions 工作流

| Workflow | 文件 | PyPI 相关配置 |
|----------|------|----------------|
| CI | ci.yml | 无 |
| CD | cd.yml | `pypi.org/project/ptestx/` |

## 常见错误

### ❌ 错误: 项目名与 PyPI 不匹配
```toml
# pyproject.toml
name = "ptest"  # 错误! PyPI 上已被占用
```
会导致发布失败: `403 Invalid API Token`

### ✅ 正确: 统一使用 ptestx
```toml
# pyproject.toml
name = "ptestx"
```

## 更新日志

- 2026-02-26: 初始版本
