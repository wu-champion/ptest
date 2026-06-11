# Pull Request: feat: P5-D 受管对象 Crash 联动

## 变更说明

### 新增功能
- P5-D 受管对象 Crash 联动能力
  - 新增 `crash_preserved` 对象状态
  - 新增 `ptest obj issues <name>` 命令
  - 增强 `ptest obj status <name>` 输出
  - 新增 `get_object_crash_info` 和 `list_object_issues` API
  - 增强 `problem recover` 对象级恢复建议

### 版本更新
- 版本号: 1.10.1 → 1.11.0
- 更新 CHANGELOG
- 添加发布说明和 release notes

### 测试
- 21 个新增单元测试用例，100% 通过
- 614 个完整回归测试用例通过
- Ruff 和 MyPy 检查通过

### 文档
- 发布说明: `docs/releases/RELEASE_NOTES_v1.11.0.md`
- 发布清单: `docs/releases/RELEASE_CHECKLIST_v1.11.0.md`
- Release Notes: `.github/release-notes/v1.11.0.md`

---

## 测试验证

```bash
# 运行新增测试
uv run pytest tests/unit/problem/test_crash_linkage.py -v

# 运行完整测试套件
uv run pytest tests/unit/ -v

# 代码质量检查
uv run ruff check src/ptest/app/workflow.py src/ptest/models/__init__.py src/ptest/cli.py src/ptest/api.py

# 类型检查
uv run mypy src/ptest/app/workflow.py src/ptest/models/__init__.py src/ptest/cli.py src/ptest/api.py
```

---

## 发布说明

**版本**: 1.11.0  
**日期**: 2026-06-11  
**主要功能**: P5-D 受管对象 Crash 联动

---

**注意**: 合并后会自动触发发布流程，无需手动创建 tag。
