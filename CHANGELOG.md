## [1.6.0] - 2026-03-27

### Added - 新增功能

- 新增 MySQL 全生命周期主案例，当前可在受管工作区内完成 `install -> start -> use -> stop -> uninstall`
- `mysql` 主对象语义已收口为数据库服务产品对象，不再默认落到通用连接对象语义
- MySQL 主案例已支持真实 `deb-bundle` 安装源接入，并可将核心 `.deb` 解包到受管 rootfs
- 已新增可重复执行的 MySQL 主案例脚本入口 `scripts/mysql_full_lifecycle_scenario.py`
- 用户文档新增 MySQL 全生命周期实践，按测试工程师分步操作方式展示真实使用流程

### Changed - 改进

- MySQL 主案例当前运行模型已明确为“受管工作区 + host runtime backend”
- `install` 已从“仅处理主包”扩展为“主包 + 依赖资产”的受管安装流程
- 数据库 case 已支持通过 `object_name` 绑定已管理的 MySQL 对象，并自动补齐连接参数
- README、快速开始和用户手册已重写为更贴近测试工程师真实使用习惯的表达方式
- README 已前移说明 `ptest / ptestx` 命名关系，避免首次安装和案例阅读时混淆

### Fixed - 修复

- MySQL 真实启动前已增加 runtime backend 能力预检，不再把受限环境中的 bind 失败模糊地表现为中途启动错误
- MySQL `stop` / `uninstall` 已形成更完整的边界检查和清理闭环
- 文档中的工作区使用方式已降低对重复 `--path` 的依赖，更符合单工作区日常操作模式

## [1.5.0] - 2026-03-26

### Added - 新增功能

- 第二阶段问题保全与复现主线已建立统一 `problem` 模型、问题索引和问题资产持久化
- CLI / Python API / `WorkflowService` 已统一支持 `problem list/show/assets/recover` 主线
- 已支持 `api_response` 问题的最小重放
- 已支持 `data_state` 问题的最小恢复方案输出
- 已支持 `environment_init`、`dependency_object`、`dependency_configuration` 问题保全与最小恢复方案
- 已支持 `service_runtime` 问题的轻量保全与基础恢复方案
- 问题记录已开始持久化恢复动作，当前包含 `recovery.json`、`latest_action` 和 `metadata.latest_recovery`

### Changed - 改进

- 问题资产已统一输出 `preservation_status`、`required_assets`、`available_assets`、`missing_assets` 与 `missing_reasons`
- 环境 / 依赖类问题已扩展到“对象启动成功但 endpoint 不可达”的预运行校验场景
- 问题记录与恢复动作已形成最小关联闭环，便于按问题视角追踪后续验证动作
- 第二阶段当前已完成正式收口，后续重点转向案例化准备和下一阶段衔接

## [1.4.0] - 2026-03-13

### Added - 新增功能

- 第一阶段主线重构已建立统一 `WorkflowService`
- 环境、对象、工具、用例、套件、数据、契约、Mock、报告已接入统一主线
- execution record 与 artifact 已形成标准目录结构和检索入口
- CLI 主线命令已统一支持工作区 `--path`

### Changed - 改进

- Python API 与 CLI 主线返回结构已完成第一轮统一
- 环境销毁与 isolation 恢复/清理策略已完成第一轮收口
- 主线接口已完成第一轮参数类型注解规范化
- README 和对外发布说明已按当前 CLI 行为更新

### Fixed - 修复

- 修复主线命令对未初始化工作区的错误提示不一致问题
- 修复执行记录与 artifact 目录结构缺乏索引入口的问题
- 修复对象运行态恢复只回放元数据、不返回可信状态的问题

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
