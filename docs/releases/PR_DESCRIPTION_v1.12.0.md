# Pull Request: feat: v1.12.0 - Crash Evidence Bundle + 验证历史 + 字段命名收口

## 变更说明

### 新增功能

#### REQ-003: problem / replay 外层字段命名收口
- 新增 `PROBLEM_OUTPUT_SCHEMA` 字段映射表
- 新增 `_apply_output_schema()` 工具函数，支持向后兼容的字段重命名
- 在 `_problem_record_payload()` 中应用字段映射
- 在 `_problem_assets_payload()` 中应用字段映射
- 在 `_build_problem_asset_summary()` 中应用字段映射
- API 输出同时包含新旧字段名，确保向后兼容

**字段映射**:
- `preservation_status` → `preservation_integrity`
- `latest_action` → `last_recovery_action`
- `object_refs` → `objects`
- `artifact_refs` → `artifacts`
- `log_refs` → `logs`

#### REQ-001: P5-E Crash Evidence Bundle
- 新增 `src/ptest/app/bundle.py` 模块，提供证据包收集和导出功能
- 新增 `ptest problem bundle <problem_id>` 命令，导出问题证据包
- 新增 `export_problem_bundle()` Python API，支持程序化导出
- 证据包格式为 tar.gz，包含 manifest.json、problem_record.json、evidence.json 等

#### REQ-002: 问题差异对比与多次验证记录
- 新增 `ptest problem verify <problem_id>` 命令，查看验证历史
- 新增 `get_problem_verification_runs()` Python API，支持分页查询
- 验证历史包含趋势分析、复现状态、恢复状态等摘要信息

### 测试

- REQ-003: 13 个字段映射测试用例
- REQ-001: 12 个 bundle 测试用例
- REQ-002: 18 个验证运行测试用例
- 总计: 660 个单元测试通过

### 代码质量

- ✅ Ruff 代码检查通过
- ✅ Ruff 格式检查通过（141 个文件）
- ✅ MyPy 类型检查通过（76 个文件）
- ✅ 单元测试通过（660 个测试）

---

## 版本更新

- 版本号: 1.11.0 → 1.12.0
- 更新 CHANGELOG
- 创建发布说明
- 创建 Release Notes

---

## 测试验证

```bash
# 运行所有单元测试
uv run pytest tests/unit/ -v

# 代码质量检查
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/ --ignore-missing-imports

# 测试新增功能
uv run pytest tests/unit/problem/test_field_mapping.py -v
uv run pytest tests/unit/problem/test_bundle.py -v
uv run pytest tests/unit/problem/test_verification_runs.py -v
```

---

## 发布说明

**版本**: 1.12.0
**日期**: 2026-06-12
**主要功能**:
- P5-E Crash Evidence Bundle
- 问题验证历史查询
- 字段命名收口

---

**注意**: 合并后会自动触发发布流程，无需手动创建 tag。
