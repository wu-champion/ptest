# ptest 项目结构说明

## 📁 目录结构概览

```
ptest/
│
├── src/                          # 📦 核心代码目录
│   └── ptest/                    # 框架主包
│       ├── __init__.py
│       ├── main.py               # CLI入口点
│       ├── cli.py                # CLI实现
│       ├── api.py                # Python API
│       ├── core.py               # 核心功能
│       ├── config.py             # 配置管理
│       ├── utils.py              # 框架内工具类
│       ├── environment.py        # 环境管理
│       │
│       ├── cases/                # 📝 测试用例管理
│       │   ├── __init__.py
│       │   ├── case.py
│       │   ├── executor.py
│       │   ├── manager.py
│       │   ├── result.py
│       │   └── tag.py
│       │
│       ├── isolation/            # 🔒 隔离引擎
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── manager.py
│       │   ├── basic_engine.py
│       │   ├── virtualenv_engine.py
│       │   ├── docker_engine.py
│       │   ├── enums.py
│       │   ├── conflict_detector.py
│       │   ├── dependency_resolver.py
│       │   ├── package_cache.py
│       │   ├── package_manager.py
│       │   ├── parallel_installer.py
│       │   └── version_manager.py
│       │
│       ├── objects/              # 🎯 对象管理
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── manager.py
│       │   ├── db.py
│       │   ├── db_client.py
│       │   ├── db_server.py
│       │   ├── db_enhanced.py
│       │   ├── db_v2.py
│       │   ├── web.py
│       │   ├── service.py
│       │   └── service_base.py
│       │
│       ├── reports/              # 📊 报告生成
│       │   ├── __init__.py
│       │   └── generator.py
│       │
│       └── tools/                # 🛠️ 工具管理
│           ├── __init__.py
│           └── manager.py
│
├── docs/                         # 📚 文档目录
│   ├── plan/                     # 📋 开发计划（不上传GitHub）
│   │   ├── 01_VIRTUALENV_IMPLEMENTATION_PLAN.md
│   │   ├── 02_DOCKER_IMPLEMENTATION_PLAN.md
│   │   ├── 03_next_steps_plan.md
│   │   ├── 04_production_readiness_plan.md
│   │   └── PTEST-004_PHASE1_COMPLETION_REPORT.md
│   │
│   ├── architecture/              # 🏗️ 架构文档
│   │   ├── system-overview.md
│   │   └── ISOLATION_ARCHITECTURE.md
│   │
│   ├── api/                      # 📖 API文档
│   │   ├── README.md
│   │   ├── python-api-guide.md
│   │   └── api-examples.md
│   │
│   ├── guides/                   # 💡 使用指南
│   │   ├── environment-management.md
│   │   └── VIRTUALENV_USER_GUIDE.md
│   │
│   ├── user-guide/               # 👤 用户指南
│   │   ├── README.md
│   │   └── basic-usage.md
│   │
│   ├── development/              # 🛠️ 开发文档
│   │   ├── development-guide.md
│   │   ├── PYTHON_API_IMPLEMENTATION.md
│   │   ├── implementation-plans/
│   │   ├── progress-reports/
│   │   ├── implementation-reports/
│   │   └── test-reports/
│   │
│   ├── archived/                 # 🗃️ 归档文档
│   │   └── ...
│   │
│   ├── README.md
│   ├── STRUCTURE.md
│   └── PROJECT_STRUCTURE.md      # 本文档
│
├── examples/                     # 💻 示例代码
│   ├── virtualenv_examples.py
│   ├── api_examples.py
│   └── test_cases.py
│
├── tests/                        # 🧪 测试代码
│   ├── unit/                     # 单元测试
│   │   ├── core/
│   │   ├── isolation/
│   │   ├── objects/
│   │   └── api/
│   ├── integration/               # 集成测试
│   │   ├── database/
│   │   ├── api/
│   │   └── test_docker_*.py
│   ├── e2e/                      # 端到端测试
│   ├── performance/              # 性能测试
│   ├── verification/             # 验证测试
│   └── reports/                  # 测试报告
│
├── .gitignore                    # Git忽略规则
├── .python-version               # Python版本指定
├── LICENSE                      # 许可证
├── README.md                    # 项目说明
├── pyproject.toml               # 项目配置
├── pytest.ini                   # pytest配置
├── uv.lock                     # uv锁定文件
└── session-*.md                # 会话记录（不上传）
```

## 📦 各目录详细说明

### 1. **src/ptest/** - 核心代码目录

框架的核心实现代码，包含所有主要功能模块。

#### **核心文件**
- `main.py` - CLI入口点，处理命令行参数
- `cli.py` - CLI实现，所有命令行逻辑
- `api.py` - Python API接口，提供编程访问
- `core.py` - 核心功能实现
- `config.py` - 配置管理
- `utils.py` - 框架内工具类
- `environment.py` - 环境管理

