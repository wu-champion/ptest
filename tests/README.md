# ptest 测试说明

本文档描述当前仓库测试目录的主要结构和推荐运行方式。

## 当前目录结构

```text
tests/
├── unit/           # 单元测试
├── integration/    # 集成测试
├── e2e/            # 端到端测试预留目录
├── performance/    # 性能测试预留目录
├── verification/   # 结构校验 / 验证测试
├── fixtures/       # 测试夹具与辅助资源
├── data/           # 测试数据
└── reports/        # 测试运行产物目录
```

当前最常用的是：

- `tests/unit/`
- `tests/integration/`

## 当前推荐运行方式

在仓库根目录执行：

```bash
uv run pytest tests/unit/ -v --tb=short
uv run pytest tests/integration/ -v --tb=short --ignore=tests/integration/docker/test_real_docker.py
```

如果你要执行完整本地质量门禁，使用：

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/ --ignore-missing-imports --show-error-codes
uv run pytest tests/unit/ -v --tb=short
uv run pytest tests/integration/ -v --tb=short --ignore=tests/integration/docker/test_real_docker.py
uv build
uv run twine check dist/*
```

## 测试层级理解

### 单元测试

聚焦单个模块或较小行为单元，例如：

- CLI 参数与解析逻辑
- API 返回结构
- isolation 引擎行为
- objects / cases / reports / problem 等模块逻辑

### 集成测试

聚焦跨模块工作流，例如：

- workflow 主线
- API 与工作流协作
- 数据库对象集成
- Docker 相关集成路径

### 其他目录

- `e2e/`、`performance/`、`verification/` 当前不是日常主入口
- 是否启用、补强或重组，按后续正式计划推进

## 编写与维护原则

- 新增主线能力时，优先补对应单元测试
- 跨模块行为变化时，补集成测试或更新已有集成断言
- 测试说明以当前仓库真实结构为准，不承诺历史测试计划仍全部有效
- 如果测试结构发生明显变化，应同步更新本文件

## 相关文档

- [README.md](../README.md)
- [docs/development/development-guide.md](../docs/development/development-guide.md)
- [docs/api/python-api-guide.md](../docs/api/python-api-guide.md)
