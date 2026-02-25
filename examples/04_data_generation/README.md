# 示例 4: 数据生成与参数化

本示例展示如何使用 ptest 的数据生成功能进行参数化测试。

## 运行方式

```bash
# 运行测试
pytest cases/ -v

# 或使用 ptest data generate
ptest data generate username --count 10 --format sql
```

## 功能说明

### 数据生成器
- 内置类型: name, email, phone, address, uuid, date, etc.
- 格式支持: JSON, CSV, SQL, YAML

### 参数化测试
- 使用 ${data:field} 引用生成的数据
- 支持循环生成测试数据
- 支持数据文件导入

## 下一步

- 示例 5: 测试套件组织
