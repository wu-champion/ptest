# MySQL 全生命周期实践

[中文](./mysql-full-lifecycle.md) | [English](./mysql-full-lifecycle.en.md)

这篇文档不是一个“把一串命令贴完就结束”的自动化示例。  
它更接近测试工程师在真实工作里的使用方式：

- 先准备工作区
- 再安装被测对象
- 启动对象并确认状态
- 按步骤执行测试
- 查看执行记录、问题记录和报告
- 最后再决定是继续保留环境，还是停止、卸载、销毁

如果你想快速理解 `ptest` 的价值，这篇文档比一组零散命令更接近真实使用场景。

## 这个案例在验证什么

这条 MySQL 主案例会验证两件事。

第一，它验证 MySQL 作为一个被测产品对象，能否在 `ptest` 管理下完成：

`install -> start -> use -> stop -> uninstall`

第二，它也在验证 `ptest` 自己是否具备：

- 受管工作区隔离
- 对象生命周期管理
- 执行记录与问题记录沉淀
- 停止与卸载后的清理能力
- 工作区外无持久性实例污染

## 先说清楚当前运行模型

当前 MySQL 主案例采用的是：

- 受管工作区
- `host` runtime backend

这意味着：

- MySQL 的目录、配置、日志、数据和依赖，都会尽量放在 `ptest` 的受管路径下
- 但真实 `mysqld` 进程仍然需要宿主执行环境提供启动和端口绑定能力

所以，这个案例当前并不承诺在任意受限沙箱中都能运行。  
当前环境至少需要允许：

- 启动真实进程
- 绑定本地 TCP 端口
- 加载受管目录中的动态库依赖

如果这些能力不满足，框架会尽量在 `start` 前给出明确提示，而不是等到中途抛出模糊错误。

## 适合谁看

这篇文档适合：

- 想第一次接触 `ptest` 的测试工程师
- 想用一个真实数据库对象体验框架能力的人
- 想在发布前做一次受控 smoke 的开发或测试成员

## 前置准备

### 1. 准备 MySQL 安装包

当前主案例使用：

- `MySQL Community Server 8.4.8 LTS`
- `Ubuntu Linux 24.04 (x86, 64-bit)`
- 安装包：`mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar`

建议把它放在一个固定资产目录里，例如：

```text
~/.ptest/assets/mysql/8.4.8/
```

例如：

```text
~/.ptest/assets/mysql/8.4.8/mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar
```

### 2. 准备依赖资产

当前真实 smoke 已验证过的运行依赖包括：

- `libaio1t64`
- `libnuma1`

也建议把它们放在固定资产目录中，例如：

```text
~/.ptest/assets/mysql/8.4.8/deps/
```

例如：

```text
~/.ptest/assets/mysql/8.4.8/deps/libaio1t64_xxx_amd64.deb
~/.ptest/assets/mysql/8.4.8/deps/libnuma1_xxx_amd64.deb
```

这些依赖会被安装到当前案例的受管目录中，而不是要求你提前把它们装到宿主机全局路径。

### 3. 准备工作区路径

建议先挑一个容易理解、也方便清理的工作区路径，例如：

- `~/ptest/mysql-demo`
- `/home/user/ptest/mysql-demo`
- `./ptest-mysql-demo`

后面文档统一用：

```text
~/ptest/mysql-demo
```

### 4. 确认命令使用方式

这篇文档默认按“已经安装了 `ptestx`，可以直接使用 `ptest` 命令”的方式来写。

先确认一下：

```bash
ptest --version
```

如果能正常输出版本号，下面的命令就可以直接照着执行。

如果你是在源码仓库里体验这条流程，也可以。  
只需要把下面所有的：

```bash
ptest
```

替换成：

```bash
uv run ptest
```

就可以了。

## 测试工程师式的分步使用方式

下面这套流程，按“一个真实测试工程师会怎样用”来写。  
你不需要一次性跑完所有命令，可以在每一步停下来查看状态、调整参数、继续操作。

### 第 1 步：初始化工作区

```bash
ptest init --path ~/ptest/mysql-demo
cd ~/ptest/mysql-demo
```

这个命令会做什么：

- 创建受管工作区
- 初始化 `.ptest/` 元数据目录
- 为后续对象、用例、执行记录和报告准备基础结构

建议立刻确认环境状态：

```bash
ptest env status
```

如果这一步成功，你通常会看到类似结果：

```text
环境状态: active
工作区: ~/ptest/mysql-demo
对象数量: 0
用例数量: 0
```

