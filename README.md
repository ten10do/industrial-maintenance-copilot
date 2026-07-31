# 工业设备运维工单 Copilot

面向工业设备运维场景的智能助手，提供故障上报、工单管理、知识库检索和 AI 辅助诊断能力。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 15 (App Router) + React 19 + Tailwind CSS 3 + TypeScript |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy + Pydantic v2 |
| 数据库 | SQLite（默认）/ PostgreSQL（可选） |
| 测试 | Jest + Testing Library + Playwright（前端）/ pytest（后端） |
| 容器化 | Docker + Docker Compose |

## 项目结构

```
industrial-maintenance-copilot/
├── apps/
│   ├── api/               # FastAPI 后端
│   │   ├── app/
│   │   │   ├── ai/         # Copilot AI 服务
│   │   │   ├── api/v1/     # REST API 端点
│   │   │   ├── core/       # 安全、配置
│   │   │   ├── db/         # 数据库会话
│   │   │   ├── models/     # SQLAlchemy 模型
│   │   │   └── schemas/    # Pydantic 模型
│   │   ├── tests/          # 后端测试
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── .env
│   └── web/                # Next.js 前端
│       ├── src/
│       │   ├── app/        # App Router 页面
│       │   ├── components/ # 可复用组件
│       │   └── lib/        # API 客户端、类型、认证
│       ├── e2e/            # Playwright E2E 测试
│       ├── __tests__/      # Jest 单元测试
│       ├── Dockerfile
│       └── package.json
├── docker-compose.yml
├── .gitignore
└── README.md
```

## 本地启动

### 前置要求

- Python 3.11+
- Node.js 22+
- npm 10+

### 1. 启动后端

```bash
cd apps/api

# 安装依赖
pip install -r requirements.txt

# 启动服务（首次启动会自动创建 SQLite 数据库并填充演示数据）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端启动后：
- API 地址：http://localhost:8000
- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 2. 启动前端

```bash
cd apps/web

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端启动后：http://localhost:3000

### 3. 演示账号

所有账号密码均为 `Demo123456`：

| 邮箱 | 角色 | 姓名 |
|------|------|------|
| admin@example.com | 系统管理员 | 系统管理员 |
| supervisor@example.com | 主管 | 张主管 |
| tech1@example.com | 维修工程师 | 李工程师 |
| tech2@example.com | 维修工程师 | 王工程师 |
| tech3@example.com | 维修工程师 | 刘工程师 |

## 工单生命周期

工单按以下状态流转，服务端会拒绝所有未列出的跨状态操作：

```text
待分派 → 已分派 → 已接受 → 处理中 → 待验收 → 已完成
                       ↕ 暂停
                                  └→ 已退回 → 重新处理 → 待验收
```

- 主管或管理员负责创建、编辑、分派、验收、退回和取消工单。
- 被分派的维修工程师负责接单、开始、暂停/恢复、填写检查清单与维修记录，以及提交完工。
- 完工前必须填写根本原因、处理措施和测试结果，完成必做检查项，并至少记录一条维修日志、工时和测试步骤。
- 高风险工单还必须提供完工照片；验收退回后，已上传的照片会保留供重新提交使用。
- 状态变化、分派和验收分别记录在状态历史、分派历史和验收记录中；验收通过后生成维修报告和知识库候选条目。

## Docker Compose 启动

```bash
# 构建并启动所有服务
docker compose up --build

# 后台运行
docker compose up -d --build

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

服务地址：
- 前端：http://localhost:3000
- API：http://localhost:8000
- API 文档：http://localhost:8000/docs

## 环境变量

### 后端 (`apps/api/.env`)

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_ENV` | 运行环境 | `development` |
| `API_HOST` | 监听地址 | `0.0.0.0` |
| `API_PORT` | 监听端口 | `8000` |
| `FRONTEND_URL` | 前端地址（CORS） | `http://localhost:3000` |
| `DATABASE_URL` | 数据库连接串 | 空（使用 SQLite） |
| `SECRET_KEY` | JWT 签名密钥 | 生产环境务必更换 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token 过期时间 | `1440` |
| `AI_ENABLED` | 启用真实 AI | `false`（Mock 模式） |
| `SEED_ON_STARTUP` | 自动初始化演示数据 | `true` |

