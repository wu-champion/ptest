# ptest

[中文](./README.md) | [English](./README.en.md)

`ptest` 想解决的，不只是“把测试跑起来”。

它更想解决测试工程师在真实工作里反复遇到、却很少被一个工具完整接住的那些事情：

- 一个服务终于装起来了，但环境怎么收口、怎么清理，没人管
- 问题测出来了，可现场没留下来，下次想复现只能从头再配
- 被测对象、测试数据、执行记录、日志、报告都散在不同脚本和目录里
- 同一个问题修复前后要反复验证，却很难回到接近当时的状态

很多时候，痛点不在于“写一条 case”，而在于：

**怎么把一个真实产品准备好、跑起来、测下去、留住现场、再干净地收回来。**

这就是 `ptest` 当前在做的事情。

## 它现在能做什么

`ptest` 当前已经建立起一条比较完整的测试主线：

- 初始化受管工作区
- 安装并管理被测对象
- 绑定测试用例并执行
- 生成执行记录、报告和问题记录
- 在失败时尽量保留现场，并提供恢复入口
- 在结束后对对象和环境做清理收口

它不是只想做一个“测试命令执行器”，而是想成为一个**测试生命周期框架**。

## 先说清楚一个名字问题

你在下面会频繁看到两个名字同时出现：

- 项目名：`ptest`
- PyPI 包名：`ptestx`

这不是文档写错了，而是发布时必须这样处理：

- 仓库和产品名称仍然是 `ptest`
- 但 PyPI 上的 `ptest` 名称已存在
- 所以发布包名使用的是 `ptestx`
- 安装完成后，命令行入口仍然是：
  - `ptest`

也就是说，第一次使用时请这样理解：

```bash
pip install ptestx
ptest --version
```

下面案例里出现的大量 `ptest ...` 命令，都是安装完成后的正常用法。

## 一个真实案例

为了避免只停留在抽象描述层面，我们提供了一个可重复执行的真实案例：

**MySQL 全生命周期实践**

它会在受管工作区里完成：

`install -> start -> use -> stop -> uninstall`

这条链路不只是验证 MySQL 能不能用，也在验证 `ptest` 自己是否真的具备：

- 受管目录隔离
- 对象生命周期管理
- 失败现场沉淀
- 停止与卸载后的清理能力

当前这个案例基于：

- `MySQL Community Server 8.4.8 LTS`
- 本地固定安装包资产
- 受管工作区
- `host` runtime backend

也就是说，`ptest` 会管理目录、配置、状态、记录和清理边界；  
真实 `mysqld` 进程运行在宿主执行环境能力之上。

现在这条主案例里的数据库测试流程，也已经明确展开成：

- 显式创建数据库
- 显式选择数据库
- 建表
- CRUD

这样案例更接近测试工程师真实验证数据库产品时的操作节奏，而不是由框架静默代做业务库准备。

## 为什么这个案例重要

很多工具能演示“连上一个数据库，跑一条 SQL”。  
但测试工程师真正需要的，往往是下面这整件事：

1. 把被测产品准备起来
2. 把依赖带齐
3. 跑一条真实测试链路
4. 出问题时把上下文留下来
5. 结束后别把机器和环境弄脏

MySQL 主案例的价值就在这里：

**它不是一个漂亮的命令示例，而是一条真实工作流。**

## 快速看一眼它怎么运行

如果你已经通过 `pip install ptestx` 安装了 `ptest`，可以直接使用 `ptest` 命令。

```bash
ptest init --path ~/ptest/mysql-demo
cd ~/ptest/mysql-demo

ptest obj install mysql mysql_demo \
  --package-path ~/.ptest/assets/mysql/8.4.8/mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libaio1t64_xxx_amd64.deb \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libnuma1_xxx_amd64.deb \
  --port 13319

ptest obj start mysql_demo
ptest case run mysql_crud_case
```

上面这组命令为“先进入工作区，再逐步操作”的形式。  
它代表测试工作中的一系列流程操作：

- 先把对象装起来
- 启动对象
- 分几次添加和执行不同用例
- 过程中反复看状态、看问题记录、看报告
- 最后再决定什么时候停止和卸载

如果你是在源码仓库里开发或验证，使用 `uv run ptest ...` 会更稳，因为它会明确使用当前项目环境。

这组命令会把你带进一个真实场景：

- MySQL 安装
- MySQL 启动
- 后续继续做 CRUD 测试
- 再根据需要查看记录、停服务、卸载对象

如果你只想先快速理解这条链路，直接看这里：

- [MySQL 全生命周期实践](./docs/user-guide/mysql-full-lifecycle.md)
- [MySQL Full Lifecycle Walkthrough](./docs/user-guide/mysql-full-lifecycle.en.md)

如果你更像一个真实测试工程师那样，一步一步创建环境、安装对象、跑 CRUD、查看记录，再手动停止和卸载对象，也建议直接从这篇文档开始。里面已经按分步操作方式重写了。

## 当前边界

为了避免说得太满，这里也把当前边界说清楚。

- `ptest` 当前已经能很好地管理**工作区隔离**和**对象生命周期**
- 对于 SQLite 这类轻量对象，这已经足够
- 对于 MySQL 这类真实服务对象，当前主案例采用的是 `host` runtime backend
- 这意味着执行环境需要允许：
  - 真实进程启动
  - TCP 端口绑定
  - 动态库加载

如果当前环境不支持这些能力，框架会尽量在启动前给出明确提示，而不是等到运行中再抛一个模糊错误。

换句话说：

**我们现在已经能把真实服务对象纳入受管流程，但还没有把“任意环境下的强隔离运行”当成已经完成的承诺。**

## 从哪里开始

如果你第一次接触 `ptest`，建议按这个顺序看：

1. [快速开始](./docs/user-guide/basic-usage.md)
2. [MySQL 全生命周期实践](./docs/user-guide/mysql-full-lifecycle.md)
3. [Python API 指南](./docs/api/python-api-guide.md)
4. [环境管理说明](./docs/guides/environment-management.md)

如果你关心架构和设计：

- [架构文档](./docs/architecture/README.md)
- [开发文档](./docs/development/README.md)

## 安装

当前 PyPI 包名为 `ptestx`，安装后使用的命令仍然是 `ptest`：

```bash
pip install ptestx
ptest --version
```

如果你在源码仓库里工作，建议直接使用：

```bash
uv sync
uv run ptest --version
```

---

`ptest` 想做的，不只是帮你把测试跑完。  
它更想帮你把对象管起来，把问题留住，把现场找回来。
