# ptest Python API 指南

本文档描述当前主线下的 Python API 使用方式。

当前推荐入口是 `PTestAPI`，它直接基于统一工作流服务工作，而不是旧的 `TestFramework` 风格接口。

## 核心入口

```python
from pathlib import Path

from ptest.api import PTestAPI

api = PTestAPI(work_path=Path("./demo-workspace"))
```

`PTestAPI` 当前负责：

- 初始化和销毁工作区
- 安装和查询对象、工具
- 创建和执行测试用例
- 读取执行记录和 artifact
- 读取问题记录、问题资产和恢复动作
- 生成报告
- 管理数据模板、契约和 mock 资产

## 统一返回结构

API 当前统一返回结构化结果：

```python
result = api.get_environment_status()

print(result["success"])
print(result["status"])
print(result["message"])
print(result["data"])
print(result.get("error"))
print(result.get("error_code"))
```

建议调用方优先依赖这些字段：

- `success`
- `status`
- `message`
- `data`
- `error`
- `error_code`

## 环境管理

### 初始化工作区

```python
init_result = api.init_environment()
print(init_result["data"]["root_path"])
```

### 获取环境状态

```python
status = api.get_environment_status()
print(status["data"]["status"])
```

### 销毁工作区

```python
destroy_result = api.destroy_environment()
print(destroy_result["success"])
```

## 对象与工具

### 安装对象

```python
result = api.create_object(
    "db",
    "demo_db",
    driver="sqlite",
    database="./demo-workspace/demo.db",
)

print(result["success"])
```

当前对象操作里，启动、停止、重启等运行态动作由工作流服务承担：

```python
api.workflow.start_object("demo_db")
status = api.workflow.get_object_status("demo_db")
print(status["object"]["status"])
```

### 工具管理

```python
tool = api.install_tool("demo_tool", version="1.0")
print(tool["success"])

tools = api.list_tools()
print(tools["data"])
```

## 用例管理

### 创建用例

```python
result = api.create_test_case(
    test_type="database",
    name="sqlite_smoke",
    content={
        "db_type": "sqlite",
        "database": "./demo-workspace/demo.db",
        "query": "SELECT 1 as value",
        "expected_result": [{"value": 1}],
    },
    tags=["smoke"],
)

case_id = result["data"]["case_id"]
```

### 列出和执行用例

```python
cases = api.list_test_cases()
print(cases["data"])

run_result = api.run_test_case(case_id)
print(run_result["status"])
```

## 执行记录与 artifact

### 执行记录

```python
records = api.list_execution_records()
print(records["data"])
```

### 单条记录

```python
execution_id = records["data"][0]["execution_id"]
detail = api.get_execution_record(execution_id)
print(detail["data"])
```

### artifact 索引

```python
artifacts = api.get_execution_artifacts(execution_id)
print(artifacts["data"]["directory"])
print(artifacts["data"]["indexes"]["artifact_index"])
```

如需直接读取 artifact 内容：

```python
artifacts = api.get_execution_artifacts(
    execution_id,
    include_contents=True,
)
print(artifacts["data"]["contents"]["result/execution.json"])
```

## 问题记录与恢复

当一次执行失败时，当前主线会自动生成问题记录。

```python
problems = api.list_problem_records(case_id=case_id)
print(problems["count"])
print(problems["filters"])
print(problems["problems"])

problem_id = problems["data"][0]["problem_id"]

detail = api.get_problem_record(problem_id)
assets = api.get_problem_assets(problem_id)
recovery = api.recover_problem(problem_id)

print(detail["data"]["problem_type"])
print(detail["data"]["capabilities"])
print(assets["data"]["preservation_status"])
print(assets["assets"]["reproduction_summary"])
print(recovery["data"]["mode"])
```

其中：

- `list_problem_records()` 现在会稳定返回 `count`、`filters`、`problems`
- `get_problem_record()` / `get_problem_assets()` 仍保留 `data`，同时也会给出更直接的 `problem` / `assets` 别名字段
- 对 `api_response` 问题，`get_problem_assets()` 还会给出 `reproduction_summary`，方便把一次接口失败的最小复现材料直接交给别人复看
- `reproduction_summary.dependency_hints` 会补充失败前最近执行过的 case 线索，帮助你判断这次问题是否可能受前置执行影响
- `dependency_hints.recommended_actions` 会直接给出下一步排查建议，例如先检查最近前置 case，或先按顺序重跑候选前置 case 再 replay

如果 `detail["data"]["capabilities"]["can_replay"]` 为 `True`，则可以继续做最小重放：

```python
replay = api.replay_problem(problem_id)
print(replay["data"])
print(replay["recovery_action"])
print(replay["replay"]["comparison"])
print(replay["replay"]["comparison"]["summary"])
print(replay["replay"]["comparison"]["highlights"])
```

对于 `api_response` 问题，`replay["replay"]["comparison"]` 会直接给出原始失败现场与当前 replay 结果的对比摘要，
并通过 `assertion_outcome` / `reproduced` 告诉你这次 replay 是否仍然复现原问题。当前 `comparison.summary`
会优先给出更适合机器消费的 `status / boundary / headers / body` 变化概要，而 `comparison.highlights` 更适合人直接阅读。
如果原始失败阶段没有保全到响应头或响应体，`comparison.summary` 也会明确把这些字段标记为当前不可比较。
其中 `comparison.summary.body.*_preview` 只会给出轻量预览，帮助快速判断变化方向，不会直接展开成完整 patch。
其中 `comparison.summary.boundary` 会固定说明当前 replay 的可信边界，例如它只重放保全下来的请求，不会自动重建历史环境状态或前置 case 影响。
如果工作区里存在与本次失败相邻的前置执行，`comparison.summary.boundary.dependency_hints` 也会一起给出，方便把 replay 结果和可能的依赖来源对起来看。
同时 `comparison.summary.boundary.recommended_actions` 会给出结构化下一步动作建议，方便 CLI、自动化脚本或上层工具直接消费。

## 报告

```python
report = api.generate_report(format_type="html")
print(report["data"]["report_path"])
```

## 数据模板

### 保存模板

```python
api.save_data_template(
    "user_template",
    {
        "username": "{{username}}",
        "email": "{{email}}",
    },
)
```

### 生成数据

```python
generated = api.generate_data_from_template("user_template", count=2)
print(generated["data"]["results"])
```

## 契约与 mock

```python
contracts = api.list_contracts()
print(contracts["data"])

mocks = api.list_mock_servers()
print(mocks["data"])
```

## 说明

- 当前对外 Python API 以 `PTestAPI` 为主
- 如果你需要看简短可运行示例，优先阅读 [api-examples.md](api-examples.md)
- 如果你需要理解能力边界，请同时参考 [../architecture/system-overview.md](../architecture/system-overview.md)
