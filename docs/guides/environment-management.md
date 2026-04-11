# 环境管理指南

本文档描述当前主线中的环境生命周期管理方式。这里的“环境”本质上是一个工作区和它对应的隔离上下文，而不是单纯的目录。

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
uv run ptest workspace status
```

`init --path` 成功后，会自动把该路径设为活动工作区。

### 查看状态

```bash
uv run ptest env status --path ./demo-workspace
uv run ptest --path ./demo-workspace status
uv run ptest workspace status
```

普通业务命令在未显式传 `--path` 时，当前主线按下面的顺序解析目标工作区：

1. `--path`
2. 当前目录工作区
3. 活动工作区

如果最终命中的是活动工作区，CLI 会提示：

```text
Using active workspace: /abs/path/to/workspace
```

你也可以显式管理当前活动工作区：

```bash
uv run ptest workspace use ./demo-workspace
uv run ptest workspace unset
```

### 销毁

```bash
uv run ptest env destroy --path ./demo-workspace
```

`env destroy` 这类工作区生命周期收尾动作，不会通过活动工作区隐式命中目标。
如果你要销毁某个工作区，请继续显式传 `--path`，或者先切到该工作区目录后再执行相关检查命令。

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
- `destroyed`: 环境已销毁，只保留识别意义，不能继续用于测试管理，需重新初始化
- `uninitialized`: 当前路径还不是工作区

一旦工作区进入 `destroyed`：

- 它不再参与默认工作区解析
- `workspace use <path>` 也不能再指向它
- 如果当前目录本身就是一个 `destroyed` 工作区，CLI 会直接报错，而不是悄悄回退到别的活动工作区

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
