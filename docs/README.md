# ptest 文档总览

`docs/` 目录按“是否对外”和“面向对象”两条边界组织：

- `docs/plan/` 是内部文档区，只存放当前正式产品主线、历史规划资料、历史会话和内部讨论沉淀，不对外。
- `docs/` 其余目录为可对外文档，分为面向用户和面向开发者两类。

## 文档边界

### 内部文档

- [plan/README.md](plan/README.md)
- 用途：当前正式产品主线、历史规划资料、历史会话与内部讨论沉淀
- 约束：不作为对外文档入口，不承担用户指南或开发指南职责

### 对外文档

#### 面向用户

- [user-guide/README.md](user-guide/README.md)
- 用途：安装、入门、基础使用、常见操作路径

#### 面向开发者

- [architecture/README.md](architecture/README.md)
- [development/README.md](development/README.md)
- [guides/README.md](guides/README.md)
- [api/README.md](api/README.md)

#### 历史参考

- [archived/README.md](archived/README.md)
- 用途：保留旧版本公开文档和历史设计资料，默认不作为当前实现的权威说明

## 推荐阅读路径

### 用户

1. [user-guide/README.md](user-guide/README.md)
2. [user-guide/basic-usage.md](user-guide/basic-usage.md)

### 开发者

1. [development/README.md](development/README.md)
2. [architecture/system-overview.md](architecture/system-overview.md)
3. [api/python-api-guide.md](api/python-api-guide.md)
4. [guides/environment-management.md](guides/environment-management.md)
5. [development/DOCUMENTATION_GUIDE.md](development/DOCUMENTATION_GUIDE.md)

## 维护规则

新增文档时按以下规则归档：

- 新的内部需求、计划、报告、调研、会话纪要放入 `docs/plan/`
- 新的开发规范、架构说明、API 说明、专题使用指南放入开发者文档目录
- 新的安装、入门、操作教程放入 `docs/user-guide/`
- 已失效但仍需保留的公开资料放入 `docs/archived/`

详细结构见 [STRUCTURE.md](STRUCTURE.md)。
