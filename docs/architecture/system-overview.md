# 系统架构总览

本文档描述当前主线下的系统架构。

当前架构重点已经从早期的“多个 manager 并列入口”收敛为“统一工作流主线 + 持久化工作区”。

## 核心分层

```text
CLI / PTestAPI
        |
        v
 WorkflowService
        |
        +--> WorkspaceStorage
        +--> models
        +--> isolation
        +--> objects
        +--> cases
        +--> reports
        +--> data / contract / mock / suites
```

## 设计目标

当前主线设计围绕这几个目标：

1. 环境、对象、用例、执行结果统一进入同一条主流程
2. CLI 和 Python API 操作同一套能力，而不是两套实现
3. 关键状态可落盘，可恢复，可清理
4. 第一阶段 MVP 主线可验证、可重复执行

## 当前关键组件

### `WorkflowService`

统一编排服务，负责：

- 初始化与销毁工作区
- 安装、启动、停止对象和工具
- 创建和执行用例
- 管理 suite
- 保存数据模板、契约和 mock 资产
- 生成报告
- 读取执行记录和 artifact

### `WorkspaceStorage`

工作区持久化层，负责：

- 保存环境元数据
- 保存对象、工具、执行记录
- 保存 artifact 索引
- 维护 `.ptest/` 下的主线状态

### `models`

当前主线数据模型主要包括：

- `EnvironmentRecord`
- `ManagedObjectRecord`
- `ToolRecord`
- `ExecutionRecord`

### `isolation`

隔离层负责具体隔离环境的创建、附着、验证和清理。当前第一阶段重点是：

- `basic`
- `virtualenv`
- `docker`

更深的多引擎恢复和治理仍属于后续增强方向。

### `objects`

对象层当前按“抽象先行，实例验证”推进，重点支持：

- 通用服务对象
- 通用数据库对象

当前 CLI 主入口已收敛为更少的默认对象类型，通过统一对象模型进入主线。

### `cases`

用例层负责：

- 用例持久化
- 执行分发
- 执行结果封装
- 与执行记录、报告系统衔接

### `reports`

报告层当前定位是：

- 基于已有执行结果生成 HTML / JSON / Markdown 报告
- 不承担工作区状态本身的持久化职责

## 工作区结构

```text
workspace/
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

当前架构里，工作区是所有主线资产的根。

## 主线执行流

一个标准的第一阶段闭环大致如下：

1. `init_environment()`
2. 安装对象或工具
3. 创建 case
4. 执行 case 或 suite
5. 保存 execution record 和 artifact
6. 生成报告
7. `destroy_environment()`

## 为什么不再以旧入口为中心

早期结构里，环境、对象、用例、报告都各自管理自己的主流程，容易出现：

- CLI 与 API 行为不一致
- 关键状态只存在于内存
- 跨命令恢复困难
- 结果和上下文散落

当前主线重构的目标，就是避免继续沿着这条路径扩散。

## 当前边界

- Web UI 不属于第一阶段核心架构
- 高级 CI 编排不属于当前核心交付
- 更完整的缺陷复现体系仍在后续阶段

## 相关文档

- [README.md](README.md)
- [../development/development-guide.md](../development/development-guide.md)
- [../api/python-api-guide.md](../api/python-api-guide.md)
- [../guides/environment-management.md](../guides/environment-management.md)
