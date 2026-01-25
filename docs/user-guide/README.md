# ptest - 综合测试框架

ptest是一个全面的测试框架，用于管理测试环境、测试对象和测试用例。

## 安装

```bash
pip install .
```

或者从源码安装：

```bash
git clone https://github.com/wu-champion/ptest.git
cd ptest
pip install -e .
```


## 使用方法
```bash
ptest init --path /home/test/
```

### 初始化测试环境
以mysql为例
```bash
# 安装MySQL对象
ptest obj install mysql my_mysql_db --version 9.9.9 # 版本号改成自己需要的版本号

# 启动MySQL对象
```

### 管理测试对象
```bash
ptest obj stop my_mysql_db

# 列出所有对象
ptest obj list
```

### 管理测试用例
```bash
# 添加测试用例
ptest case add mysql_connection_test '{"type": "connection", "description": "Test MySQL connection"}'

# 运行特定测试用例
```

### 生成报告
```bash
# 生成HTML报告
ptest report --format html

# 生成JSON报告
```

### 查看状态
```bash
ptest status
```

### 命令别名
同时提供了```p```作为简写命令：
```bash
p init --path /home/test/
p obj install mysql my_mysql_db
p run all
```