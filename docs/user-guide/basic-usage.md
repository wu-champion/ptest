# ptest 快速开始

本文档只覆盖当前主线已经稳定支持的最小闭环：

`环境初始化 -> 对象安装与启动 -> 用例创建与执行 -> 执行记录与报告 -> 环境销毁`

## 环境要求

- Python 3.12+
- 建议使用 `uv`
- Docker 属于可选能力，本地快速开始不依赖它

## 安装

如果你是作为框架使用者来使用 `ptest`，推荐直接安装：

```bash
pip install ptestx
ptest --version
```

如果你是在源码仓库里开发或验证当前项目，推荐使用：

```bash
uv sync
uv run ptest --version
```

下面的 CLI 示例默认按“已经安装完成，可以直接使用 `ptest` 命令”的方式来写。  
如果你是在源码仓库里操作，只需要把 `ptest` 替换成 `uv run ptest` 即可。

## CLI 快速开始

以下示例使用一个 SQLite 数据库用例来打通当前 MVP 主线。

### 1. 初始化工作区

```bash
ptest init --path ./demo-workspace
ptest workspace status
ptest env status
```

`ptest init --path ...` 成功后，会自动把这个工作区设为活动工作区。
后续工作区内业务命令如果没显式传 `--path`，会按下面的顺序解析：

1. `--path`
2. 当前目录工作区
3. 活动工作区

你也可以随时查看或切换：

```bash
ptest workspace use ./demo-workspace
ptest workspace status
```

### 2. 安装并启动对象

```bash
ptest obj install db demo_db --database ./demo.db --driver sqlite
ptest obj start demo_db
ptest obj status demo_db
```

### 3. 添加测试用例

`case add` 当前要求通过 `--data` 或 `--file` 提供 JSON。

```bash
ptest case add sqlite_smoke --data '{
  "type": "database",
  "db_type": "sqlite",
  "database": "./demo.db",
  "query": "SELECT 1 as value",
  "expected_result": [{"value": 1}]
}'
```

### 4. 执行测试

```bash
ptest case run sqlite_smoke
ptest execution list
ptest exec list
```

### 5. 查看执行产物并生成报告

```bash
ptest execution artifacts <execution_id>
ptest report generate --format html
```

### 5.1 查看问题记录与恢复信息

当一次执行失败时，当前主线会自动沉淀问题记录：

```bash
ptest problem list
ptest problem show <problem_id>
ptest problem assets <problem_id>
ptest problem recover <problem_id>
```

### 6. 销毁工作区资源

```bash
cd ..
ptest env destroy --path ./demo-workspace
```

这里仍然建议显式写 `--path`，因为销毁属于工作区生命周期收尾动作，不会隐式回退到活动工作区。

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
ptest status
ptest workspace status
ptest case list
ptest obj list
ptest tool list
ptest suite list
ptest data types
ptest exec list
```

如果你是在自动化脚本里，或者要跨多个工作区操作，再显式加上 `--path` 会更稳。
如果你只是在单机上持续操作同一个工作区，活动工作区可以帮你减少很多 `--path` 的重复输入。

## 当前已知边界

- `docs/plan/` 是内部文档区，不属于对外使用入口
- 本地 Docker 真实环境测试可能受网络和宿主机环境影响，真实 Docker 校验以 CI 为准
- MySQL 主案例当前依赖 `host` runtime backend，需要执行环境允许真实进程启动和 TCP 端口绑定
- 当前用户文档优先覆盖第一阶段主线，不承诺所有历史命令都继续可用

## 下一步阅读

- CLI / API 入口说明：[`README.md`](../../README.md)
- MySQL 主案例实践：[mysql-full-lifecycle.md](mysql-full-lifecycle.md)
- Python API 说明：[../api/python-api-guide.md](../api/python-api-guide.md)
- 环境管理专题：[../guides/environment-management.md](../guides/environment-management.md)
