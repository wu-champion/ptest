# ptest v1.12.0 发布说明

**发布日期**: 2026-06-12  
**版本**: 1.12.0  
**状态**: 正式发布

---

## 🎉 新功能

### P5-E Crash Evidence Bundle

本次发布新增了 Crash Evidence Bundle 能力，让测试工程师能够一键导出问题证据包，用于缺陷提交和问题调查。

#### 核心能力

1. **证据包导出**
   - 新增 `ptest problem bundle <problem_id>` 命令
   - 支持导出为 tar.gz 格式
   - 包含 manifest.json、problem_record.json、evidence.json 等关键文件

2. **证据收集**
   - 自动收集 crash_target、crash_event、dump_refs 等证据
   - 支持 process_result、core_environment 等进程信息
   - 支持 log_window、config_refs 等辅助信息

3. **Python API**
   - 新增 `export_problem_bundle()` 方法
   - 支持自定义输出路径
   - 返回导出结果和文件路径

#### 使用示例

```bash
# 导出证据包
ptest problem bundle prob_123

# 指定输出目录
ptest problem bundle prob_123 --output /tmp/evidence

# 查看证据包内容
tar -tzf bundle_prob_123.tar.gz
```

```python
from ptest.api import PTestAPI

api = PTestAPI(work_path="/path/to/workspace")

# 导出证据包
result = api.export_problem_bundle("prob_123")
print(result["data"]["archive_path"])
```

### 问题验证历史查询

本次发布新增了问题验证历史查询能力，让测试工程师能够追踪问题的验证状态和趋势。

#### 核心能力

1. **验证历史查询**
   - 新增 `ptest problem verify <problem_id>` 命令
   - 支持分页查询（`--limit` 和 `--offset`）
   - 返回验证记录列表和摘要信息

2. **趋势分析**
   - 自动计算验证趋势（reproduced/not_reproduced/recovered/inconclusive）
   - 统计复现次数和恢复次数
   - 提供最近复现时间和恢复时间

3. **Python API**
   - 新增 `get_problem_verification_runs()` 方法
   - 支持分页参数
   - 返回验证记录和摘要

#### 使用示例

```bash
# 查看验证历史
ptest problem verify prob_123

# 限制返回数量
ptest problem verify prob_123 --limit 5

# 分页查询
ptest problem verify prob_123 --limit 10 --offset 20
```

```python
from ptest.api import PTestAPI

api = PTestAPI(work_path="/path/to/workspace")

# 获取验证历史
result = api.get_problem_verification_runs("prob_123", limit=10)
print(result["data"]["summary"])
```

### 字段命名收口

本次发布完成了 problem 相关 API 的字段命名收口，提升 API 的可读性和一致性。

#### 核心改进

1. **字段映射**
   - `preservation_status` → `preservation_integrity`
   - `latest_action` → `last_recovery_action`
   - `object_refs` → `objects`
   - `artifact_refs` → `artifacts`
   - `log_refs` → `logs`

2. **向后兼容**
   - 旧字段始终保留
   - 新旧字段值完全相同
   - 添加 `_meta.field_aliases` 记录映射关系
   - 添加 `_meta.deprecated_fields` 标记废弃字段

#### 迁移指南

```python
# 旧代码
payload["preservation_status"]
payload["object_refs"]

# 新代码（推荐）
payload["preservation_integrity"]
payload["objects"]

# 旧代码仍然有效
payload["preservation_status"]  # 仍然可用
```

---

## 📈 改进

- 增强 `_problem_record_payload()`，应用字段映射
- 增强 `_problem_assets_payload()`，应用字段映射
- 增强 `_build_problem_asset_summary()`，应用字段映射
- CLI `ptest problem` 命令新增 `bundle` 和 `verify` 子命令

---

## 📊 质量指标

### 测试覆盖

- **单元测试**: 660 个测试用例通过
- **集成测试**: 9 个测试用例跳过
- **代码质量**: Ruff 和 MyPy 检查通过

### 新增测试

- REQ-003: 13 个字段映射测试用例
- REQ-001: 12 个 bundle 测试用例
- REQ-002: 18 个验证运行测试用例

---

## 📝 安装

```bash
pip install ptestx==1.12.0
```

## 📚 文档

- [发布说明](docs/releases/RELEASE_NOTES_v1.12.0.md)
- [API 文档](docs/api/python-api-guide.md)
- [用户指南](docs/user-guide/basic-usage.md)

---

## 🔄 升级指南

### 从 v1.11.0 升级

1. **更新包**:
   ```bash
   pip install --upgrade ptestx
   ```

2. **检查字段映射**:
   - 现有代码使用旧字段名仍然有效
   - 新代码建议使用新字段名

3. **使用新功能**:
   - 使用 `ptest problem bundle` 导出证据包
   - 使用 `ptest problem verify` 查看验证历史

### 兼容性

- **向后兼容**: 完全兼容 v1.11.0
- **数据迁移**: 无需数据迁移
- **配置变更**: 无需配置变更

---

## 📝 已知问题

无

---

## 🔮 后续计划

### 短期计划

1. **监控上线后表现**: 观察新功能在生产环境的表现
2. **收集用户反馈**: 了解用户对新功能的使用体验
3. **性能优化**: 根据实际使用情况优化性能

### 中期计划

1. **扩展功能**: 支持更多 problem 类型的证据包导出
2. **优化建议**: 根据用户反馈优化验证历史展示
3. **文档完善**: 补充使用文档和示例

---

## 🙏 致谢

感谢所有参与本次发布的团队成员：

- **架构师**: 技术设计和评审
- **产品专家**: 需求分析和验收
- **开发专家**: 功能开发和测试
- **测试专家**: 测试验证和质量保证

---

## 📞 支持

如有问题或建议，请通过以下方式联系：

- **GitHub Issues**: https://github.com/wu-champion/ptest/issues
- **文档**: https://ptest.readthedocs.io
- **邮箱**: support@ptest.dev

---

**发布日期**: 2026-06-12  
**版本**: 1.12.0  
**状态**: 正式发布
