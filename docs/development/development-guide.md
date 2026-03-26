# ptest 开发指南

本文档面向当前仓库维护者和贡献者，描述 `1.5.0` 主线下的开发方式。

## 开发目标

当前开发以第一阶段 MVP 主线为准，重点围绕：

- 环境生命周期管理
- 对象生命周期管理
- 用例与执行管理
- 结果与上下文留存
- CLI / Python API 一致性

详细范围见内部 `docs/plan/current/`。

## 开发环境

### 基础要求

- Python 3.12+
- `uv`
- Git

### 初始化

```bash
git clone <your-repo>
cd ptest
uv sync
```

## 当前关键目录

```text
src/ptest/
├── api.py                 # Python API 入口
├── cli.py                 # CLI 入口
├── app/                   # 统一工作流主线
├── storage/               # 工作区持久化
├── models/                # 主线数据模型
├── isolation/             # 隔离能力
├── objects/               # 被测对象能力
├── cases/                 # 用例与执行能力
├── reports/               # 报告生成
├── data/                  # 测试数据能力
├── contract/              # 契约能力
└── mock/                  # Mock 能力
```

当前架构上，CLI 和 `PTestAPI` 都应尽量通过 `WorkflowService` 进入主线。

## 开发原则

### 1. 计划优先

- 所有开发优先映射到当前正式计划
- 新问题先归类，再决定是否进入当前开发
- 不因为局部旧实现而牺牲当前主线设计

### 2. 统一主线优先

- CLI 不应自行承载复杂业务逻辑
- Python API 不应绕开工作流主线直接拼装 manager
- 新能力尽量落到 `app/`、`storage/`、`models/` 这条主线上

### 3. 质量门禁优先

提交前默认执行：

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/ --ignore-missing-imports --show-error-codes
uv run pytest tests/unit/ -v --tb=short
uv run pytest tests/integration/ -v --tb=short --ignore=tests/integration/docker/test_real_docker.py
uv build
uv run twine check dist/*
```

真实 Docker 环境验证以 CI 为准，本地允许使用模拟或可控替代方式验证。

## 代码约束

- 新增或修改主线 public 接口时，补参数类型注解
- 优先保持 CLI / API 返回结构一致
- 避免新增只存在于内存中的关键状态
- 需要持久化的主线资产优先进入工作区 `.ptest/`

## 文档约束

- `docs/plan/` 是内部文档区，不进入远端
- 公开文档按 `user-guide / api / architecture / development / guides` 分类维护
- 新增或移动文档时，同步更新目录 README 和 `docs/README.md`

具体规则见 [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md)。

## 常见开发路径

### 代码修改

1. 先确认对应哪条当前计划
2. 优先检查主线入口是否已存在
3. 落代码
4. 补测试
5. 跑质量门禁
6. 再考虑本地提交

### 发布收口

1. 对齐 README / docs
2. 确认版本号与 changelog
3. 跑完整本地检查
4. 本地构建
5. 由维护者手动完成远端推送

## 相关文档

- [README.md](README.md)
- [CODING_STANDARDS.md](CODING_STANDARDS.md)
- [CODE_QUALITY_GUIDE.md](CODE_QUALITY_GUIDE.md)
- [CI_CD_GUIDE.md](CI_CD_GUIDE.md)
- [../architecture/system-overview.md](../architecture/system-overview.md)
