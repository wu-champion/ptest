# ptest 测试文档

## 📋 测试概述

**现阶段的测试使用pytest/unittest，后面用自己的框架测试自己的框架试试**
本文档描述了 ptest 项目的测试策略、测试结构和测试覆盖范围。

## 🏗️ 测试架构

### 测试层级

```
tests/
├── unit/                    # 单元测试
│   ├── api/                 # API模块测试
│   ├── isolation/           # 隔离模块测试
│   ├── core/                # 核心模块测试
│   └── objects/             # 对象模块测试
├── integration/             # 集成测试
│   ├── database/            # 数据库集成测试
│   ├── api/                 # API集成测试
│   └── workflow/            # 工作流集成测试
├── e2e/                     # 端到端测试
├── performance/             # 性能测试
└── verification/            # 验证测试
```

### 测试金字塔

```
            /\
           /  \
          /    \
         /  E2E \   ← 端到端测试（少数，高价值）
        /________\
       /          \
      /Integration \  ← 集成测试（适量，中等价值）
     /______________\
    /                \
   /   Unit Tests     \ ← 单元测试（大量，快速反馈）
  /____________________\
```

## 🧪 测试分类

### 单元测试 (Unit Tests)

**目标**: 测试单个函数、类或模块的功能  
**范围**: 最小代码单元，无外部依赖  
**特点**: 快速、独立、可重复

#### 测试覆盖范围

| 模块 | 测试文件 | 覆盖内容 |
|-----|---------|---------|
| API | `unit/api/` | TestFramework, TestEnvironment 等 |
| 隔离 | `unit/isolation/` | IsolationManager, 各引擎实现 |
| 核心 | `unit/core/` | 核心类和工具函数 |
| 对象 | `unit/objects/` | ObjectManager, 各种对象类型 |

### 集成测试 (Integration Tests)

**目标**: 测试多个模块间的交互  
**范围**: 模块间接口，数据流  
**特点**: 中等复杂度，需要部分环境

#### 测试场景

| 场景 | 测试文件 | 测试内容 |
|-----|---------|---------|
| 数据库集成 | `integration/database/` | 数据库对象与框架集成 |
| API集成 | `integration/api/` | API测试与执行引擎集成 |
| 工作流集成 | `integration/workflow/` | 完整测试流程 |

### 端到端测试 (E2E Tests)

**目标**: 测试完整用户场景  
**范围**: 从用户输入到最终结果  
**特点**: 高复杂度，接近真实使用

### 性能测试 (Performance Tests)

**目标**: 测试系统性能指标  
**范围**: 响应时间、吞吐量、资源使用  
**特点**: 基准测试、压力测试

### 验证测试 (Verification Tests)

**目标**: 验证系统功能完整性  
**范围**: API完整性、结构验证  
**特点**: 确保实现符合规范

## 🎯 测试与需求对应

### ENV-001 环境隔离需求

| 需求项 | 测试类型 | 测试文件 | 状态 |
|-------|---------|---------|------|
| 文件系统隔离 | 单元测试 | `unit/isolation/test_basic_isolation.py` | ✅ 已完成 |
| 隔离管理器 | 单元测试 | `unit/isolation/test_isolation_manager.py` | 🚧 计划中 |
| Virtualenv隔离 | 集成测试 | `integration/isolation/test_virtualenv.py` | 🚧 计划中 |
| Docker隔离 | 集成测试 | `integration/isolation/test_docker.py` | 🚧 计划中 |

### API-001 Python API需求

| 需求项 | 测试类型 | 测试文件 | 状态 |
|-------|---------|---------|------|
| 框架核心功能 | 单元测试 | `unit/api/test_framework.py` | 🚧 计划中 |
| 环境管理 | 集成测试 | `integration/api/test_environment.py` | 🚧 计划中 |
| 对象管理 | 单元测试 | `unit/objects/test_manager.py` | 🚧 计划中 |

### OBJ-001 对象管理需求

| 需求项 | 测试类型 | 测试文件 | 状态 |
|-------|---------|---------|------|
| 数据库对象 | 集成测试 | `integration/database/test_db_objects.py` | ✅ 已完成 |
| 对象生命周期 | 单元测试 | `unit/objects/test_lifecycle.py` | 🚧 计划中 |
| 依赖管理 | 集成测试 | `integration/objects/test_dependencies.py` | 🚧 计划中 |

