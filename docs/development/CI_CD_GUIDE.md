# CI/CD 流程文档

## 概述

本文档描述了 ptest 测试框架的完整 CI/CD（持续集成/持续部署）流程。

## 工作流概览

### 1. CI 工作流 (`ci.yml`)

**触发条件**:
- 推送到 `main` 或 `develop` 分支
- 创建 Pull Request

**任务**:

#### 1.1 代码质量检查 (lint-and-format)
- **代码格式检查**: 使用 ruff 检查代码格式
- **代码风格检查**: 使用 ruff format 验证代码风格
- **类型检查**: 使用 mypy 进行静态类型检查

#### 1.2 单元测试 (unit-tests)
- **多平台测试**: Ubuntu, Windows, macOS
- **Python 版本**: 3.12
- **覆盖率报告**: 生成并上传到 Codecov

#### 1.3 集成测试 (integration-tests)
- 运行集成测试套件
- 验证组件间协作

#### 1.4 构建验证 (build-check)
- 构建 Python 包
- 验证构建产物
- 测试安装

#### 1.5 安全扫描 (security-scan)
- **依赖安全扫描**: 使用 pip-audit
- **代码安全扫描**: 使用 bandit

### 2. CD 工作流 (`cd.yml`)

**触发条件**:
- 发布 Release
- 手动触发 (workflow_dispatch)

**任务**:

#### 2.1 发布构建 (build)
- 运行完整测试
- 构建发布包

#### 2.2 发布到 PyPI (publish-pypi)
- 使用 Trusted Publishing
- 自动发布到 PyPI

#### 2.3 创建 GitHub Release (create-release)
- 自动生成 Release 说明
- 上传构建产物

### 3. main 自动发布工作流 (`release-on-main.yml`)

**触发条件**:
- 推送到 `main` 分支
- 且本次变更包含 `pyproject.toml` 或 `CHANGELOG.md`

**任务**:

#### 3.1 检查是否需要自动发布 (prepare-release)
- 读取 `pyproject.toml` 中的版本号
- 检查对应 `v<version>` 标签是否已存在
- 如标签已存在则跳过自动发布

#### 3.2 自动执行 CI、构建与发布
- 复用 `ci.yml` 完成测试与质量检查
- 构建发布包并验证产物
- 发布到正式 PyPI
- 自动创建版本标签
- 自动创建 GitHub Release

### 4. Docker 工作流 (`docker.yml`)

**触发条件**:
- 推送到 `main` 分支
- 创建 Tag
- Pull Request

**任务**:

#### 3.1 构建和推送镜像 (build-and-push)
- 多架构构建 (linux/amd64, linux/arm64)
- 推送到 GitHub Container Registry
- 生成构件证明

#### 3.2 镜像扫描 (scan-image)
- 使用 Trivy 扫描安全漏洞
- 上传扫描结果

## 使用方法

### 本地开发

```bash
# 运行代码质量检查
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/

# 运行测试
uv run pytest tests/unit/ -v

# 构建包
uv build
```

### 手动触发发布

1. 进入 GitHub Actions 页面
2. 选择 "CD - 发布到 PyPI" 工作流
3. 点击 "Run workflow"
4. 选择版本号类型 (patch/minor/major)

### 自动发布

1. 在功能分支中更新版本号与 `CHANGELOG.md`
2. 通过 PR 合并到 `main`
3. `release-on-main.yml` 会自动：
   - 读取版本号
   - 检查标签是否存在
   - 执行 CI
   - 发布到 PyPI
   - 创建标签和 GitHub Release

## 环境配置

### PyPI 发布配置

1. 在 GitHub 仓库设置中配置环境:
   - 环境名称: `pypi`
   - 保护规则: 需要审查

2. 在 PyPI 项目中添加 Trusted Publisher:
   - 发布者: GitHub Actions
   - 仓库: `<username>/ptest`
   - 工作流: `cd.yml` 或 `release-on-main.yml`

## 状态徽章

