# 示例 6: 轻量状态型 API replay 验证

本示例展示如何用一个仓库内自给的轻量状态型 API 服务，验证：

- 普通 `api_response` 问题如何被记录、查看和 replay
- 前置状态变化导致的隐性依赖问题，为什么在单独 replay 时可能不再复现

## 目录内容

- `service/stateful_api_server.py`
  本地轻量状态型 API 服务
- `cases/01_direct_body_mismatch.json`
  直接失败的 API case
- `cases/02_enable_hidden_failure.json`
  前置状态切换 case
- `cases/03_orders_after_hidden_state.json`
  受前置状态影响而失败的 case
- `demo.sh`
  一键跑通最小演示流程

## 快速开始

```bash
bash examples/06_stateful_api_replay/demo.sh
```

如果你想手动执行，请阅读：

- [docs/user-guide/stateful-api-replay.md](../../docs/user-guide/stateful-api-replay.md)

## 这个案例验证什么

1. `problem assets` 是否能输出可转交的复现材料
2. `problem replay` 是否能告诉你问题是否仍然复现
3. `comparison.summary` / `comparison.highlights` 是否足够解释变化
4. 当前 replay 只是 `request-level replay`，不会自动重建历史前置状态
