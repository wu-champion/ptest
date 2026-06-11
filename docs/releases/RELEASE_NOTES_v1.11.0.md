# ptest v1.11.0 发布说明

**发布日期**: 2026-06-11  
**版本**: 1.11.0  
**状态**: 正式发布

---

## 🎉 新功能

### P5-D 受管对象 Crash 联动

本次发布新增了受管对象 Crash 联动能力，让测试工程师能够更高效地调查和处理对象 crash 问题。

#### 核心能力

1. **Crash 后自动状态更新**
   - native case 异常退出后，关联对象状态自动更新为 `crash_preserved`
   - 自动记录 crash 时间、execution_id、problem_id
   - 支持 crash_count 累计和 crash_history 记录（保留最近 10 条）

2. **对象状态展示 Crash 信息**
   - `ptest obj status <name>` 现在展示最近 crash 信息
   - 显示 crash 时间、crash_count、关联的 problem_id、dump 目录

3. **对象关联问题查询**
   - 新增 `ptest obj issues <name>` 命令
   - 支持按 problem 类型过滤：`--type crash_dump`
   - 支持限制返回数量：`--limit 10`

4. **对象级恢复建议**
   - `problem recover` 现在提供对象级恢复建议
   - 根据 crash 类型（SIGSEGV、SIGABRT）提供建议
   - 提供可执行的命令示例

#### 使用示例

```bash
# 查看对象状态（包含 crash 信息）
ptest obj status mysql_demo

# 查看对象关联的问题
ptest obj issues mysql_demo

# 按类型过滤问题
ptest obj issues mysql_demo --type crash_dump

# 限制返回数量
ptest obj issues mysql_demo --limit 5

# 查看问题恢复建议
ptest problem recover prob_xxx
```

#### Python API

```python
from ptest.api import PTestAPI

api = PTestAPI(work_path="/path/to/workspace")

# 获取对象 crash 信息
crash_info = api.get_object_crash_info("mysql_demo")

# 列出对象关联的问题
issues = api.list_object_issues("mysql_demo", problem_type="crash_dump", limit=10)
```

---

## 📈 改进

### 对象状态扩展

- 新增 `crash_preserved` 对象状态
- 扩展 `OBJECT_FAILURE_PRESERVED_STATUSES`，包含 `crash_preserved`
- 扩展 `OBJECT_CLEARABLE_STATUSES`，支持清除 `crash_preserved` 状态
- 扩展 `OBJECT_RESETTABLE_STATUSES`，支持重置 `crash_preserved` 状态

### 恢复计划增强

- 增强 `_build_crash_dump_recovery_plan`，包含对象级恢复建议
- 增强 `_build_object_status_payload`，包含 crash 信息

---

## 🔧 技术细节

### 数据模型

#### Object Status

```python
OBJECT_STATUS_CRASH_PRESERVED = "crash_preserved"
```

#### Crash Capture 元数据

```python
{
    "last_crash_time": "2026-06-11T10:00:00",
    "last_execution_id": "exec_xxx",
    "last_problem_id": "prob_xxx",
    "crash_count": 3,
    "dump_dir": "/workspace/dumps",
    "crash_history": [
        {
            "time": "2026-06-11T10:00:00",
            "execution_id": "exec_xxx",
            "problem_id": "prob_xxx",
            "signal": "SIGABRT",
            "returncode": -6
        }
    ]
}
```

### 新增方法

#### WorkflowService

- `_update_object_after_crash()`: crash 后更新对象状态
- `list_object_issues()`: 列出对象关联的 problem
- `get_object_crash_info()`: 获取对象 crash 联动信息
- `_build_object_crash_recommendations()`: 构建对象 crash 恢复建议

#### PTestAPI

- `get_object_crash_info()`: 获取对象 crash 联动信息
- `list_object_issues()`: 列出对象关联的 problem

### CLI 命令

- `ptest obj issues <name>`: 列出对象关联的问题
  - `--type`: 按 problem 类型过滤
  - `--limit`: 限制返回数量

---

## 📊 质量指标

### 测试覆盖

- **单元测试**: 21 个新增测试用例，100% 通过
- **集成测试**: 614 个测试用例通过，9 个跳过
- **代码质量**: Ruff 和 MyPy 检查通过

### 性能影响

- **对象状态查询**: < 100ms
- **问题列表查询**: < 200ms
- **crash 后状态更新**: < 1s

---

## 🔄 升级指南

### 从 v1.10.1 升级

1. **更新包**:
   ```bash
   pip install --upgrade ptestx
   ```

2. **检查对象状态**:
   - 现有对象状态不受影响
   - 新增 `crash_preserved` 状态

3. **使用新功能**:
   - 使用 `ptest obj issues` 查看对象关联的问题
   - 使用 `ptest obj status` 查看 crash 信息

### 兼容性

- **向后兼容**: 完全兼容 v1.10.1
- **数据迁移**: 无需数据迁移
- **配置变更**: 无需配置变更

---

## 📝 已知问题

无

---

## 🔮 后续计划

### 短期计划

1. **监控上线后表现**: 观察 crash 联动功能在生产环境的表现
2. **收集用户反馈**: 了解用户对新功能的使用体验
3. **性能优化**: 根据实际使用情况优化性能

### 中期计划

1. **扩展功能**: 支持更多 crash 类型
2. **优化建议**: 根据用户反馈优化恢复建议
3. **文档完善**: 补充使用文档和示例

### 长期计划

1. **自动化测试**: 增加自动化测试用例
2. **性能监控**: 建立性能监控机制
3. **持续改进**: 根据使用数据持续改进

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

- **GitHub Issues**: https://github.com/your-org/ptest/issues
- **文档**: https://ptest.readthedocs.io
- **邮箱**: support@ptest.dev

---

**发布日期**: 2026-06-11  
**版本**: 1.11.0  
**状态**: 正式发布
