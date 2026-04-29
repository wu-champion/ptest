# service_runtime 最小恢复链路

本文档演示 `service_runtime` 这一类问题的最小可验证链路。

目标不是自动恢复服务，而是验证：

- 运行时故障发生后，系统能否生成 `service_runtime` problem
- `problem assets` 能否给出清楚的运行时线索
- `problem recover` 能否给出结构化最小恢复计划
- `problem show` 能否通过统一 `investigation` 视图收敛重点信息

## 适用场景

当前这一批最小覆盖的是：

- 服务未启动
- 服务启动失败
- 服务异常退出
- 健康检查失败
- 端口不可达

本案例使用**端口不可达**来验证整条链路，因为它最轻量，不依赖外部服务资产。

## 一键演示

```bash
bash examples/08_service_runtime_recovery/demo.sh
```

## 手动执行步骤

### 1. 初始化工作区

```bash
ptest init --path /tmp/ptest-service-runtime-demo
```

### 2. 准备一个未监听的本地端口

下面的命令会输出一个当前空闲端口：

```bash
python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
```

假设输出端口为 `45678`。

### 3. 新建一个 `service` case

```json
{
  "type": "service",
  "service_name": "demo_runtime_service",
  "check_type": "port",
  "host": "127.0.0.1",
  "port": 45678,
  "timeout": 1
}
```

导入 case：

```bash
ptest case add service_runtime_port_unreachable --file /path/to/service_case.json --path /tmp/ptest-service-runtime-demo
```

### 4. 运行 case 并触发失败

```bash
ptest case run service_runtime_port_unreachable --path /tmp/ptest-service-runtime-demo
```

预期结果：

- case 失败
- 失败原因是本地端口不可达
- 系统自动保留一条 `service_runtime` problem

### 5. 查看问题列表

```bash
ptest problem list --case-id service_runtime_port_unreachable --path /tmp/ptest-service-runtime-demo
```

记录返回的 `problem_id`。

### 6. 查看保全材料

```bash
ptest problem assets <problem_id> --path /tmp/ptest-service-runtime-demo
```

重点看这些字段：

- `details.failure_kind`
- `details.runtime_hints`
- `investigation.runtime_target`
- `investigation.failure_kind`
- `investigation.boundary`

你应该能看到：

- `failure_kind = port_unreachable`
- 目标 host / port
- 当前问题只是运行时观察结果，不等于历史上下文重建

### 7. 查看恢复计划

```bash
ptest problem recover <problem_id> --path /tmp/ptest-service-runtime-demo
```

重点看这些字段：

- `recommended_checks`
- `suggested_repairs`
- `next_actions`
- `boundary`

你应该能看到：

- 先检查端口和服务状态
- 再检查最近日志
- 当前建议属于 `runtime_level_plan`

### 8. 查看统一调查摘要

```bash
ptest problem show <problem_id> --path /tmp/ptest-service-runtime-demo
```

重点看：

- `investigation.runtime_target`
- `investigation.failure_kind`
- `investigation.runtime_hints`
- `investigation.boundary`
- `investigation.next_actions`

## 当前能力边界

当前 `service_runtime` 恢复能力明确只提供：

- 运行时线索保全
- 最小恢复计划
- 统一调查摘要

当前**不提供**：

- 自动重启 / 自动恢复执行
- dump / core 深诊断
- CPU / 内存 / 线程级分析
- 跨服务依赖恢复
- 历史运行时上下文重建

也就是说，当前目标是让运行时问题更容易被理解和继续调查，而不是一键修复服务。
