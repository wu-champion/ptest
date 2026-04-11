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
print(problems["data"])

problem_id = problems["data"][0]["problem_id"]

detail = api.get_problem_record(problem_id)
assets = api.get_problem_assets(problem_id)
recovery = api.recover_problem(problem_id)

print(detail["data"]["problem_type"])
print(assets["data"]["preservation_status"])
print(recovery["data"]["mode"])
```

如果问题类型支持最小重放：

```python
replay = api.replay_problem(problem_id)
print(replay["data"])
print(replay["recovery_action"])
```

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
