# ptest Quickstart Example Notes

`examples/quickstart/` 当前不是 `ptest` 主线的权威入门入口。

这里目前保留了一个轻量 quickstart 脚本：

- [demo.sh](demo.sh)

它现在已经对齐到当前开发主线，会用 SQLite 跑一条最小闭环：

- 初始化工作区
- 安装并启动对象
- 添加并执行用例
- 查看 execution 记录
- 生成报告
- 可选销毁工作区
如果你要按当前版本上手，请优先阅读这些文档：

- [README.md](../../README.md)
- [docs/user-guide/basic-usage.md](../../docs/user-guide/basic-usage.md)
- [docs/user-guide/mysql-full-lifecycle.md](../../docs/user-guide/mysql-full-lifecycle.md)

不过，当前权威说明仍然是下面这些文档。

## 当前建议

- 想快速体验 CLI 主线：看 `docs/user-guide/basic-usage.md`
- 想跑真实对象生命周期案例：看 `docs/user-guide/mysql-full-lifecycle.md`
- 想做 Python 集成：看 `docs/api/python-api-guide.md`

## 关于 `demo.sh`

你可以直接运行：

```bash
bash examples/quickstart/demo.sh
```

如果想让脚本结束后自动销毁工作区：

```bash
bash examples/quickstart/demo.sh --cleanup
```

如果想保留工作区继续查看产物：

```bash
bash examples/quickstart/demo.sh --keep-workspace
```

即便如此，文档和主线行为解释仍以 `README` 与 `docs/user-guide/` 为准。
