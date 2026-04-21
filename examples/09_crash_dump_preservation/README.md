# 示例 9: crash_dump 最小保全链路

本示例展示如何用一个轻量本地服务验证 `crash_dump` 第一阶段：

- 服务先正常监听
- 触发一次连接后退出
- 同时生成一个受控 dump 文件
- `ptest` 将这次失败识别为 `crash_dump` problem

## 目录内容

- `demo.sh`
  一键跑通最小演示流程
- `service/crash_once_server.py`
  轻量本地崩溃服务

## 快速开始

```bash
bash examples/09_crash_dump_preservation/demo.sh
```

如果你想手动执行，请阅读：

- [docs/user-guide/crash-dump-preservation.md](../../docs/user-guide/crash-dump-preservation.md)

## 这个案例验证什么

1. `crash_dump` problem 能否稳定生成
2. dump/core 引用是否会被保全
3. `problem assets` 是否能给出最小严重故障摘要
4. `problem recover` 是否能给出最小调查计划
5. 当前边界是否明确为“保全优先”，而不是完整 crash 分析平台