## 📊 测试覆盖率

### 当前覆盖情况

| 模块 | 覆盖率 | 测试文件数 | 状态 |
|-----|-------|-----------|------|
| 隔离模块 | 85% | 1 | ✅ 基础完成 |
| API模块 | 60% | 3 | 🚧 需增强 |
| 数据库模块 | 70% | 4 | ✅ 基础完成 |
| 对象模块 | 50% | 2 | 🚧 需增强 |
| 核心模块 | 40% | 1 | 🚧 需增强 |

### 目标覆盖率

| 时间节点 | 目标覆盖率 | 重点关注 |
|---------|-----------|-----------|
| Week 2 | 90% | 隔离模块完整覆盖 |
| Week 4 | 85% | API和对象模块增强 |
| Week 8 | 80% | 整体覆盖率提升 |
| Week 12 | 85% | 高级功能覆盖 |

## 🚀 运行测试

### 运行所有测试

```bash
# 使用 unittest
python -m unittest discover tests/

# 使用 pytest (推荐)
pytest tests/ -v
```

### 运行特定类型测试

```bash
# 单元测试
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v

# 隔离模块测试
pytest tests/unit/isolation/ -v
```

### 生成覆盖率报告

```bash
pytest --cov=ptest --cov-report=html tests/
# 查看: htmlcov/index.html
```

### 性能测试

```bash
python tests/performance/run_benchmarks.py
```

## 📝 测试编写规范

### 测试文件命名

- 单元测试: `test_<module_name>.py`
- 集成测试: `test_<feature>_integration.py`
- E2E测试: `test_<scenario>_e2e.py`
- 性能测试: `test_<feature>_performance.py`

### 测试类命名

```python
class TestModuleName(unittest.TestCase):
    """模块名 + Test"""
    pass

class TestFeatureIntegration(unittest.TestCase):
    """功能名 + Integration"""
    pass
```

### 测试方法命名

```python
def test_function_success_case(self):
    """test + 功能描述 + 场景"""
    pass

def test_function_with_invalid_input(self):
    """test + 功能描述 + 条件"""
    pass
```

### 测试结构

```python
import unittest
from unittest.mock import Mock, patch

class TestExample(unittest.TestCase):
    def setUp(self):
        """测试前准备"""
        pass
    
    def tearDown(self):
        """测试后清理"""
        pass
    
    def test_success_case(self):
        # Arrange
        # 准备测试数据
        
        # Act
        # 执行测试操作
        
        # Assert
        # 验证结果
        pass
```

## 🔧 测试工具和配置

### 测试依赖

```python
# requirements-dev.txt
pytest>=7.0.0
pytest-cov>=4.0.0
pytest-mock>=3.10.0
pytest-asyncio>=0.21.0
pytest-xdist>=3.0.0
black>=22.0.0
pylint>=2.15.0
mypy>=0.991
```

### 测试配置

```ini
# pytest.ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    performance: Performance tests
    slow: Slow running tests
```

### CI/CD 配置

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, 3.10, 3.11]
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v3
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt
      - name: Run tests
        run: |
          pytest tests/ --cov=ptest
```

## 📋 测试清单

### 新功能测试清单

- [ ] 单元测试覆盖
- [ ] 集成测试覆盖
- [ ] 边界条件测试
- [ ] 错误处理测试
- [ ] 性能基准测试
- [ ] 文档示例测试

### 代码质量检查

- [ ] 所有测试通过
- [ ] 测试覆盖率 > 80%
- [ ] 代码风格检查通过
- [ ] 类型检查通过
- [ ] 无安全漏洞

### 发布前检查

- [ ] 完整测试套件运行
- [ ] 性能回归测试
- [ ] 兼容性测试
- [ ] 文档验证测试

## 🔗 相关文档

- [开发指南](../development/development-guide.md)
- [API参考](../api/python-api.md)
- [实现计划](../development/implementation-plans/ENV-001_IMPLEMENTATION_PLAN.md)
- [项目结构](../architecture/system-overview.md)

---

**测试版本**: 1.0  
**最后更新**: 2026-01-25  
**维护者**: cp