从这里开始，后面的命令都默认你已经在 `~/ptest/mysql-demo` 这个工作区里了。  
这也是更贴近测试工程师日常使用的方式：先进入受管工作区，再连续完成安装、启动、测试、查看记录和清理。

### 第 2 步：安装 MySQL 对象

```bash
ptest obj install mysql mysql_demo \
  --package-path ~/.ptest/assets/mysql/8.4.8/mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libaio1t64_xxx_amd64.deb \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libnuma1_xxx_amd64.deb \
  --port 13319
```

关键参数说明：

- `obj install`
  表示安装一个被测对象，而不是运行一个测试 case

- `mysql`
  对象类型。当前在这个主案例里，`mysql` 表示“数据库服务产品对象”，不是连接字符串

- `mysql_demo`
  对象名。后续 `start`、`status`、`stop`、`uninstall` 都会用到它

- `--package-path`
  MySQL 主安装包路径。当前是必填项

- `--dependency-asset`
  依赖资产路径。可以重复传入多个

- `--port`
  运行端口。建议显式指定，避免与宿主机已有 MySQL 或其他服务冲突

这一步完成后，你可以先看对象状态：

```bash
ptest obj status mysql_demo
```

如果安装成功，通常会看到类似结果：

```text
对象名称: mysql_demo
对象类型: mysql
当前状态: installed
运行端口: 13319
受管目录: ~/ptest/mysql-demo/.ptest/managed_objects/mysql_demo
```

### 第 3 步：启动 MySQL 对象

```bash
ptest obj start mysql_demo
```

这个命令会做什么：

- 检查当前环境是否允许真实服务启动
- 检查端口绑定能力
- 检查受管依赖是否可解析
- 启动真实 `mysqld`
- 做最小可用性确认

启动后建议再次看状态：

```bash
ptest obj status mysql_demo
```

如果启动成功，通常会看到类似结果：

```text
对象名称: mysql_demo
当前状态: running
运行端口: 13319
runtime backend: host
健康检查: passed
```

如果启动失败，不要急着重试，先看提示信息。  
当前框架会尽量把失败归类成更容易理解的问题，例如：

- 缺共享库
- 端口冲突
- 当前执行环境不允许绑定端口

### 第 4 步：准备 CRUD 用例文件

为了让新手更容易理解，建议第一版不要把整段 JSON 直接塞进命令行，而是先写到一个文件里。

比如创建：

```text
./mysql_crud_case.json
```

内容如下：

```json
{
  "type": "database",
  "object_name": "mysql_demo",
  "operations": [
    {
      "name": "create_database",
      "query": "CREATE DATABASE IF NOT EXISTS ptest_mysql_demo"
    },
    {
      "name": "use_database",
      "query": "USE ptest_mysql_demo"
    },
    {
      "name": "create_table",
      "query": "CREATE TABLE IF NOT EXISTS crud_items (id INT PRIMARY KEY, name VARCHAR(32))"
    },
    {
      "name": "insert",
      "query": "INSERT INTO crud_items VALUES (1, 'alpha')",
      "expected_result": {"count": 1}
    },
    {
      "name": "select_after_insert",
      "query": "SELECT id, name FROM crud_items",
      "expected_result": [{"id": 1, "name": "alpha"}]
    },
    {
      "name": "update",
      "query": "UPDATE crud_items SET name = 'beta' WHERE id = 1",
      "expected_result": {"count": 1}
    },
    {
      "name": "select_after_update",
      "query": "SELECT id, name FROM crud_items",
      "expected_result": [{"id": 1, "name": "beta"}]
    },
    {
      "name": "delete",
      "query": "DELETE FROM crud_items WHERE id = 1",
      "expected_result": {"count": 1}
    },
    {
      "name": "select_after_delete",
      "query": "SELECT COUNT(*) AS count FROM crud_items",
      "expected_result": {"count": 0}
    }
  ]
}
```

关键字段说明：

- `type: database`
  表示这是数据库类测试

- `object_name: mysql_demo`
  表示这条 case 绑定到已经安装并启动的 MySQL 对象，而不是自己再写一套独立连接参数

- `operations`
  表示按顺序执行多步数据库操作

- `name`
  每一步操作的名称，便于执行记录和问题定位

- `query`
  当前步骤实际执行的 SQL

- `expected_result`
  当前步骤的预期结果

### 第 5 步：添加测试用例

```bash
ptest case add mysql_crud_case --file ./mysql_crud_case.json
```

关键参数说明：

- `case add`
  表示把一条测试用例注册到当前工作区

