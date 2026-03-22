# ptest Python API 示例

本文档只使用当前 `PTestAPI` 与统一工作流主线已经验证过的接口。

## 示例 1：初始化工作区并执行一个数据库用例

```python
from pathlib import Path

from ptest.api import PTestAPI

workspace = Path("./example-workspace")
api = PTestAPI(work_path=workspace)

init_result = api.init_environment()
print(init_result["status"])

api.create_object(
    "db",
    "demo_db",
    driver="sqlite",
    database=str(workspace / "demo.db"),
)
api.workflow.start_object("demo_db")

case_result = api.create_test_case(
    test_type="database",
    name="sqlite_smoke",
    content={
        "db_type": "sqlite",
        "database": str(workspace / "demo.db"),
        "query": "SELECT 1 as value",
        "expected_result": [{"value": 1}],
    },
    tags=["smoke", "database"],
)

case_id = case_result["data"]["case_id"]
run_result = api.run_test_case(case_id)

print(run_result["success"])
print(run_result["status"])
print(run_result["data"]["execution_id"])
```

## 示例 2：读取执行记录和 artifact 索引

```python
records = api.list_execution_records()
latest = records["data"][0]

execution_id = latest["execution_id"]
detail = api.get_execution_record(execution_id)
artifacts = api.get_execution_artifacts(execution_id)

print(detail["data"]["status"])
print(artifacts["data"]["directory"])
print(artifacts["data"]["indexes"]["artifact_index"])
```

如果你需要直接读取 artifact 内容：

```python
artifacts = api.get_execution_artifacts(
    execution_id,
    include_contents=True,
)

print(artifacts["data"]["contents"]["result/execution.json"])
```

## 示例 3：生成报告

```python
report = api.generate_report(format_type="json")
print(report["data"]["report_path"])
```

## 示例 4：数据模板

```python
save_result = api.save_data_template(
    "user_template",
    {
        "username": "{{username}}",
        "email": "{{email}}",
    },
)

print(save_result["success"])

generated = api.generate_data_from_template("user_template", count=2)
print(generated["data"]["results"])
```

## 示例 5：契约与 mock

当前 API 也支持把契约、mock 这类工作区资产纳入统一主线。

```python
contracts = api.list_contracts()
print(contracts["data"])

mocks = api.list_mock_servers()
print(mocks["data"])
```

## 示例 6：结构化返回值

`PTestAPI` 当前统一返回结构化结果，调用方应优先读取这些字段：

```python
result = api.get_environment_status()

print(result["success"])
print(result["status"])
print(result["message"])
print(result["data"])
print(result.get("error"))
print(result.get("error_code"))
```

推荐约定：

- `success`: 操作是否成功
- `status`: 当前状态，如 `ready`、`passed`、`generated`
- `message`: 面向调用方的简短说明
- `data`: 业务结果
- `error` / `error_code`: 失败时读取

## 示例 7：清理资源

```python
destroy_result = api.destroy_environment()
print(destroy_result["success"])
```

## 说明

- 当前 API 入口类是 `PTestAPI`
- 文档中的示例以第一阶段 MVP 主线为准
- 更完整的接口说明见 [python-api-guide.md](python-api-guide.md)
