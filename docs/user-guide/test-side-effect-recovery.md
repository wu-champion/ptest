# 测试副作用导致的环境恢复

本文档说明当前 `ptest` 对“测试副作用导致的服务端环境偏移”提供的最小恢复能力。

当前场景是：

- 服务或数据起始状态正常
- 前置 case 修改了服务端状态、数据或运行态
- 后置 case 因环境已偏离基线而失败

当前阶段的目标不是自动回滚环境，而是把下面三件事表达清楚：

- 疑似哪个前置 case 触发了环境偏移
- 当前更像哪类副作用
- 下一步最小恢复计划是什么

## 当前覆盖范围

当前这批已经接入：

- `api_response`
- `service_runtime`
- `data_state`

当前仍未接入：

- `crash_dump`

## 查看方式

仍然使用现有问题入口：

```bash
ptest problem show <problem_id> --path /tmp/your-workspace
ptest problem assets <problem_id> --path /tmp/your-workspace
ptest problem recover <problem_id> --path /tmp/your-workspace
```

重点查看：

- `side_effect`
- `environment_recovery`
- `workspace_recovery`

## 当前输出重点

### `side_effect`

用于表达副作用线索，当前会给出：

- `classification`
- `signal_strength`
- `environment_shift_detected`
- `likely_trigger_case_id`
- `candidate_case_ids`
- `reason`

当前常见分类包括：

- `possible_request_side_effect`
- `possible_runtime_destabilization`
- `possible_data_pollution`
- `no_recent_side_effect_signal`

### `environment_recovery`

用于表达最小环境恢复计划，当前会给出：

- `scope = workspace_side_effect_minimum_recovery`
- `assessment`
- `confidence`
- `likely_trigger_case_id`
- `affected_objects`
- `recommended_sequence`

### `workspace_recovery`

`environment_recovery` 不是替代 `workspace_recovery`，而是在其上补充“为什么要这样恢复”的副作用视角。

## 当前边界

当前阶段只提供：

- 最小因果线索
- 最小环境偏移摘要
- 最小恢复计划

当前不提供：

- 自动恢复执行
- 快照恢复
- 容器级回滚
- 多服务复杂污染恢复
- 全量时间点恢复

## 推荐理解方式

当前能力更适合这样理解：

- 不是“系统已经帮你恢复完”
- 而是“系统已经把副作用线索和最小恢复路径组织出来”

这能明显降低“环境为什么突然不可信”这类问题的定位成本。

