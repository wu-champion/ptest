# 示例 7: SQLite data_state 最小恢复链路

本示例展示如何用一个本地 SQLite 数据库，验证 `data_state` 主线的最小可用闭环：

- 查询结果值不匹配时，如何生成 `data_state` problem
- 查询结果缺少记录时，如何生成 `data_state` problem
- `problem assets` 如何提供状态线索
- `problem recover` 如何给出结构化最小恢复计划
- `problem show` 如何通过统一 `investigation` 视图收敛重点信息

## 目录内容

- `scripts/prepare_sqlite_state_demo.py`
  初始化 SQLite 数据库并生成 demo 用例文件
- `demo.sh`
  一键跑通最小演示流程

## 快速开始

```bash
bash examples/07_sqlite_data_state_recovery/demo.sh
```

如果你想手动执行，请阅读：

- [docs/user-guide/sqlite-data-state-recovery.md](../../docs/user-guide/sqlite-data-state-recovery.md)

## 这个案例验证什么

1. `data_state` 问题能否稳定生成
2. `problem assets` 是否能提供 `failure_kind / state_hints / investigation`
3. `problem recover` 是否能给出 `recommended_queries / suggested_repairs / next_actions`
4. 当前能力是“最小恢复计划”，不是自动修库或历史状态重建
