# DataQuery Copilot 部署手册

## 部署形态

第五阶段提供一套前后端分离的 Render Blueprint：

```text
React 静态站点  -->  FastAPI 服务  -->  SQLite + DeepSeek
```

- 前端服务：构建 `frontend/`，发布 `frontend/dist/`。
- API 服务：启动 `api.main:app`，健康检查为 `/api/health`。
- 示例数据库：部署构建阶段运行 `scripts/prepare_demo_db.py` 自动准备。

## Render 部署

1. 将仓库推送到 GitHub。
2. 在 Render 中选择 **New → Blueprint**，连接该仓库。
3. Render 读取根目录的 `render.yaml`，创建 API 和前端两个服务。
4. 在 API 服务中设置 `DEEPSEEK_API_KEY`。
5. 在前端服务中设置 `VITE_API_BASE_URL`，值为 API 服务的完整 HTTPS 地址，例如：

   ```text
   https://dataquery-copilot-api.onrender.com
   ```

6. 将前端最终地址填入 API 服务的 `CORS_ORIGINS`，多个地址用逗号分隔。
7. 重新部署两个服务。
8. 打开 API 的 `/api/health` 和前端页面验证状态。

注意：示例 SQLite 数据随服务构建生成，Render 免费实例重启后会重新构建或恢复到镜像中的示例数据。真实业务数据不应依赖本地 SQLite，应迁移到持久化数据库。

## Docker 本地验证

API 镜像使用根目录的 `Dockerfile.api`：

```bash
docker build -f Dockerfile.api -t dataquery-copilot-api .
docker run --rm -p 8000:8000 \
  -e DEEPSEEK_API_KEY=your_api_key_here \
  -e CORS_ORIGINS=http://localhost:5173 \
  dataquery-copilot-api
```

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
| API | `DB_PATH` | 默认 `data/query.db` |
| API | `TABLE_NAME` | 默认 `orders` |
| API | `CORS_ORIGINS` | 允许访问 API 的前端地址 |
| 前端 | `VITE_API_BASE_URL` | API 完整 URL；本地开发留空使用 Vite 代理 |

## 部署验收

```bash
curl https://<api-host>/api/health
curl https://<api-host>/api/schema
curl https://<api-host>/api/quality
```

浏览器端应确认：

- 顶栏显示 `API 已连接`。
- 左侧显示真实 Schema 和数据质量。
- 查询按钮可用，并能看到阶段状态。
- 前端域名不产生 CORS 错误。
- API Key 不出现在 HTML、浏览器响应或 Git 历史中。

## 当前交付状态

部署配置已经提交到仓库，但尚未绑定用户的 Render/Vercel 账号，也没有伪造线上地址。完成实际部署后，只需把真实前端地址和 API 地址补入 README。
