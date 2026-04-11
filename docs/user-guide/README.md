# ptest 用户文档

[中文主入口](../../README.md) | [English Entry](../../README.en.md)

`user-guide/` 目录面向框架使用者，提供安装、入门和基础操作说明。

## 推荐阅读顺序

1. [basic-usage.md](basic-usage.md)
2. [mysql-full-lifecycle.md](mysql-full-lifecycle.md)
3. [mysql-full-lifecycle.en.md](mysql-full-lifecycle.en.md)

如果你正在直接使用 CLI，建议优先掌握这几个点：

- `ptest init --path <path>` 会初始化并自动切换活动工作区
- `ptest workspace status/use/unset` 用来查看和切换当前工作区上下文
- 工作区内业务命令在不传 `--path` 时，会优先使用当前目录工作区，再回退活动工作区

## 适用范围

这部分文档默认面向：

- 测试工程师
- 自动化测试使用者
- 需要快速上手 `ptest` CLI / Python API 的项目成员

## 当前说明

- SQLite 等轻量对象可以直接作为最小主线示例
- MySQL 全生命周期主案例当前基于 `host` runtime backend，需要执行环境支持真实服务运行
- `execution` 保持正式命令名，同时支持更短的 `exec` 别名

## 与其他目录的关系

- 如果你想直接使用框架，从这里开始
- 如果你要做二次开发，请转到 [../development/README.md](../development/README.md)
- 如果你要查看架构设计，请转到 [../architecture/README.md](../architecture/README.md)
- 如果你要看 API 细节，请转到 [../api/README.md](../api/README.md)
