# DataQuery Copilot 部署手册

## 部署形态

第五阶段提供一套前后端分离的 Render Blueprint：

```text
React 静态站点  -->  FastAPI 服务  -->  SQLite + DeepSeek
```

- 前端服务：构建 `frontend/`，发布 `frontend/dist/`。
- API 服务：启动 `api.main:app`，健康检查为 `/api/health`（免鉴权轻量探针，只回报进程与库文件状态；业务健康接口为 `/api/v1/health`，需 `X-API-Key`）。
- 示例数据库：部署构建阶段运行 `scripts/prepare_demo_db.py` 自动准备在 `data/query.db`。

## Render 部署

1. 将仓库推送到 GitHub。
2. 在 Render 中选择 **New → Blueprint**，连接该仓库。
3. Render 读取根目录的 `render.yaml`，创建 API 和前端两个服务。
4. API 服务挂载 1GB 持久磁盘到 `/var/data`，`DB_PATH=/var/data/query.db`（P1-20）。应用启动（lifespan）时若挂载点没有库文件，会自动把构建期示例库 `data/query.db` 复制过去，保证首次启动可用；之后所有数据（Key 表、配额、上传数据集）都落在持久磁盘上，重新部署不丢失。
5. 在 API 服务中设置 `DEEPSEEK_API_KEY`。
6. 在前端服务中设置 `VITE_API_BASE_URL`，值为 API 服务的完整 HTTPS 地址，例如：

   ```text
   https://dataquery-copilot-api.onrender.com
   ```

7. 将前端最终地址填入 API 服务的 `CORS_ORIGINS`，多个地址用逗号分隔。
8. 重新部署两个服务。
9. 打开 API 的 `/api/health` 和前端页面验证状态。

注意：真实业务数据现在落在 Render 持久磁盘 `/var/data` 上；但单机 SQLite 仍是单点，请按下方「备份与恢复」配置每日备份。若并发增长超出 SQLite/单实例能力，应迁移托管 PostgreSQL（另行排期）。

## Docker 本地验证

API 镜像使用根目录的 `Dockerfile.api`：

```bash
docker build -f Dockerfile.api -t dataquery-copilot-api .
docker run --rm -p 8000:8000 \
  -e DEEPSEEK_API_KEY=your_api_key_here \
  -e CORS_ORIGINS=http://localhost:5173 \
  dataquery-copilot-api
```

生产镜像默认 `DQC_DISABLE_DOCS=1`（P2-31）：`/docs`、`/redoc`、`/openapi.json` 在容器内返回 404，健康探针不受影响。本地开发若需查看文档，用 `docker run -e DQC_DISABLE_DOCS=0 ...` 或直接在宿主机运行。

前端仍在另一个终端运行：

```bash
cd frontend
npm ci
npm run dev
```

## 环境变量

| 服务 | 变量 | 说明 |
|---|---|---|
| API | `DEEPSEEK_API_KEY` | 必填，不能提交到 Git |
| API | `MODEL_NAME` | 默认 `deepseek-chat` |
| API | `DB_PATH` | 默认 `data/query.db`；Render Blueprint 指向挂载点 `/var/data/query.db` |
| API | `TABLE_NAME` | 默认 `orders` |
| API | `CORS_ORIGINS` | 允许访问 API 的前端地址 |
| API | `DQC_JSON_LOGS` | `1` 开启结构化 JSON 日志（生产镜像默认开启） |
| API | `DQC_DISABLE_DOCS` | `1` 关闭 `/docs`、`/openapi.json`（生产镜像与 Render Blueprint 默认开启） |
| API | `WEB_CONCURRENCY` | 保持 `1`（限流/配额/指标为单进程内存态，多 worker 启动时会打告警） |
| 前端 | `VITE_API_BASE_URL` | API 完整 URL；本地开发留空使用 Vite 代理 |

## 部署验收

```bash
# 免鉴权存活探针（Render 健康检查同款路径）
curl https://<api-host>/api/health

# v1 业务接口需要 X-API-Key（先用 scripts/manage_keys.py create 签发）
curl -H 'X-API-Key: <管理Key>' https://<api-host>/api/v1/health
curl -H 'X-API-Key: <管理Key>' https://<api-host>/api/v1/schema
curl -H 'X-API-Key: <管理Key>' https://<api-host>/api/v1/quality
```

浏览器端应确认：

- 顶栏显示 `API 已连接`。
- 左侧显示真实 Schema 和数据质量。
- 查询按钮可用，并能看到阶段状态。
- 前端域名不产生 CORS 错误。
- API Key 不出现在 HTML、浏览器响应或 Git 历史中。

## 备份与恢复（P2-48）

备份脚本使用 SQLite 在线备份 API（含 WAL 中已提交事务），可在服务运行中执行：

```bash
python scripts/backup_db.py --db /var/data/query.db --dir /var/data/backups --keep 14
```

### crontab 样例（每日 03:00，保留 14 份）

```cron
0 3 * * * cd /opt/dataquery-copilot && /usr/bin/python3 scripts/backup_db.py --db /var/data/query.db --dir /var/data/backups --keep 14 >> /var/log/backup_db.log 2>&1
```

### systemd timer 样例

`/etc/systemd/system/dqc-backup.service`：

```ini
[Unit]
Description=DataQuery Copilot SQLite backup

[Service]
Type=oneshot
WorkingDirectory=/opt/dataquery-copilot
ExecStart=/usr/bin/python3 scripts/backup_db.py --db /var/data/query.db --dir /var/data/backups --keep 14
```

`/etc/systemd/system/dqc-backup.timer`：

```ini
[Unit]
Description=Daily DataQuery Copilot backup

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

启用：`systemctl enable --now dqc-backup.timer`。

### Render Cron Job 样例

在 Render 中新建 **Cron Job** 服务，指向同一仓库：

- Command：`pip install -r requirements.txt && python scripts/backup_db.py --db /var/data/query.db --dir /var/data/backups --keep 14`
- Schedule：`0 3 * * *`

注意：Render Cron Job 是独立实例，需与 API 服务挂载同一 disk 才能读到库文件；若不方便共享磁盘，可改为在 API 服务的 startCommand 前置后台循环，或迁移到托管数据库后使用其自带备份。

### 每月恢复演练

```bash
# 1. 取最新快照复制为演练库
cp /var/data/backups/query_<timestamp>.db /tmp/restored.db

# 2. 校验可打开且数据完整
python -c "import sqlite3; conn=sqlite3.connect('/tmp/restored.db'); print(conn.execute('PRAGMA integrity_check').fetchone()); print(conn.execute('SELECT COUNT(*) FROM orders').fetchone())"
```

演练通过标准：`integrity_check` 返回 `ok`，行数与业务预期一致。

## 当前交付状态

部署配置已经提交到仓库，但尚未绑定用户的 Render/Vercel 账号，也没有伪造线上地址。完成实际部署后，只需把真实前端地址和 API 地址补入 README。
