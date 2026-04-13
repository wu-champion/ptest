# SQLite data_state 最小恢复链路

本案例用一个本地 SQLite 数据库，验证 `ptest` 如何在数据状态问题出现后，给出可执行的最小恢复调查信息。

这个案例会展示两种最常见的问题：

1. `value_mismatch`
   查询到了目标记录，但关键字段值不符合预期
2. `missing_rows`
   查询结果中缺少原本应该出现的记录

按下面步骤执行，你应该能稳定看到和文档一致的结果。

## 适用场景

适合你想快速确认这些能力是否已经可用：

- `problem list`
- `problem show`
- `problem assets`
- `problem recover`
- `investigation`
- `recovery.failure_kind`
- `recovery.state_hints`
- `recovery.recommended_queries`
- `recovery.suggested_repairs`
- `recovery.next_actions`

## 前置要求

- 你已经在仓库根目录
- 本地可执行 `python3`
- 当前仓库依赖已安装

## 第 1 步：初始化工作区

```bash
ptest init --path /tmp/ptest-sqlite-data-state
```

## 第 2 步：准备 SQLite 数据库和案例文件

```bash
python3 examples/07_sqlite_data_state_recovery/scripts/prepare_sqlite_state_demo.py \
  --workspace /tmp/ptest-sqlite-data-state
```

这一步会创建：

- `/tmp/ptest-sqlite-data-state/orders.db`
- `/tmp/ptest-sqlite-data-state/generated_cases/01_order_state_mismatch.json`
- `/tmp/ptest-sqlite-data-state/generated_cases/02_missing_order.json`

初始数据库里会有两条记录：

- `ORD-100`，状态是 `pending`
- `ORD-200`，状态是 `ready`

## 第 3 步：导入 2 个验证 case

```bash
ptest case add sqlite_state_mismatch \
  --file /tmp/ptest-sqlite-data-state/generated_cases/01_order_state_mismatch.json \
  --path /tmp/ptest-sqlite-data-state

ptest case add sqlite_missing_order \
  --file /tmp/ptest-sqlite-data-state/generated_cases/02_missing_order.json \
  --path /tmp/ptest-sqlite-data-state
```

## 第 4 步：触发 value_mismatch

先运行第一条 case：

```bash
ptest case run sqlite_state_mismatch --path /tmp/ptest-sqlite-data-state
```

这条 case 会失败，因为数据库中 `ORD-100` 的真实状态是 `pending`，但 case 期望它是 `ready`。

继续查看问题列表：

```bash
ptest problem list --case-id sqlite_state_mismatch --path /tmp/ptest-sqlite-data-state
```

记下 `problem_id`，然后执行：

```bash
ptest problem show <problem_id> --path /tmp/ptest-sqlite-data-state
ptest problem assets <problem_id> --path /tmp/ptest-sqlite-data-state
ptest problem recover <problem_id> --path /tmp/ptest-sqlite-data-state
```

你应该重点看这些字段：

- `problem.investigation.failure_kind`
- `problem.investigation.state_hints`
- `assets.details.actual_result`
- `assets.recovery.recommended_queries`
- `assets.recovery.suggested_repairs`
- `recovery.next_actions`

这个场景里，你会看到：

- `failure_kind` 是 `value_mismatch`
- `state_hints.mismatched_fields` 里包含 `state`
- `suggested_repairs[0].action` 是 `align_key_field_values`

这说明当前最小恢复计划认为：

- 目标记录是存在的
- 主要问题不是缺记录，而是关键字段值不一致
- 下一步应先重跑保全查询，再修正关键字段值

## 第 5 步：触发 missing_rows

再运行第二条 case：

```bash
ptest case run sqlite_missing_order --path /tmp/ptest-sqlite-data-state
```

这条 case 会失败，因为查询期望找到 `ORD-404`，但当前数据库里根本没有这条记录。

继续查看问题列表：

```bash
ptest problem list --case-id sqlite_missing_order --path /tmp/ptest-sqlite-data-state
```

记下新的 `problem_id`，然后执行：

```bash
ptest problem assets <problem_id> --path /tmp/ptest-sqlite-data-state
ptest problem recover <problem_id> --path /tmp/ptest-sqlite-data-state
```

这个场景里，你会看到：

- `failure_kind` 是 `missing_rows`
- `state_hints.missing_row_count` 会指出缺少的记录数
- `suggested_repairs[0].action` 是 `insert_minimal_required_rows`

这说明当前最小恢复计划认为：

- 先确认是不是查错了数据源或条件
- 如果查询和数据源都没问题，再补建最小必需记录

## 第 6 步：如何理解当前恢复边界

这条 `data_state` 主线当前提供的是：

- 失败时的状态线索保全
- 结构化最小恢复计划
- 统一调查摘要入口

它当前**不会**做这些事：

- 自动改库
- 自动插入/删除/更新数据
- 自动重建完整历史数据库状态
- 自动分析复杂跨表依赖链

所以你应该把 `problem recover` 理解成：

- 一份恢复调查计划
- 一份最小修正建议
- 一份帮助你快速确认下一步的结构化摘要

而不是“已经自动修复数据”。

## 推荐观察点

如果你只想快速判断这条能力链是不是够用，建议重点看：

1. `ptest problem show <problem_id>`
   先看 `investigation`
2. `ptest problem assets <problem_id>`
   再看 `details.actual_result` 和 `recovery`
3. `ptest problem recover <problem_id>`
   最后看 `suggested_repairs` 和 `next_actions`

## 一键演示

如果你不想手动敲全部命令，也可以直接执行：

```bash
bash examples/07_sqlite_data_state_recovery/demo.sh
```

它会自动：

- 初始化工作区
- 准备 SQLite 数据库
- 生成案例文件
- 导入两个失败 case
- 输出对应的 `problem assets / recover / show`

## 这个案例没有覆盖什么

这个案例不会验证：

- 自动恢复数据库状态
- 快照与回滚
- 多数据源联合恢复
- MySQL 等更重资源场景

它的目标只有一个：证明 `data_state` 这条最小恢复链路已经可以实际使用。
