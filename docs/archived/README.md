# 归档文档索引

`archived/` 保存不再作为当前版本权威说明的公开文档，用于历史参考和演进追溯。

## 使用原则

- 归档文档默认不再维护
- 如果归档文档与当前实现冲突，以当前文档为准
- 对外说明优先阅读 `docs/README.md` 中当前目录入口

## 当前主要归档内容

### 早期需求与产品资料

- [prd.md](./prd.md)
  - 项目早期需求文档
  - 用于理解产品定义如何从“传统测试框架”演化到当前主线

### 历史数据库架构资料

- [DATABASE_ARCHITECTURE_REFACTOR.md](./DATABASE_ARCHITECTURE_REFACTOR.md)
- [DATABASE_SEPARATION_ARCHITECTURE_COMPLETE.md](./DATABASE_SEPARATION_ARCHITECTURE_COMPLETE.md)
- [DATABASE_SERVER_CLIENT_SEPARATION.md](./DATABASE_SERVER_CLIENT_SEPARATION.md)
- [UNIVERSAL_DATABASE_CONNECTOR.md](./UNIVERSAL_DATABASE_CONNECTOR.md)

这些文档主要用于追溯数据库对象设计和历史拆分方案，不应直接作为当前 API 或 CLI 的权威说明。

### 历史开发与目录资料

- [AGENTS.md](./AGENTS.md)
- [AGENTS_EN.md](./AGENTS_EN.md)
- [TEST_DIRECTORY_RESTRUCTURE.md](./TEST_DIRECTORY_RESTRUCTURE.md)
- [TEST_EXECUTION_README.md](./TEST_EXECUTION_README.md)

## 当前推荐入口

如果你需要当前版本文档，请优先阅读：

- [../README.md](../README.md)
- [../user-guide/README.md](../user-guide/README.md)
- [../api/README.md](../api/README.md)
- [../architecture/README.md](../architecture/README.md)
- [../development/README.md](../development/README.md)
- [../guides/README.md](../guides/README.md)

## 说明

- `docs/plan/` 是内部文档区，不作为对外入口
- 归档区的价值是保留历史，不是延续旧结论
- 如需查历史决策，优先结合 `docs/archived/` 与内部 `docs/plan/history/` 理解
