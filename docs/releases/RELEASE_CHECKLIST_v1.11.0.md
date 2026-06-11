# ptest v1.11.0 发布清单

**发布日期**: 2026-06-11  
**版本**: 1.11.0  
**负责人**: DevOps

---

## 1. 发布前检查

### 1.1 代码检查

- [x] 所有单元测试通过（614 passed）
- [x] 代码质量检查通过（Ruff）
- [x] 类型检查通过（MyPy）
- [x] 无安全漏洞

### 1.2 文档检查

- [x] CHANGELOG 已更新
- [x] 发布说明已准备
- [x] API 文档已更新
- [x] 用户指南已更新

### 1.3 版本检查

- [x] pyproject.toml 版本号已更新（1.11.0）
- [x] __init__.py 版本号已更新（1.11.0）
- [x] 版本号一致性检查通过

---

## 2. 发布流程

### 2.1 分支准备

```bash
# 1. 确保在正确的分支上
git checkout feature/19-native-crash-capture

# 2. 拉取最新代码
git pull origin feature/19-native-crash-capture

# 3. 检查状态
git status
```

### 2.2 创建 Pull Request

```bash
# 1. 推送分支到远程
git push origin feature/19-native-crash-capture

# 2. 在 GitHub 上创建 Pull Request
#    - 标题: feat: P5-D 受管对象 Crash 联动
#    - 目标分支: main
#    - 描述: 包含发布说明
```

### 2.3 合并 Pull Request

1. 在 GitHub 上审核 Pull Request
2. 确认所有 CI 检查通过
3. 合并 Pull Request 到 main

### 2.4 自动发布机制

**重要**: 本项目使用自动发布机制，无需手动创建 tag！

当 `main` 分支的 `pyproject.toml` 或 `CHANGELOG.md` 变更时，会自动触发 `release-on-main.yml` 工作流：

1. **检查版本号**: 从 `pyproject.toml` 读取版本号
2. **检查标签**: 检查远端是否已存在该版本标签
3. **CI 检查**: 运行完整的 CI 测试
4. **构建包**: 构建 Python 包
5. **发布到 PyPI**: 自动发布到 PyPI
6. **创建标签**: 自动创建 `v1.11.0` 标签
7. **创建 Release**: 自动创建 GitHub Release

**注意**: 
- 标签由 GitHub Actions 自动创建，无需手动操作
- 如果标签已存在，会跳过自动发布
- Release notes 从 `.github/release-notes/v1.11.0.md` 读取

---

## 3. 自动构建和发布

**重要**: 以下步骤由 GitHub Actions 自动执行，无需手动操作！

### 3.1 自动触发条件

当 `main` 分支发生以下变更时，会自动触发发布：
- `pyproject.toml` 文件变更
- `CHANGELOG.md` 文件变更

### 3.2 自动执行流程

1. **CI 检查**: 运行完整的 CI 测试
2. **构建包**: 自动构建 Python 包
3. **发布到 PyPI**: 自动发布到 PyPI
4. **创建标签**: 自动创建 `v1.11.0` 标签
5. **创建 Release**: 自动创建 GitHub Release

### 3.3 手动触发（可选）

如果需要手动触发发布，可以使用 `cd.yml` 工作流：

1. 进入 GitHub 仓库
2. 点击 "Actions"
3. 选择 "CD - 发布到 PyPI"
4. 点击 "Run workflow"
5. 选择版本类型（patch/minor/major）
6. 点击 "Run workflow"

**注意**: 手动触发会创建新的 Release，但不会自动更新版本号。

---

## 4. 发布后验证

### 4.1 PyPI 验证

```bash
# 1. 安装新版本
pip install --upgrade ptestx

# 2. 验证版本
ptest --version

# 3. 验证功能
ptest --help
```

### 4.2 Docker 验证

```bash
# 1. 拉取镜像
docker pull ptest:1.11.0

# 2. 运行容器
docker run ptest:1.11.0 --version

# 3. 验证功能
docker run ptest:1.11.0 --help
```

### 4.3 功能验证

```bash
# 1. 创建测试环境
ptest init --path /tmp/test-release

# 2. 测试新功能
ptest obj issues --help
ptest obj status --help

# 3. 清理环境
rm -rf /tmp/test-release
```