#### **cases/** - 测试用例管理
管理测试用例的完整生命周期，包括创建、执行、结果跟踪等。

#### **isolation/** - 隔离引擎
提供多种环境隔离机制：
- `basic_engine.py` - 基础文件系统隔离
- `virtualenv_engine.py` - Python虚拟环境隔离
- `docker_engine.py` - Docker容器隔离
- `manager.py` - 隔离管理器
- 其他支持模块：冲突检测、依赖解析、包管理等

#### **objects/** - 对象管理
管理各种被测对象：
- 数据库对象（MySQL、PostgreSQL等）
- Web服务对象
- 通用服务对象
- 对象管理器

#### **reports/** - 报告生成
生成各种格式的测试报告（HTML、JSON等）。

#### **tools/** - 工具管理
管理开发工具和测试工具的安装、启动、停止等。

---

### 2. **docs/** - 文档目录

所有项目相关文档，按类型分类。

#### **plan/** - 开发计划（不上传GitHub）
记录开发过程中的详细计划文档，包括：
- 各阶段的实施计划
- 完成报告
- 进度跟踪

**重要**: 此目录不纳入Git版本控制，仅供内部开发参考。

#### **architecture/** - 架构文档
系统设计和架构说明文档。

#### **api/** - API文档
完整的API参考和使用示例。

#### **guides/** - 使用指南
详细的功能使用说明和最佳实践。

#### **user-guide/** - 用户指南
面向最终用户的快速入门和使用教程。

#### **development/** - 开发文档
开发者相关文档，包括：
- 开发指南
- 实现计划
- 进度报告
- 测试报告

#### **archived/** - 归档文档
历史文档和已废弃功能的文档。

---

### 3. **examples/** - 示例代码

演示框架各功能如何使用的示例代码。

---

### 4. **tests/** - 测试代码

完整的测试套件，按类型分类。

#### **unit/** - 单元测试
各模块的单元测试。

#### **integration/** - 集成测试
模块间集成和端到端测试。

#### **e2e/** - 端到端测试
完整工作流的测试。

#### **performance/** - 性能测试
性能基准和压力测试。

#### **verification/** - 验证测试
验证API结构和功能的测试。

#### **reports/** - 测试报告
测试结果和覆盖率报告。

---

### 5. **根目录文件**

项目基础配置和文档文件。

- `.gitignore` - Git版本控制忽略规则
- `.python-version` - 指定Python版本（3.12+）
- `LICENSE` - 项目许可证
- `README.md` - 项目说明文档
- `pyproject.toml` - 项目配置文件（uv管理）
- `pytest.ini` - pytest测试配置
- `uv.lock` - uv依赖锁定文件

---

## 🚀 快速导航

### **开发者**
- 📖 开发指南：`docs/development/development-guide.md`
- 🏗️ 架构文档：`docs/architecture/`
- 🧪 测试代码：`tests/`
- 💻 示例代码：`examples/`

### **用户**
- 📖 快速开始：`docs/user-guide/README.md`
- 💡 使用指南：`docs/guides/`
- 📚 API文档：`docs/api/`

### **维护者**
- 📋 开发计划：`docs/plan/`
- 📊 进度报告：`docs/development/progress-reports/`
- 📝 实现报告：`docs/development/implementation-reports/`

---

## 📝 组织原则

### **代码组织**
1. **清晰分层** - 核心功能、业务逻辑、工具类分离
2. **模块化** - 每个模块职责单一，高内聚低耦合
3. **可扩展** - 易于添加新功能和自定义扩展

### **文档组织**
1. **分类明确** - 按文档类型和受众分类
2. **易于查找** - 结构化命名和目录组织
3. **版本控制** - 计划文档不上传，其他文档完整版本管理

### **测试组织**
1. **分层测试** - 单元、集成、端到端测试分开
2. **清晰命名** - 统一的测试文件命名规范
3. **完整覆盖** - 确保关键功能有测试覆盖

---

## 🔧 开发规范

### **代码提交**
- 遵循Git Flow工作流
- 提交信息清晰描述改动
- 确保测试全部通过
- 更新相关文档

### **开发计划**
- 在`docs/plan/`创建详细计划文档
- 计划通过审核后实施
- 完成后记录到实现报告

### **版本管理**
- 使用语义化版本号（1.0.1）
- 更新`pyproject.toml`中的版本号
- 发布时更新`CHANGELOG.md`

---

## 📊 项目状态

- **版本**: 1.0.1
- **Python**: 3.12+
- **管理工具**: uv
- **测试框架**: pytest
- **完成度**: 约95%

---

**最后更新**: 2026-01-30
**维护者**: ptest开发团队