添加以下徽章到 README.md:

```markdown
[![CI](https://github.com/<username>/ptest/actions/workflows/ci.yml/badge.svg)](https://github.com/<username>/ptest/actions/workflows/ci.yml)
[![CD](https://github.com/<username>/ptest/actions/workflows/cd.yml/badge.svg)](https://github.com/<username>/ptest/actions/workflows/cd.yml)
[![Docker](https://github.com/<username>/ptest/actions/workflows/docker.yml/badge.svg)](https://github.com/<username>/ptest/actions/workflows/docker.yml)
[![codecov](https://codecov.io/gh/<username>/ptest/branch/main/graph/badge.svg)](https://codecov.io/gh/<username>/ptest)
```

## 故障排除

### 常见问题

#### CI 失败
1. 检查代码格式: `uv run ruff check src/`
2. 检查类型错误: `uv run mypy src/`
3. 运行测试: `uv run pytest tests/unit/`

#### 发布失败
1. 检查版本号格式是否正确
2. 检查 PyPI 凭据配置
3. 检查构建产物是否完整

#### Docker 构建失败
1. 检查 Dockerfile 语法
2. 检查基础镜像是否可用
3. 检查依赖安装是否成功

## 最佳实践

1. **提交前检查**: 始终在本地运行代码质量检查
2. **小步提交**: 频繁提交小的、可工作的更改
3. **详细提交信息**: 编写清晰的提交信息
4. **使用分支**: 在功能分支上工作，通过 PR 合并
5. **审查要求**: 确保所有 PR 都通过 CI 检查

## 分支管理规范

### 阶段结束规则

- 每个已发布版本视为一个阶段的正式结束
- 版本发布完成后，当前开发分支不再继续承载下一阶段的主开发任务
- 后续如无紧急补丁需求，应在新的开发分支上开展下一阶段工作

### 规范类改动与新阶段开发的边界

- 仓库级治理规则、发布规则、分支管理规则、CI/CD 流程规则等，视为当前阶段收口的一部分
- 这类规范性改动可以在当前阶段的收口分支中进入 Git 管理
- 新阶段的产品需求、功能实现、案例建设、文档交付等内容，不应继续放在上一阶段分支中开发
- 因此，是否进入新分支，不以“是否和未来有关”为判断标准，而以“是仓库治理规则，还是下一阶段产品开发内容”为判断标准

### 新分支创建时机

- 新阶段先在本地完成产品规划与范围讨论
- 规划讨论内容保留在本地内部文档中，不直接进入远端仓库
- 只有当任务正式进入 Git 管理范围时，才创建新的开发分支

### 分支命名规则

- 分支名称应同时体现“阶段顺序”和“主题”
- 不建议只使用主题命名，也不建议在规划初期机械绑定最终版本号
- 推荐格式：

```text
feature/<阶段编号>-<主题>
```

- 示例：

```text
feature/03-mysql-lifecycle-scenario
feature/04-crash-preservation
feature/05-problem-replay-enhancement
```

### 版本号与分支名称的关系

- 分支名称中的阶段编号用于体现开发顺序
- 最终发布版本号在阶段收口和发布前统一确认
- 当后续出现大版本变化（如从 1.x 进入 2.x）时，不要求提前在分支名中写死版本号
- 如后续团队需要，也可在进入开发时再决定是否引入与大版本相关的命名扩展

### 风险提示

- 启用自动发布流程后，不建议在本地提前手动创建并推送 `v<version>` 标签
- 当前自动发布 workflow 会以远端标签是否存在作为是否发布的判断条件
- 如果提前手动推送同版本标签，可能导致自动发布跳过 PyPI 与 GitHub Release 流程

## 更新维护

定期更新:
- GitHub Actions 版本
- Python 版本
- 依赖包版本
- 安全检查规则

## 联系方式

如有 CI/CD 相关问题，请联系:
- 邮件: <your-email>
- Issues: https://github.com/<username>/ptest/issues