### 前端 (`apps/web`)

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `API_BASE_URL` | 服务端 API 地址 | 空（开发环境使用 Next.js rewrites 代理） |
| `NEXT_PUBLIC_API_URL` | 浏览器端 API 地址 | 空（使用相对路径） |

### API_BASE_URL 说明

- **服务端渲染（SSR）**：Next.js 服务端使用 `API_BASE_URL` 访问后端 API
- **客户端渲染（CSR）**：浏览器直接通过 Next.js rewrites 代理访问，无需设置
- **Docker 环境**：设置 `API_BASE_URL=http://api:8000`（容器网络中的 API 服务名）
- **本地开发**：无需设置，Next.js rewrites 自动代理到 `localhost:8000`

## 数据库说明

- 默认使用 SQLite（`DATABASE_URL` 为空），数据库文件：`apps/api/maintenance.db`
- 首次启动且数据库为空时自动创建表结构并填充演示数据（`SEED_ON_STARTUP=true`）
- 如需使用 PostgreSQL，在 `DATABASE_URL` 中配置连接串

## 数据库迁移

项目使用 SQLAlchemy `create_all` 创建新数据库，并在应用启动时执行幂等的兼容升级。

启动时自动执行：
1. 检查并升级旧数据库中的工单检查清单字段
2. 按标准清单内容回填安全、诊断、维修和测试类别
3. 创建尚不存在的表
4. 如果 `SEED_ON_STARTUP=true` 且数据为空，填充演示数据

迁移回归测试：

```bash
cd apps/api
pytest tests/test_database_migrations.py
```

## 测试

### 后端测试

```bash
cd apps/api
pytest
```

### 前端单元测试

```bash
cd apps/web

# 运行全部测试
npm test

# 监听模式
npm run test:watch

# 覆盖率报告
npm run test:coverage
```

### Playwright E2E 测试

```bash
cd apps/web

# 无头运行
npm run test:e2e

# 有头运行（可视化调试）
npm run test:e2e:headed

# Playwright UI 模式
npm run test:e2e:ui

# 针对 Docker 环境运行
E2E_BASE_URL=http://localhost:3000 npm run test:e2e
```

E2E 测试前提：
1. 后端运行在 `localhost:8000`
2. 前端运行在 `localhost:3000`（或通过 `E2E_BASE_URL` 指定）
3. 已安装 Playwright 浏览器：`npx playwright install chromium`

生命周期专项回归使用 Playwright runner（不要通过 Jest/Vitest 执行）：

```bash
npx playwright test e2e/work-order-lifecycle.spec.ts
```

## TypeScript 检查

```bash
cd apps/web
npm run typecheck
```

## ESLint

```bash
cd apps/web
npm run lint
```

## 生产构建

```bash
cd apps/web
npm run build
npm start
```

构建输出支持 Next.js standalone 模式，适用于 Docker 部署。

## 健康检查

```bash
# 后端健康检查（包含数据库连通性）
curl http://localhost:8000/health

# 返回示例
# {"status":"ok","database":"ok","ai_enabled":false}
```

## Mock AI 模式

当 `AI_ENABLED=false` 或 `LLM_API_KEY` 为空时，系统使用 Mock AI 模式：
- Copilot 问答使用基于规则的关键词匹配
- 不调用外部 LLM API
- E2E 测试在 Mock 模式下稳定可重复

如需启用真实 AI：
1. 设置 `AI_ENABLED=true`
2. 配置 `LLM_API_KEY`（支持 OpenAI 兼容 API）
3. 根据需要调整 `LLM_API_BASE` 和 `LLM_MODEL`

## 常见故障处理

### 后端启动失败

```bash
# 检查端口占用
netstat -ano | findstr :8000

# 删除旧数据库重新初始化
del apps\api\maintenance.db
```

### 前端 API 请求失败

- 确认后端已启动在 `localhost:8000`
- 确认 CORS 配置：`FRONTEND_URL` 需与前端地址一致
- 开发环境确认 Next.js rewrites 配置正确

### Docker build 失败

- Windows 环境下确保 Docker Desktop 使用 Linux 容器
- CRLF 换行符问题：`git config core.autocrlf input`

### E2E 测试超时

- 确保前后端均已启动
- 清除旧的测试输出：手动删除 `test-results/`、`e2e-output/`、`playwright-report/`