- `mysql_crud_case`
  用例 ID，后续执行和查询记录会用到它

- `--file`
  从 JSON 文件加载 case 定义。对新手更友好，也更容易维护

### 第 6 步：执行测试用例

```bash
ptest case run mysql_crud_case
```

这一步会：

- 解析绑定对象 `mysql_demo`
- 自动补齐数据库连接信息
- 按顺序执行建库、用库、建表和 CRUD 操作
- 记录执行结果

这里的数据库流程现在是显式展开的：

- 先 `CREATE DATABASE`
- 再 `USE` 指定库
- 再建表并做 CRUD

也就是说，当前主案例不再依赖框架在启动后静默创建业务库。

如果这一步成功，你通常会看到类似结果：

```text
用例: mysql_crud_case
执行状态: passed
execution_id: execution_xxxxxxxx
```

### 第 7 步：查看执行记录和产物

先看执行记录：

```bash
ptest execution list --case-id mysql_crud_case
```

如果你已经拿到某个 `execution_id`，还可以继续看产物：

```bash
ptest execution artifacts <execution_id>
```

这一步适合在你想确认：

- SQL 执行结果
- 执行元数据
- 产物索引
- 报告文件路径

例如，执行记录列表通常会包含：

```text
execution_id: execution_xxxxxxxx
case_id: mysql_crud_case
status: passed
created_at: 2026-03-27T...
```

### 第 8 步：一条故意失败的用例

如果只演示成功路径，你会看不到 `ptest` 在“问题保留和恢复”上的价值。  
所以这里加一条**故意失败**的 case，用来直观看问题记录是怎么留下来的。

比如创建：

```text
./mysql_crud_case_fail.json
```

内容如下：

```json
{
  "type": "database",
  "object_name": "mysql_demo",
  "operations": [
    {
      "name": "select_wrong_expectation",
      "query": "SELECT COUNT(*) AS count FROM crud_items",
      "expected_result": {"count": 99}
    }
  ]
}
```

这条 case 的目的很简单：

- SQL 本身能正常执行
- 但预期结果故意写错
- 这样就能稳定制造一个测试失败场景

添加并运行它：

```bash
ptest case add mysql_crud_case_fail --file ./mysql_crud_case_fail.json
ptest case run mysql_crud_case_fail
```

如果这一步失败，通常会看到类似结果：

```text
用例: mysql_crud_case_fail
执行状态: failed
execution_id: execution_yyyyyyyy
error: expected_result mismatch
```

### 第 9 步：查看问题记录

如果执行失败，当前主线会自动沉淀问题记录：

```bash
ptest problem list
```

如果问题已经沉淀成功，你通常会在列表里看到类似结果：

```text
problem_id: problem_execution_yyyyyyyy
problem_type: data_state
status: open
preservation_status: success
```

如果想查看某个问题详情：

```bash
ptest problem show <problem_id>
ptest problem assets <problem_id>
ptest problem recover <problem_id>
```

这部分对应的是 `ptest` 现在比较重要的一条能力：

**不只是告诉你“失败了”，还尽量把现场留下来。**

例如：

- `problem show` 会告诉你问题类型、来源执行、当前状态
- `problem assets` 会告诉你这次失败保留下来了哪些信息
- `problem recover` 会告诉你当前这类问题至少还能做什么恢复动作

### 第 10 步：如果对象进入失败保留态，使用 clear / reset

从这一版开始，MySQL 主案例已经支持两类失败保留状态：

- `install_failed_preserved`
- `start_failed_preserved`

你可以先查看对象状态：

```bash
ptest obj status mysql_demo
```

如果对象进入失败保留态，通常会看到类似结果：

```text
对象名称: mysql_demo
当前状态: start_failed_preserved
可用动作: clear, reset
failure_state.phase: start
```

这时有两个显式动作：

```bash
ptest obj clear mysql_demo
ptest obj reset mysql_demo
```

两者区别是：

- `clear`
  只清理失败现场
- `reset`
  把整个对象重置回初始状态

当前第一版规则是：

- `install_failed_preserved`
  - `clear` 后对象会被移除
- `start_failed_preserved`
  - `clear` 后对象会回到 `installed`
- 对正常状态对象，`clear` 会被拒绝

如果你只是想先分析失败原因，建议先看：

```bash
ptest obj status mysql_demo
ptest problem list
```

再决定用 `clear` 还是 `reset`。

### 第 11 步：停止 MySQL 对象

```bash
ptest obj stop mysql_demo
```

这一步不是简单改状态，而是要确认：

