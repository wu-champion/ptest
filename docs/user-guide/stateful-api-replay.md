# 轻量状态型 API replay 验证

本案例用一个仓库内自带的轻量状态型 API 服务，验证两件事：

1. `ptest` 如何记录、展示并 replay 一个普通的接口问题
2. 当失败由前置状态变化触发时，为什么单独 replay 后置请求可能不再复现

这个案例是“所见即所得”的：按下面步骤执行，你应该能看到和文档一致的结果。

## 适用场景

适合你想快速确认这些能力是否已经可用：

- `problem assets`
- `reproduction_summary`
- `problem replay`
- `comparison.summary`
- `comparison.highlights`
- `comparison.summary.boundary`

## 前置要求

- 你已经在仓库根目录
- 本地可执行 `python3`
- 已安装当前仓库的运行依赖

本文默认使用固定地址：

- Host: `127.0.0.1`
- Port: `18090`

## 第 1 步：启动本地状态型 API 服务

在终端 A 中执行：

```bash
python3 examples/06_stateful_api_replay/service/stateful_api_server.py --host 127.0.0.1 --port 18090
```

启动后你会看到类似输出：

```json
{"status": "serving", "host": "127.0.0.1", "port": 18090, "service": "stateful_api_replay"}
```

保持这个终端不要关闭。

## 第 2 步：初始化工作区

在终端 B 中执行：

```bash
ptest init --path /tmp/ptest-stateful-api-replay
```

## 第 3 步：导入 3 个验证 case

```bash
ptest case add direct_body_mismatch \
  --file examples/06_stateful_api_replay/cases/01_direct_body_mismatch.json \
  --path /tmp/ptest-stateful-api-replay

ptest case add enable_hidden_failure \
  --file examples/06_stateful_api_replay/cases/02_enable_hidden_failure.json \
  --path /tmp/ptest-stateful-api-replay

ptest case add orders_after_hidden_state \
  --file examples/06_stateful_api_replay/cases/03_orders_after_hidden_state.json \
  --path /tmp/ptest-stateful-api-replay
```

## 第 4 步：验证普通 API 失败

先运行一个“直接失败”的接口 case：

```bash
ptest case run direct_body_mismatch --path /tmp/ptest-stateful-api-replay
```

它会失败，因为服务返回的是正常订单结果，而 case 故意期望了错误的响应摘要。

查看问题记录：

```bash
ptest problem list --case-id direct_body_mismatch --path /tmp/ptest-stateful-api-replay
```

从输出里记下 `problem_id`，然后继续：

```bash
ptest problem assets <problem_id> --path /tmp/ptest-stateful-api-replay
ptest problem replay <problem_id> --path /tmp/ptest-stateful-api-replay
```

你应该重点看这些字段：

- `assets.reproduction_summary`
- `assets.reproduction_summary.dependency_hints`
- `replay.comparison.summary`
- `replay.comparison.highlights`
- `replay.comparison.summary.boundary`

这个场景里，问题通常会继续复现，因为它不是由历史状态污染触发的，而是一个可稳定重现的请求/期望不匹配。

## 第 5 步：验证隐性依赖导致的后置失败

先运行前置状态切换 case：

```bash
ptest case run enable_hidden_failure --path /tmp/ptest-stateful-api-replay
```

它会把服务切换到“下一次访问 `/api/orders` 时返回异常状态”的模式，但它自己不会失败。

再运行受前置影响的 case：

```bash
ptest case run orders_after_hidden_state --path /tmp/ptest-stateful-api-replay
```

这一次会失败。继续查看问题记录：

```bash
ptest problem list --case-id orders_after_hidden_state --path /tmp/ptest-stateful-api-replay
```

记下新的 `problem_id`，然后执行：

```bash
ptest problem assets <problem_id> --path /tmp/ptest-stateful-api-replay
ptest problem replay <problem_id> --path /tmp/ptest-stateful-api-replay
```

## 第 6 步：理解 replay 结果

这个场景里，前置 case 触发的是“一次性状态变化”：

- 第一次 `GET /api/orders` 会因为前置状态而返回异常结果
- 这个异常结果被消费后，服务会恢复正常

所以你在单独 replay `orders_after_hidden_state` 对应的问题时，通常会看到：

- `comparison.highlights` 提示“这次 replay 已不再复现原问题”
- `comparison.summary.reproduced` 为 `false`
- `comparison.summary.boundary.scope` 为 `request_level`
- `comparison.summary.boundary.hidden_dependency_possible` 为 `true`
- `comparison.summary.boundary.dependency_hints.candidate_case_ids` 里会出现 `enable_hidden_failure`
- `comparison.summary.boundary.recommended_actions` 会提示你先检查最近前置 case，再按顺序重跑候选前置 case

这正是当前边界要表达的内容：

- 现在的 `api_response replay` 是 `request-level replay`
- 它会重新发起请求并对比结果
- 它不会自动重建之前 case 带来的历史状态

## 推荐观察点

如果你只想快速判断这套能力是不是对你有帮助，建议重点看：

1. `ptest problem assets <problem_id>`
   看 `reproduction_summary`
2. `ptest problem replay <problem_id>`
   看 `comparison.summary`
3. `ptest problem replay <problem_id>`
   再看 `comparison.highlights`
4. `ptest problem replay <problem_id>`
   补看 `comparison.summary.boundary`

## 一键演示

如果你不想手动敲全部命令，也可以直接执行：

```bash
bash examples/06_stateful_api_replay/demo.sh
```

它会自动：

- 启动本地服务
- 初始化工作区
- 导入 3 个 case
- 运行普通失败和隐性依赖场景
- 输出对应的问题列表

## 这个案例没有覆盖什么

这个案例不会验证：

- 完整历史环境恢复
- 前置 case 链自动重建
- 数据快照恢复
- 更重的数据库/服务对象级状态回放

如果你遇到的是“前置步骤污染状态，单独 replay 后置请求不足以复现”的问题，这个案例正是用来说明当前 replay 边界的。
