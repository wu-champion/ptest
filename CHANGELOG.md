## [1.3.0] - 2026-02-25

> **注意**: v1.3.0 是内置断言系统版本
> 安装命令: `pip install ptestx==1.3.0`

### Added - 新增功能

#### Sprint 1: 断言系统基础
- 断言基类 (Assertion)
- 断言结果 (AssertionResult)
- 断言工厂 (AssertionFactory)
- 14种内置断言类型
- 期望/实际值显示
- 断言位置显示
- 修复建议生成

#### Sprint 2: 增强功能
- 链式断言 (And, Or, Not)
- 断言模板系统
- 内置模板 (http_response, api_success)

#### Sprint 3: 稳定化与发布
- 性能优化 (单次 <1ms, 1000次 <100ms)
- 断言使用指南

---

## [1.2.0] - 2026-02-24

> **注意**: v1.2.0 是 CLI 完善与功能补全版本
> 安装命令: `pip install ptestx==1.2.0`

### Added - 新增功能

#### Sprint 1: CLI 完善
 测试套件执行 (ptest suite run)
 Mock CLI 集成 (ptest mock start/stop/list)
 并行执行 (ptest case run --parallel)

#### Sprint 2: 功能补全
 SQL INSERT 格式 (ptest data generate --format sql)
 YAML 用例持久化
 用例引用作为 Setup

#### Sprint 3: 体验优化
 快速开始示例 (5个)
 执行进度显示
 数据库通用接口

---

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-02-10

> **注意**: 从 v1.1.0 开始，PyPI 包名由 `ptest` 改为 `ptestx`，
> 原因是 `ptest` 已被其他项目占用。
> 
> 安装命令: `pip install ptestx==1.1.0`
> 
> 所有功能保持不变：
> - CLI 命令: `ptest` / `p`
> - Python 导入: `import ptest`

### Added - 新增功能

#### Week 1: 测试数据生成器
- **数据生成模块** (`ptest.data`)
  - 30+ 种数据类型支持（姓名、邮箱、电话、UUID、整数、浮点数等）
  - Faker 库集成，支持中英文国际化
  - 批量数据生成（支持 JSON/YAML/CSV/Raw 格式）
  - 数据模板系统，支持变量替换
  - 随机种子支持，实现确定性生成
  - CLI 命令: `ptest data generate/template/types`

#### Week 2: API 契约管理
- **契约管理模块** (`ptest.contract`)
  - OpenAPI 3.0/2.0 契约导入支持
  - 从 URL 或文件导入契约
  - 契约验证（JSON Schema 验证）
  - 自动生成测试用例
  - 用例持久化存储（JSON 格式）
  - CLI 命令: `ptest contract import/list/show/validate/generate-cases/delete`

#### Week 3: Hooks 与配置管理
- **Hooks 系统** (`ptest.cases.hooks`)
  - 4 种 Hook 类型：command、api、sql、function
  - Setup/Teardown 支持
  - 条件执行（only_on_success 等）
  - 失败处理和超时控制
  
- **配置管理** (`ptest.config`)
  - YAML/JSON 配置文件支持
  - 环境变量展开（`$VAR`, `${VAR}`, `${VAR:-default}`）
  - 配置模板（minimal/full/api/database）
  - 配置验证功能
  - CLI 命令: `ptest config init/validate/show/edit`

#### Week 4: 测试套件基础
- **测试套件模块** (`ptest.suites`)
  - 测试套件数据模型（TestSuite, CaseRef）
  - 用例依赖关系管理
  - 拓扑排序和依赖验证
  - 串行/并行执行模式
  - 套件验证和排序
  - CLI 命令: `ptest suite create/list/show/delete/validate/run`

#### Week 5: Mock 服务 + 并行执行
- **Mock 服务** (`ptest.mock`)
  - Flask-based Mock 服务器
  - 动态路由配置
  - 条件响应匹配（headers, query, body）
  - 请求历史记录
  - 模板变量支持（`{{uuid}}`, `{{timestamp}}`）
  - 优雅关闭机制
  - CLI 命令: `ptest mock start/stop/status/logs/list/add-route`

- **并行执行** (`ptest.execution`)
  - 基于 ThreadPoolExecutor 的并行执行
  - 依赖拓扑排序
  - 循环依赖检测
  - 结果聚合和报告
  - 超时控制

#### Week 6: Fixtures + 报告增强
- **Fixtures 机制** (`ptest.fixtures`)
  - `@fixture` 装饰器
  - session/function 作用域
  - 依赖注入支持
  - Generator 支持（yield/teardown）
  - `use_fixtures` 装饰器

- **增强报告** (`ptest.reports.enhanced_generator`)
  - 现代化 HTML 模板
  - Chart.js 图表集成（结果分布、时间趋势）
  - 响应式布局设计
  - 附件支持（截图、日志）
  - 历史数据保存和对比

### Changed - 改进

- 统一使用 `get_logger()` 进行日志记录
- 改进 CLI 输出格式和颜色显示
- 优化异常处理机制
- 增强类型注解覆盖率

### Fixed - 修复

- 修复 MyPy 类型检查问题
- 修复 Ruff 代码风格问题
- 修复 Windows Unicode 编码问题
- 修复子进程安全漏洞（使用 shlex 转义）
- 修复 SQL/命令注入风险

### Security - 安全

- 添加 `use_shell` 配置选项，默认禁用 shell=True
- 添加 `allow_unsafe_sql` 配置选项
- 使用 `shlex.quote()` 和 `shlex.split()` 转义命令

## [1.0.1] - 2026-01-30

### Fixed
- 修复 Docker 引擎在模拟模式下的问题
- 修复集成测试配置问题
- 统一日志使用规范

## [1.0.0] - 2026-01-25

### Added - 初始版本
- 核心架构实现
  - 环境隔离系统（Basic/Virtualenv/Docker）
  - 对象管理系统（数据库、Web 服务）
  - 测试用例管理（创建、执行、结果跟踪）
  - 报告生成（HTML/JSON）
  - CLI 命令接口
  - Python API

[1.1.0]: https://github.com/cp/ptest/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/cp/ptest/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/cp/ptest/releases/tag/v1.0.0
