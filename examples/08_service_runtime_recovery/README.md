# 示例 8: service_runtime 最小恢复链路

本示例展示如何用一个未监听的本地端口，验证 `service_runtime` 主线的最小可用闭环：

- 服务端口不可达时，如何生成 `service_runtime` problem
- `problem assets` 如何提供运行时线索
- `problem recover` 如何给出结构化最小恢复计划
- `problem show` 如何通过统一 `investigation` 视图收敛重点信息

## 目录内容

- `demo.sh`
  一键跑通最小演示流程

## 快速开始

```bash
bash examples/08_service_runtime_recovery/demo.sh
```

如果你想手动执行，请阅读：

- [docs/user-guide/service-runtime-recovery.md](../../docs/user-guide/service-runtime-recovery.md)

## 这个案例验证什么

1. `service_runtime` 问题能否稳定生成
2. `problem assets` 是否能提供 `failure_kind / runtime_hints / investigation`
3. `problem recover` 是否能给出 `recommended_checks / suggested_repairs / next_actions`
4. 当前能力是“最小恢复计划”，不是自动恢复、dump 分析或历史运行时重建
