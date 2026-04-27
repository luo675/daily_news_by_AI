# Application Pipeline 验证说明

目标：确认 `daily_news` 的 application pipeline 在当前机器上走真实 PostgreSQL，而不是 SQLite fallback。

## 前置条件

在当前 shell 中显式设置以下环境变量：

```powershell
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "5432"
$env:DB_NAME = "daily_news"
$env:DB_USER = "postgres"
$env:DB_PASSWORD = "<your-password>"
```

目标数据库需要满足：

- PostgreSQL 可连接
- 已安装 `pgvector` 扩展

## 验证命令

```powershell
.\.venv\Scripts\python.exe scripts\verify_application_persistence_db.py
.\.venv\Scripts\python.exe scripts\verify_application_api.py
```

## 通过标准

- `verify_application_persistence_db.py` 输出包含 `Database mode: PostgreSQL`
- `verify_application_api.py` 中 `persist=true` 默认路径返回成功
- 如失败，脚本会输出明确层级：
- `environment variable`
- `DB connection`
- `pgvector`
- `schema/bootstrap`
- `API call`

## 说明

- 不接受 SQLite fallback 作为完成结果
- 不接受 `persist=true` 验证被跳过
- 如果 PostgreSQL、`pgvector` 或 schema 初始化有问题，应先修复验证层暴露出的最小问题，再继续后续任务
