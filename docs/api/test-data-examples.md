# 测试数据示例

这个文件提供文档和示例代码中可复用的测试数据片段。

## SQL 测试数据

```sql
CREATE TABLE test_users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    status TEXT NOT NULL
);

INSERT INTO test_users VALUES (1, 'Alice', 'alice@example.com', 'active');
INSERT INTO test_users VALUES (2, 'Bob', 'bob@example.com', 'inactive');
```

## JSON 测试数据

```json
{
  "users": [
    {"id": 1, "name": "Alice", "email": "alice@example.com", "status": "active"},
    {"id": 2, "name": "Bob", "email": "bob@example.com", "status": "inactive"}
  ]
}
```