---

## 5. GitHub Release

### 5.1 创建 Release

1. 进入 GitHub 仓库
2. 点击 "Releases"
3. 点击 "Create a new release"
4. 选择标签：`v1.11.0`
5. 填写标题：`ptest v1.11.0`
6. 填写描述：复制发布说明
7. 上传构建产物：`dist/*`
8. 点击 "Publish release"

### 5.2 Release 内容

**标题**: ptest v1.11.0

**描述**:
```markdown
# ptest v1.11.0

## 🎉 新功能

### P5-D 受管对象 Crash 联动

- 新增 `crash_preserved` 对象状态
- 新增 `ptest obj issues <name>` 命令
- 增强 `ptest obj status <name>` 输出
- 新增 `get_object_crash_info` 和 `list_object_issues` API
- 增强 `problem recover` 对象级恢复建议

## 📈 改进

- 扩展对象状态集合
- 增强恢复计划

## 📊 质量指标

- 单元测试：21 个新增测试用例，100% 通过
- 集成测试：614 个测试用例通过
- 代码质量：Ruff 和 MyPy 检查通过

## 📝 详细说明

详见 [发布说明](docs/releases/RELEASE_NOTES_v1.11.0.md)
```

---

## 6. 通知和文档

### 6.1 通知相关方

- [x] 通知开发团队
- [x] 通知测试团队
- [x] 通知产品团队
- [ ] 通知用户（通过邮件/公告）

### 6.2 更新文档

- [x] 更新 CHANGELOG
- [x] 更新发布说明
- [x] 更新 API 文档
- [x] 更新用户指南

### 6.3 更新状态

- [x] 更新项目状态
- [x] 更新版本历史
- [x] 更新路线图

---

## 7. 回滚计划

### 7.1 回滚条件

- 发现严重 bug
- 性能问题
- 安全漏洞

### 7.2 回滚步骤

```bash
# 1. 切换到 main 分支
git checkout main

# 2. 回滚到上一个版本
git revert HEAD

# 3. 推送回滚
git push origin main

# 4. 删除标签
git tag -d v1.11.0
git push origin :refs/tags/v1.11.0

# 5. 重新发布上一个版本
pip install ptestx==1.10.1
```

---

## 8. 发布检查清单

### 8.1 发布前

- [x] 代码检查通过
- [x] 测试检查通过
- [x] 文档检查通过
- [x] 版本号检查通过
- [x] CHANGELOG 更新
- [x] Release Notes 准备

### 8.2 发布中（手动操作）

- [ ] 创建 Pull Request
- [ ] 审核 Pull Request
- [ ] 合并 Pull Request 到 main

### 8.3 发布中（自动执行）

- [ ] CI 检查通过
- [ ] 包构建成功
- [ ] PyPI 发布成功
- [ ] 标签自动创建
- [ ] GitHub Release 自动创建

### 8.4 发布后

- [ ] PyPI 验证
- [ ] GitHub Release 验证
- [ ] 功能验证
- [ ] 通知发送

---

## 9. 发布时间表

| 时间 | 任务 | 负责人 | 状态 |
|------|------|--------|------|
| 2026-06-11 10:00 | 代码检查 | 开发专家 | ✅ 完成 |
| 2026-06-11 10:30 | 测试验证 | 测试专家 | ✅ 完成 |
| 2026-06-11 11:00 | 文档准备 | 技术文档 | ✅ 完成 |
| 2026-06-11 11:30 | 发布准备 | DevOps | ✅ 完成 |
| 2026-06-11 12:00 | 发布执行 | DevOps | 🔄 进行中 |
| 2026-06-11 12:30 | 发布验证 | 测试专家 | ⏳ 待执行 |
| 2026-06-11 13:00 | 通知发送 | 产品专家 | ⏳ 待执行 |

---

## 10. 联系方式

如有问题，请联系：

- **DevOps**: devops@ptest.dev
- **开发团队**: dev@ptest.dev
- **测试团队**: qa@ptest.dev

---

**发布清单日期**: 2026-06-11  
**负责人**: DevOps  
**审核人**: 架构师  
**批准人**: 产品专家
