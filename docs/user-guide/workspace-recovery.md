# workspace_recovery 最小恢复基线

本文档说明 `workspace_recovery` 当前阶段提供的能力边界。

当前它不是独立问题类型，也不是自动恢复命令。  
它是挂在已有问题恢复结果里的**工作区级最小恢复计划**，目标是回答：

- 当前问题影响了哪些对象
- 这些对象建议按什么动作恢复
- 恢复后应先做哪些验证

## 当前适用范围

当前 `workspace_recovery` 会跟随这些问题类型一起出现：

- `api_response`
- `data_state`
- `service_runtime`
- `crash_dump`

它提供的是：

- 最小受影响对象列表
- 推荐恢复动作
- 恢复顺序
- 恢复边界
- 恢复后验证建议

它**不提供**：

- 自动恢复执行
- 快照回滚
- 容器级恢复
- 跨工作区恢复

## 推荐理解方式

把 `workspace_recovery` 理解成：

- 不是“帮你恢复完成”
- 而是“把恢复计划组织清楚”

当前阶段的目标是把环境带回一个**可继续调查、可继续执行**的最小基线。

## 查看方式

先像平常一样处理问题：

```bash
ptest problem list --path /tmp/your-workspace
ptest problem show <problem_id> --path /tmp/your-workspace
ptest problem recover <problem_id> --path /tmp/your-workspace
```

重点查看：

- `problem show` 里的 `investigation.workspace_recovery`
- `problem recover` 里的 `workspace_recovery`

## 输出结构

当前你会看到类似结构：

```json
{
  "workspace_recovery": {
    "scope": "workspace_minimum_recovery",
    "affected_objects": [
      {
        "object_name": "demo_runtime_service",
        "object_type": "service",
        "current_status": "start_failed_preserved",
        "recommended_action": "reinstall"
      }
    ],
    "recommended_sequence": [
      "stabilize_problem_objects",
      "revalidate_runtime_or_data_paths"
    ],
    "recovery_boundary": {
      "scope": "workspace_minimum_recovery"
    },
    "post_recovery_checks": [
      {
        "action": "recheck_problem_objects"
      }
    ]
  }
}
```

## 当前动作含义

当前最常见的推荐动作包括：

- `restart`
  - 适合运行态问题或 crash 后的最小恢复
- `reset`
  - 适合数据状态问题下的对象级最小重置
- `reinstall`
  - 适合对象安装/启动已明显损坏的情况

这些动作当前只是**计划建议**，不是自动执行结果。

## 当前阶段边界

`workspace_recovery` 第一阶段的重点是：

- 统一恢复计划表达
- 统一对象动作推导
- 统一恢复后验证建议

后续如果进入更重的恢复阶段，才会继续考虑：

- 测试副作用导致的服务端环境恢复
- 快照恢复
- 容器级恢复

