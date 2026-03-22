# ptest 开发者文档

`development/` 目录面向框架开发者，提供开发流程、工程规范和质量要求。

## 文档索引

- [development-guide.md](development-guide.md)
  - 开发环境、模块结构、扩展方式
- [CODING_STANDARDS.md](CODING_STANDARDS.md)
  - 代码风格、命名、类型注解、错误处理规范
- [CODE_QUALITY_GUIDE.md](CODE_QUALITY_GUIDE.md)
  - Ruff / MyPy / 测试检查要求
- [CI_CD_GUIDE.md](CI_CD_GUIDE.md)
  - 持续集成、发布流程与本地验证方式
- [docker-testing-guide.md](docker-testing-guide.md)
  - Docker 相关测试说明
- [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md)
  - 文档归档、分类、更新和链接维护规则

## 使用建议

- 新成员先读 `development-guide.md`
- 提交代码前对照 `CODING_STANDARDS.md` 和 `CODE_QUALITY_GUIDE.md`
- 需要理解流水线时再看 `CI_CD_GUIDE.md`
- 涉及新增或重组文档时，同时查看 `DOCUMENTATION_GUIDE.md`
