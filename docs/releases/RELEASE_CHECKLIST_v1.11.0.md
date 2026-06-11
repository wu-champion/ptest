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

### 2.2 创建发布分支

```bash
# 1. 创建发布分支
git checkout -b release/v1.11.0

# 2. 推送发布分支
git push origin release/v1.11.0
```

### 2.3 合并到 main

```bash
# 1. 切换到 main 分支
git checkout main

# 2. 拉取最新代码
git pull origin main

# 3. 合并发布分支
git merge release/v1.11.0

# 4. 推送到远程
git push origin main
```

### 2.4 创建标签

```bash
# 1. 创建标签
git tag -a v1.11.0 -m "Release v1.11.0: P5-D 受管对象 Crash 联动"

# 2. 推送标签
git push origin v1.11.0
```

---

## 3. 构建和发布

### 3.1 构建包

```bash
# 1. 清理旧构建
rm -rf dist/ build/ *.egg-info

# 2. 构建包
uv build

# 3. 检查包
ls -la dist/
```

### 3.2 发布到 PyPI

```bash
# 1. 安装 twine
uv pip install twine

# 2. 检查包
twine check dist/*

# 3. 发布到 PyPI
twine upload dist/*
```

### 3.3 构建 Docker 镜像

```bash
# 1. 构建镜像
docker build -t ptest:1.11.0 .

# 2. 标记镜像
docker tag ptest:1.11.0 ptest:latest

# 3. 推送镜像
docker push ptest:1.11.0
docker push ptest:latest
```

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

### 8.2 发布中

- [ ] 分支创建
- [ ] 代码合并
- [ ] 标签创建
- [ ] 包构建
- [ ] PyPI 发布
- [ ] Docker 发布

### 8.3 发布后

- [ ] PyPI 验证
- [ ] Docker 验证
- [ ] 功能验证
- [ ] GitHub Release 创建
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
