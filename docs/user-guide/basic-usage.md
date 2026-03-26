# ptest 快速开始

本文档只覆盖当前 `1.5.0` 主线已经稳定支持的最小闭环：

`环境初始化 -> 对象安装与启动 -> 用例创建与执行 -> 执行记录与报告 -> 环境销毁`

## 环境要求

- Python 3.12+
- 建议使用 `uv`
- Docker 属于可选能力，本地快速开始不依赖它

## 安装

如果你在源码仓库内工作，优先使用：

```bash
uv sync
uv run ptest --version
```

如果你使用构建产物安装：

```bash
uv pip install ptestx
ptest --version
```

## CLI 快速开始

以下示例使用一个 SQLite 数据库用例来打通当前 MVP 主线。

### 1. 初始化工作区

```bash
uv run ptest init --path ./demo-workspace
uv run ptest env status --path ./demo-workspace
```

### 2. 安装并启动对象

```bash
uv run ptest --path ./demo-workspace obj install db demo_db --database ./demo-workspace/demo.db --driver sqlite
uv run ptest --path ./demo-workspace obj start demo_db
uv run ptest --path ./demo-workspace obj status demo_db
```

### 3. 添加测试用例

`case add` 当前要求通过 `--data` 或 `--file` 提供 JSON。

```bash
uv run ptest --path ./demo-workspace case add sqlite_smoke --data '{
  "type": "database",
  "db_type": "sqlite",
  "database": "./demo-workspace/demo.db",
  "query": "SELECT 1 as value",
  "expected_result": [{"value": 1}]
}'
```

### 4. 执行测试

```bash
uv run ptest --path ./demo-workspace case run sqlite_smoke
uv run ptest --path ./demo-workspace execution list
```

### 5. 查看执行产物并生成报告

```bash
uv run ptest --path ./demo-workspace execution artifacts <execution_id>
uv run ptest --path ./demo-workspace report generate --format html
```

### 5.1 查看问题记录与恢复信息

当一次执行失败时，当前主线会自动沉淀问题记录：

```bash
uv run ptest --path ./demo-workspace problem list
uv run ptest --path ./demo-workspace problem show <problem_id>
uv run ptest --path ./demo-workspace problem assets <problem_id>
uv run ptest --path ./demo-workspace problem recover <problem_id>
```

### 6. 销毁工作区资源

```bash
uv run ptest env destroy --path ./demo-workspace
```

## Python API 快速开始

当前推荐使用 `PTestAPI`，它直接基于统一工作流服务工作。

```python
from pathlib import Path

from ptest.api import PTestAPI

workspace = Path("./demo-api-workspace")
api = PTestAPI(work_path=workspace)

api.init_environment()

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
    tags=["smoke"],
)

case_id = case_result["data"]["case_id"]
run_result = api.run_test_case(case_id)
print(run_result["status"])

records = api.list_execution_records()
print(records["data"])

report = api.generate_report(format_type="json")
print(report["data"]["report_path"])

problems = api.list_problem_records()
print(problems["data"])

if problems["data"]:
    problem_id = problems["data"][0]["problem_id"]
    recovery = api.recover_problem(problem_id)
    print(recovery["data"])

api.destroy_environment()
```

## 当前主线常用命令

```bash
uv run ptest --path ./demo-workspace status
uv run ptest --path ./demo-workspace case list
uv run ptest --path ./demo-workspace obj list
uv run ptest --path ./demo-workspace tool list
uv run ptest --path ./demo-workspace suite list
uv run ptest --path ./demo-workspace data types
```

## 当前已知边界

- `docs/plan/` 是内部文档区，不属于对外使用入口
- 本地 Docker 真实环境测试可能受网络和宿主机环境影响，真实 Docker 校验以 CI 为准
- 当前用户文档优先覆盖第一阶段主线，不承诺所有历史命令都继续可用

## 下一步阅读

- CLI / API 入口说明：[`README.md`](../../README.md)
- Python API 说明：[../api/python-api-guide.md](../api/python-api-guide.md)
- 环境管理专题：[../guides/environment-management.md](../guides/environment-management.md)
