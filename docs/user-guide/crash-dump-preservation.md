# crash_dump 最小保全链路

本文档演示 `crash_dump` 第一阶段的最小可验证链路。

目标不是自动分析 core，也不是自动恢复服务，而是验证：

- 严重故障发生后，系统能否生成 `crash_dump` problem
- `problem assets` 能否保留 dump/core 引用和最小严重故障摘要
- `problem recover` 能否给出最小调查计划
- `problem show` 能否通过统一 `investigation` 视图收敛重点信息

## 适用场景

当前这一批最小覆盖的是：

- 服务原本可以运行
- 触发一次连接后异常退出
- 同时在受控目录下生成一个 dump/core 文件引用

本批不覆盖：

- 真实 ELF core 解析
- 栈符号化
- 自动回放 crash
- 自动恢复服务

## 一键演示

```bash
bash examples/09_crash_dump_preservation/demo.sh
```

## 手动执行步骤

### 1. 初始化工作区

```bash
ptest init --path /tmp/ptest-crash-dump-demo
```

### 2. 启动一个 one-shot 崩溃服务

这个服务会：

- 监听一个本地端口
- 接受一次连接
- 退出并生成一个伪 dump 文件

先找一个空闲端口：

```bash
python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
```

假设输出 `45679`，然后启动服务：

```bash
python3 examples/09_crash_dump_preservation/service/crash_once_server.py \
  127.0.0.1 45679 /tmp/ptest-crash-dump-demo/demo_service.core &
```

### 3. 准备一个 `service` case

```json
{
  "type": "service",
  "service_name": "demo_crash_service",
  "check_type": "port",
  "host": "127.0.0.1",
  "port": 45679,
  "timeout": 1,
  "expected_runtime_state": "running",
  "dump_paths": ["/tmp/ptest-crash-dump-demo/demo_service.core"]
}
```

导入 case：

```bash
ptest case add service_crash_dump_check \
  --file /path/to/crash_dump_case.json \
  --path /tmp/ptest-crash-dump-demo
```

### 4. 触发服务退出并生成 dump

```bash
python3 -c 'import socket; s=socket.create_connection(("127.0.0.1", 45679), timeout=1); s.close()'
```

这一步之后，服务会退出，并在指定路径生成一个伪 dump 文件。

### 5. 运行 case 并触发 `crash_dump`

```bash
ptest case run service_crash_dump_check --path /tmp/ptest-crash-dump-demo
```

预期结果：

- case 失败
- 系统自动保留一条 `crash_dump` problem

### 6. 查看问题列表

```bash
ptest problem list --case-id service_crash_dump_check --path /tmp/ptest-crash-dump-demo
```

记录返回的 `problem_id`。

### 7. 查看保全材料

```bash
ptest problem assets <problem_id> --path /tmp/ptest-crash-dump-demo
```

重点看这些字段：

- `details.crash_target`
- `details.dump_refs`
- `investigation.crash_summary`
- `investigation.dump_refs`
- `investigation.boundary`

你应该能看到：

- 服务目标信息
- dump/core 路径引用
- 当前 dump 是否存在
- 当前边界是 `crash_asset_preservation`

### 8. 查看恢复计划

```bash
ptest problem recover <problem_id> --path /tmp/ptest-crash-dump-demo
```

重点看这些字段：

- `mode`
- `recommended_checks`
- `next_actions`
- `boundary`

你应该能看到：

- 当前模式是 `crash_dump_investigation`
- 先检查 dump/core 文件
- 再检查最近运行日志
- 当前只是最小调查计划，不代表已经完成 crash 根因分析

### 9. 查看统一调查摘要

```bash
ptest problem show <problem_id> --path /tmp/ptest-crash-dump-demo
```

重点看：

- `investigation.crash_target`
- `investigation.crash_summary`
- `investigation.dump_refs`
- `investigation.boundary`
- `investigation.next_actions`

## 当前能力边界

当前 `crash_dump` 第一阶段只提供：

- 严重故障问题建模
- dump/core 引用保全
- 最小调查计划
- 统一调查摘要

当前**不提供**：

- core 文件深解析
- 崩溃栈分析
- 自动恢复服务
- 自动回放 crash
- 工作区级 core 自动捕获
- dump/core 自动发现与自动挂接

也就是说，当前目标是先把严重故障资产稳定接住，而不是一步做到完整 crash 平台。

## Dump Summary (P5-B)

当 `dump_paths` 或自动发现的 dump 文件存在时，ptest 会为每个 ref 生成轻量摘要：

- **file_type**: `elf_core`、`minidump`、`archive`、`text_dump` 或 `unknown`（通过 magic 字节或扩展名识别）
- **hash_sha256_prefix**: sha256 十六进制前 16 位（流式计算，最多 16MB）
- **detected_by**: `magic`、`extension`、`archive_probe` 或 `fallback`
- **warnings**: `empty_file`、`file_missing`、`permission_denied`、`archive_probe_failed` 等

对于压缩包文件（`.zip`、`.tar`、`.tar.gz`、`.tgz`），ptest 只读取目录（不解压），报告：

- `entry_count`、`sample_entries`（最多 20 条）、`total_uncompressed_size`、`truncated`

当 dump refs 超过 20 个时，超出部分标记 `summary_status=skipped`，warnings 包含 `dump_ref_summary_limit_reached`。

`problem assets.details`、`problem show` investigation 和 `problem recover` 都包含聚合摘要 `dump_summary`：

```json
{
  "dump_summary": {
    "total_count": 2,
    "available_count": 1,
    "unavailable_count": 1,
    "types": {"elf_core": 1, "unknown": 1},
    "has_archive": false,
    "warnings": ["file_missing"]
  }
}
```

ptest **不会**解析 core 内容、符号化栈或解压压缩包。摘要纯粹是元数据，用于判断是否值得继续调查。
