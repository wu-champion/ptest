# 示例 2: 数据库测试

本示例展示如何使用 ptest 进行数据库测试，包括 MySQL/PostgreSQL/SQLite。

## 前置要求

```bash
# 安装数据库驱动
pip install pymysql psycopg2-binary

# 或使用 Docker 运行 MySQL
docker-compose up -d
```

## 运行方式

```bash
# 使用 Docker 启动 MySQL
docker-compose up -d

# 运行测试
pytest cases/ -v

# 清理
docker-compose down
```

## 测试用例说明

### test_user_crud
- 描述: 测试用户 CRUD 操作
- 类型: SQL 测试
- 操作: 创建、读取、更新、删除用户

## 预期输出

```
PASSED: test_user_crud
  - Create User: ✓
  - Read User: ✓
  - Update User: ✓
  - Delete User: ✓
```

## 数据库配置

配置位于 `ptest_config.yaml`:
- host: localhost
- port: 3306
- database: test_db
- user: test_user
- password: test_pass

## 扩展练习

1. 添加更多 SQL 断言
2. 测试事务回滚
3. 测试批量操作
4. 添加 setup/teardown 钩子

## 下一步

- 示例 3: Mock 服务使用
- 示例 4: 数据生成与参数化
