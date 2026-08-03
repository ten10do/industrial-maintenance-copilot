# 基于 AI Agent 的工业设备智能运维与预测性维护平台

**AI-Powered Industrial Intelligent Maintenance and Predictive Maintenance Platform**

[![CI](https://github.com/ten10do/industrial-maintenance-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/ten10do/industrial-maintenance-copilot/actions/workflows/ci.yml)
![Next.js](https://img.shields.io/badge/Next.js-15.1.12-black)
![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.11-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1)
![License](https://img.shields.io/badge/release-v1.0.0-blue)

项目已从以工单为中心的被动运维系统，增量升级为以设备健康状态为中心的主动智能运维平台。原“工单 Copilot”全部能力保留在“智能工单中心”，并新增设备资产、软件仿真、实时遥测、异常检测、故障诊断、风险预测、维护策略、人员与备件调度、高风险操作审批和维修效果验证。

> 本项目是工业运维业务与 AI 工程能力演示系统。默认仅连接 Mock Equipment Gateway，不连接真实 PLC、SCADA 或生产设备，不应作为真实工业控制系统使用。AI 不会直接执行高风险操作。

## Existing v1 Demo

- Web：[https://industrial-maintenance-copilot.netlify.app](https://industrial-maintenance-copilot.netlify.app)
- API：[https://industrial-maintenance-copilot-api.onrender.com](https://industrial-maintenance-copilot-api.onrender.com)
- Health：[https://industrial-maintenance-copilot-api.onrender.com/health](https://industrial-maintenance-copilot-api.onrender.com/health)
- API Docs：[https://industrial-maintenance-copilot-api.onrender.com/docs](https://industrial-maintenance-copilot-api.onrender.com/docs)

> 本分支没有部署生产环境。以上地址是升级前的 v1 演示，在 API、数据库、Worker/Scheduler 与 Web 按发布顺序协同升级前，不能作为本平台验收结果。

公开演示账号使用同一密码：`Demo123456`。

| 账号 | 角色 | 适合体验 |
| --- | --- | --- |
| `admin@example.com` | 管理员 | 系统管理与完整数据视图 |
| `supervisor@example.com` | 主管 | 分派、验收、退回和报表 |
| `tech@example.com` | 维修工程师 | 接单、执行、暂停、恢复和完工提交 |

公开环境只包含虚构演示数据，AI 固定使用 Mock 模式。演示账号不具备 Netlify、Render 或 Neon 平台权限。

## Screenshots

| 主管仪表盘 | 故障上报 |
| --- | --- |
| ![主管仪表盘](docs/images/dashboard.png) | ![故障上报](docs/images/fault-report.png) |

| 工单执行详情 | 知识库 |
| --- | --- |
| ![工单执行详情](docs/images/work-order-detail.png) | ![知识库](docs/images/knowledge-base.png) |

![带结构化引用的 Mock Copilot](docs/images/copilot.png)

## Core Features

- 智能运维驾驶舱：设备健康分、实时异常、风险预测、审批与工单总览
- 设备资产中心：设备档案、额定参数、运行状态、健康分、风险、传感器与维护计划
- 软件设备仿真：工业电机与轴承八类场景、固定随机种子、启动/暂停/重置/单步
- 实时状态监测：振动 RMS、轴承温度、电流、电压、转速、负载、环境温度与累计运行时间
- 确定性异常检测：九类典型故障映射、证据链、诊断摘要和健康分更新
- 预测性维护：失效概率、剩余寿命、维护窗口、结构化诊断、RAG 引用与维修策略
- 运维 Agent 审计：Agent Run、Tool Invocation、低置信度人工复核
- 智能调度：人员技能/负载匹配、备件预留与库存缺口
- 安全控制：高风险命令先形成审批单，人工批准后才调用 Equipment Gateway
- 故障上报、结构化解析与一键转工单
- 工单创建、分派、接单、开始、暂停、恢复、完工、验收、退回和取消
- 服务端状态机、角色权限与非法转换拦截
- 安全检查清单、维修记录、工时、备件和附件
- 状态历史、分派历史、验收记录和审计轨迹
- 维修效果验证：通过后关闭工单，失败后自动重新打开
- 维修报告与待人工审核的知识案例草稿
- 知识检索和带来源引用的 Copilot 问答
- SQLite 零配置本地运行与 PostgreSQL 部署支持
- Docker、GitHub Actions 和公开环境 Smoke Test

完整升级审计见 [`docs/upgrade-audit.md`](docs/upgrade-audit.md)，架构与演示说明见 [`docs/intelligent-maintenance-platform.md`](docs/intelligent-maintenance-platform.md)。

## Business Workflow

```mermaid
flowchart LR
    A["设备数据采集"] --> B["实时状态监测"]
    B --> C["异常检测"]
    C --> D["Agent 诊断 + RAG"]
    D --> E["风险预测与维护窗口"]
    E --> F["维修策略与智能工单"]
    F --> G["人员与备件调度"]
    G --> H{"高风险操作审批"}
    H -->|批准| I["维修执行"]
    H -->|驳回| F
    I --> J["维修效果验证"]
    J --> K["运维知识沉淀"]
```

核心状态流转：

```text
待分派 → 已分派 → 已接受 → 处理中 → 待验收 → 已完成
                       ↕ 暂停
                                  └→ 已退回 → 重新处理 → 待验收
```

- 主管或管理员负责创建、编辑、分派、验收、退回和取消。
- 被分派的维修工程师负责接单、执行、维修记录与完工提交。
- 完工前必须满足必做检查项，并填写根因、措施、测试结果、维修日志和工时等证据。
- 高风险工单必须补充完工照片；退回后已有证据保留，可修正后重新提交。

## Architecture

```mermaid
flowchart LR
    User["维修工程师 / 主管"] --> Web["Next.js Web<br/>Netlify"]
    Web --> API["FastAPI<br/>Render"]
    API --> DB[("PostgreSQL 16")]
    API --> Redis[("Redis")]
    Worker["Worker / Scheduler"] --> DB
    Worker --> Redis
    API --> Equipment["Equipment Gateway<br/>Mock Simulator"]
    API --> Copilot["LLM Provider + RAG"]
    Copilot --> KB["Knowledge Base"]
    API --> Audit["Agent / Tool / Approval Audit"]
```

生产演示只维护一套部署：Netlify + Render + Neon。详细配置、重置与回滚步骤见 [部署指南](docs/deployment.md)。

## Tech Stack

| 层级 | 技术 |
| --- | --- |
| Web | Next.js 15.1.12、React 19、TypeScript、Tailwind CSS |
| API | Python 3.11、FastAPI、SQLAlchemy、Pydantic v2 |
| Database | PostgreSQL 16（生产/CI）/ SQLite（本地默认）、Redis（Worker/Scheduler） |
| AI | 可插拔 OpenAI 兼容接口；公开环境为确定性 Mock |
| Test | pytest、Jest、Testing Library、Playwright |
| Delivery | Docker、Docker Compose、GitHub Actions |

## Engineering Highlights

- 事务内状态转换与权限校验，拒绝未定义的跨状态操作
- 幂等数据库兼容迁移和空库 Seed
- 三重确认保护的演示数据重置脚本，无公开重置接口
- Next.js 同源 `/api` 代理，避免浏览器暴露数据库或服务端密钥
- CI 使用 PostgreSQL 16 与 Redis，覆盖迁移往返、后端、前端、Docker Compose 和真实浏览器 E2E
- `/health` 提供存活探测，`/ready` 验证数据库 schema、Redis 与 Provider 模式

## Test Coverage

当前发布基线：

| 范围 | 结果 |
| --- | --- |
| Backend | 96 passed；整体覆盖率 73.38%，智能运维服务 85% |
| Frontend | 16 suites / 220 tests passed |
| Frontend coverage | Statements 52.47%，Branches 49.11%，Functions 39.50%，Lines 53.01% |
| Playwright local E2E | 23 passed / 1 个公开环境 Smoke 按配置跳过 |
| Public demo Smoke | 1 passed |
| TypeScript / ESLint | 0 errors |
| Next.js production build | passed，19 个应用路由 |

公开 Smoke 使用 `@playwright/test`，与本地完整 E2E 分开执行。

## Local Development

前置要求：Python 3.11+、Node.js 22+、npm 10+。

启动 API：

```bash
cd apps/api
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动 Web：

```bash
cd apps/web
npm install
npm run dev
```

本地地址：

- Web：<http://localhost:3000>
- API：<http://localhost:8000>
- Swagger：<http://localhost:8000/docs>

未设置 `DATABASE_URL` 时，API 使用 `apps/api/maintenance.db`。空库首次启动会创建结构并填充演示数据。

## Docker

```bash
docker compose up --build
docker compose ps
docker compose logs -f
docker compose down -v --remove-orphans
```

容器服务地址仍为 Web `http://localhost:3000` 和 API `http://localhost:8000`。

## Environment Variables

后端以代码实际变量为准：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `APP_ENV` | 运行环境 | `development` |
| `DATABASE_URL` | SQLite 或 PostgreSQL 连接串 | 空，使用 SQLite |
| `REDIS_URL` | Worker/Scheduler 与就绪探测 | 本地单进程可留空 |
| `SECRET_KEY` | JWT 签名密钥 | 仅本地占位值 |
| `FRONTEND_URL` | 唯一允许的生产前端 CORS Origin | `http://localhost:3000` |
| `AI_ENABLED` | 启用真实模型 | `false` |
| `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI 兼容模型配置 | Mock 时不需要 Key |
| `SEED_ON_STARTUP` | 空库自动 Seed | `true` |

前端服务端使用 `API_BASE_URL` 生成同源 `/api` rewrite。浏览器只访问相对路径，不需要公开数据库、JWT 或 LLM Secret，也不需要重复配置 `NEXT_PUBLIC_API_URL`。

复制 [`.env.example`](.env.example) 后仅在本机填写值；不要提交 `.env`。

## Validation Commands

```bash
# Backend
cd apps/api
python -m scripts.quality
python -m mypy
python -m pytest --cov=app --cov-report=term-missing

# Frontend
cd ../web
npm run typecheck
npm run lint
npm test -- --runInBand
npm run build
npm run test:e2e

# Public demo smoke
PUBLIC_DEMO_SMOKE=true \
E2E_BASE_URL=https://industrial-maintenance-copilot.netlify.app \
E2E_TECHNICIAN_EMAIL=tech@example.com \
npx playwright test e2e/public-demo-smoke.spec.ts
```

PowerShell 请使用 `$env:NAME='value'` 设置对应环境变量。

## Deployment

完整步骤见 [docs/deployment.md](docs/deployment.md)。仓库中的部署入口为：

- `render.yaml`：Render API Blueprint
- `netlify.toml`：Netlify Next.js 构建与运行时
- `scripts/reset_demo_data.py`：受保护的演示数据重置

## Known Limitations

- 现有线上 v1 演示仍使用 Mock AI；本分支尚未部署生产。
- Render Free 实例闲置后会休眠，首次请求可能延迟约 50 秒。
- 文件上传使用 Render 本地临时文件系统；数据库记录持久化，但上传文件不保证跨部署保留。
- 不连接真实 PLC、SCADA、传感器或生产网络。
- 备件预留会记录库存占用/缺口，但不执行 ERP 级库存扣减。
- 规则健康分与剩余寿命是确定性/统计演示值；LLM 仅负责解释，不替代 OEM 诊断。
- 不提供生产级多租户隔离。

## Roadmap

- 对象存储与附件持久化
- 可配置的定时演示数据重置任务
- 生产级多租户、组织边界与审计导出
- 经安全评估后接入真实 LLM 与企业知识源
