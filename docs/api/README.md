# 测试数据示例
# 这个文件包含测试用例的示例数据

## SQL测试数据
```sql
-- 创建测试表
CREATE TABLE test_users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    status TEXT NOT NULL
);

-- 插入测试数据
INSERT INTO test_users VALUES (1, 'Alice', 'alice@example.com', 'active');
INSERT INTO test_users VALUES (2, 'Bob', 'bob@example.com', 'inactive');
```

## JSON测试数据
```json
{
    "users": [
        {"id": 1, "name": "Alice", "email": "alice@example.com", "status": "active"},
        {"id": 2, "name": "Bob", "email": "bob@example.com", "status": "inactive"}
    ]
}
```