- 进程退出
- 端口释放
- 运行痕迹收口

如果停止成功，通常会看到类似结果：

```text
对象名称: mysql_demo
当前状态: stopped
端口释放检查: passed
```

### 第 12 步：卸载 MySQL 对象

```bash
ptest obj uninstall mysql_demo
```

这一步会清理当前受管实例，而不是卸载宿主机全局 MySQL。

如果卸载成功，通常会看到类似结果：

```text
对象名称: mysql_demo
当前状态: uninstalled
对象清理检查: passed
```

### 第 13 步：在测试结束后，生成报告

到这一步，你已经完成了：

- 成功用例验证
- 失败用例验证
- 问题记录查看
- stop
- uninstall

这时候生成报告，可以看到这轮完整测试工作的结果。

```bash
ptest report generate --format json
```

如果你更喜欢 HTML：

```bash
ptest report generate --format html
```

如果报告生成成功，通常会看到类似结果：

```text
报告生成成功
format: html
report_path: ~/ptest/mysql-demo/.ptest/reports/latest/index.html
```

### 第 14 步：如果需要，再销毁整个工作区

```bash
cd ..
ptest env destroy --path ~/ptest/mysql-demo
```

如果你只想保留工作区看报告和执行记录，可以先不做这一步。

如果销毁成功，通常会看到类似结果：

```text
环境已销毁
工作区: ~/ptest/mysql-demo
```

这里重新显式写 `--path`，是因为这一步更像“跨工作区的收尾动作”。  
如果你一直在同一个工作区里连续操作，通常不需要每条命令都带 `--path`。
`ptest init --path ...` 成功后会自动切换活动工作区；后续像 `obj`、`case`、`report`、`execution`/`exec`、`problem` 这些工作区内业务命令，都可以直接沿用当前目录工作区或活动工作区。

## 如果你只想一次性做验证

上面是更接近测试工程师日常使用的“分步模式”。  
如果你只是想快速验证当前环境是否能跑通 MySQL 主案例，也可以用脚本入口：

- [`scripts/mysql_full_lifecycle_scenario.py`](../../scripts/mysql_full_lifecycle_scenario.py)

例如：

```bash
uv run python scripts/mysql_full_lifecycle_scenario.py \
  --package-path ~/.ptest/assets/mysql/8.4.8/mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar \
  --workspace ~/ptest/mysql-demo \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libaio1t64_xxx_amd64.deb \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libnuma1_xxx_amd64.deb \
  --port 13319
```

这个入口更适合：

- 发布前验证
- 自动化 smoke
- 快速确认当前环境是否支持真实 MySQL 主案例

## 当前验收重点

这个案例当前最重要的验收点不是“SQL 能不能执行”这么简单，而是：

- 工作区边界是否成立
- 依赖是否能被受管安装
- 真实服务是否能启动
- CRUD 是否能跑通
- stop / uninstall 是否真的收口
- 工作区外是否没有持久污染

## 常见问题

### 1. 启动时报缺少共享库

这通常说明你没有通过 `--dependency-asset` 传入对应依赖资产。  
当前已知至少需要：

- `libaio1t64`
- `libnuma1`

### 2. 启动时报 `Operation not permitted`

这通常不是安装包本身坏了，而是当前执行环境不允许真实服务对象绑定端口或启动受管服务。

这时需要：

- 换到具备真实服务运行能力的宿主环境
- 或调整当前环境的执行限制策略

### 3. 端口冲突

如果宿主机已有 MySQL 或其他服务正在使用某个端口，请显式通过 `--port` 换一个端口。

### 4. 我想保留环境继续做别的测试

这正是推荐的正常使用方式。  
你完全可以在：

- `obj start mysql_demo`

之后继续：

- 添加更多 case
- 继续执行不同 SQL 测试
- 查看执行记录
- 生成报告

而不是每次都一条命令从头跑到尾。

## 关于 `--path` 的一个补充说明

你在其他文档、脚本或 CI 配置里，可能会看到很多 `--path`。  
那种写法更适合：

- 自动化脚本
- CI 场景
- 同时管理多个工作区

而在单机、单工作区、人工逐步操作的场景里，更自然的方式通常是：

1. `ptest init --path ~/ptest/mysql-demo`
2. `ptest workspace status`
3. 如果你喜欢在工作区内操作，就 `cd ~/ptest/mysql-demo`
4. 后续直接执行 `ptest obj ...`、`ptest case ...`、`ptest execution ...` 或 `ptest exec ...`

这样命令更短，也更符合测试人员真实使用习惯。
