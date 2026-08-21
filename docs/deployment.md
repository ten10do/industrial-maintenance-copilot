# 生产部署与回滚

本文只准备发布流程，不表示本次改动已经部署。推荐拓扑为 Netlify Web、Render API/Worker/Scheduler、托管 PostgreSQL 与托管 Redis。

## 强制发布顺序

1. 备份生产 PostgreSQL。
2. 在副本或受控窗口执行 `alembic upgrade head`。
3. 部署 Render API。
4. 验证 `/health` 和 `/ready`。
5. 部署 Worker 与 Scheduler。
6. 验证新旧工单 API 兼容性。
7. 更新 Netlify `API_BASE_URL`。
8. 部署 Netlify Web。
9. 执行生产 Smoke。
10. 保留回滚窗口并观察日志与指标。

禁止只部署新版 Web。新版页面依赖智能运维 API、表结构和运行时，继续连接旧 API 会产生不可用路由。

## 数据库备份与迁移前检查

使用平台快照或 `pg_dump` 创建加密备份，示例不包含真实连接串：

```bash
pg_dump --format=custom --no-owner --file=pre-upgrade.dump "$DATABASE_URL"
pg_restore --list pre-upgrade.dump >/dev/null
```

迁移前确认：

- 备份可读且恢复责任人、位置和保留期明确；
- PostgreSQL 版本、磁盘空间、连接数和锁等待正常；
- 应用角色具有目标 schema 的 `USAGE`、`CREATE`、`ALTER` 权限；
- 当前旧工单记录数、关键设备数和最新备份时间已记录；
- `SEED_ON_STARTUP=false`；
- 维护窗口和回滚决策人已确认。

Alembic revision `20260811_01` 是可接管基线：首次升级时调用幂等兼容逻辑补齐旧设备/清单字段并创建缺失表，然后写入 `alembic_version`。新库、未版本化旧库和已经具备当前结构的数据库都使用同一条 `alembic upgrade head` 路径；后续结构变化必须新增 revision，应用启动不再直接调用兼容升级器。

基线可能接管包含旧工单的生产库，因此它明确禁止破坏性 `alembic downgrade base`。生产回滚应保留数据库结构并回退应用；只有经过审批的备份恢复才能回退基线前的数据结构。

生产环境禁止 `AUTO_MIGRATE_ON_STARTUP=true`。Render 使用 `preDeployCommand` 在新版本切流前单独执行迁移；API、Worker 和 Scheduler 只检查数据库是否处于 Alembic head，未迁移时拒绝就绪或停止业务循环。Docker Compose 的单个 API 容器在启动 Uvicorn 前执行一次迁移。本地直接运行 API 时默认允许自动迁移。

受控迁移验证：

```bash
cd apps/api
alembic current
alembic upgrade head
python -m scripts.verify_migrations
```

CI 会在 PostgreSQL 16 上执行 Alembic upgrade、重复 upgrade、旧工单兼容数据与 Seed，并检查 revision、外键、索引与时区列。

## Render

`render.yaml` 定义 API、Worker、Scheduler 和 Redis。生产至少需要以下变量：

| 变量 | API | Worker/Scheduler | 说明 |
| --- | --- | --- | --- |
| `APP_ENV=production` | 是 | 是 | 生产标识 |
| `DATABASE_URL` | 是 | 是 | 托管 PostgreSQL TLS 连接串 |
| `AUTO_MIGRATE_ON_STARTUP=false` | 是 | 是 | 生产实例只校验版本，不执行 DDL |
| `REDIS_URL` | 是 | 是 | 托管 Redis TLS/私网连接串 |
| `SECRET_KEY` | 是 | 是 | 独立高熵 JWT Secret |
| `FRONTEND_URL` | 是 | 否 | 精确 Netlify Origin |
| `AI_ENABLED=true` | 是 | 是 | 生产解释型 AI 开关 |
| `LLM_API_KEY` / `LLM_MODEL` | 按需 | 按需 | 平台 Secret，不写入日志 |
| `EQUIPMENT_COMMAND_TIMEOUT_SECONDS` | 是 | 是 | 高风险命令转人工核验的超时阈值，默认 300 秒 |
| `SEED_ON_STARTUP=false` | 是 | 是 | 生产禁止自动演示数据 |
| `STORAGE_TYPE` 及存储凭证 | 是 | 按需 | 附件应使用持久化对象存储 |

API 启动命令：

API、Worker 和 Scheduler 会在启动时校验安全配置：非 `development` 环境若使用默认/短于 32 字符的 `SECRET_KEY`、启用 `SEED_ON_STARTUP` 或启用启动时自动迁移，进程会直接退出。生产环境也会拒绝种子数据使用的 `@example.com` 演示账号及其已有 Token。

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Worker 与 Scheduler：

```text
python -m app.runtime worker
python -m app.runtime scheduler
```

二者会验证 PostgreSQL/Redis 并更新带过期时间的心跳。平台健康检查应调用对应 `--check` 命令。

## Netlify

生产 Web 变量：

| 变量 | 说明 |
| --- | --- |
| `API_BASE_URL` | 已验证的 Render API HTTPS 地址 |
| `NODE_ENV=production` | Next.js 生产模式 |

不得把 `DATABASE_URL`、`REDIS_URL`、`SECRET_KEY` 或 LLM Key 配置为 `NEXT_PUBLIC_*`。浏览器只请求相对 `/api/v1/...`，Next.js 服务端代理到 API。

## CORS 与健康检查

`FRONTEND_URL` 必须是唯一生产 Web Origin，不使用 `*`。

- `/health`：API 进程存活与数据库探测，供排障。
- `/ready`：数据库 schema head、Redis（配置时）和 AI Provider 模式，供流量切换。
- Worker/Scheduler：`python -m app.runtime <role> --check`。

## 向后兼容

- 旧工单、故障上报、Copilot、知识库和原状态枚举保留。
- 新设备列为增量字段；旧数据会补齐稳定 `asset_uuid` 与默认健康数据。
- 新表可由旧应用忽略，因此生产回滚优先回退应用而不是回删表。
- 自动案例仅为草稿，不改变旧知识库发布流程。

## 回滚

1. 停止 Web 流量切换，保留当前数据库和日志。
2. Netlify 重新发布上一个已验证版本。
3. Render 回滚 API、Worker、Scheduler 到同一兼容版本。
4. 保留新增表与列，验证旧工单 API 可读写。
5. 只有数据本身损坏或迁移不可兼容时，才在审批后从备份恢复 PostgreSQL。
6. 通过正常 revert 提交回滚 Git；不 force push。

若必须演练 schema downgrade，先使用非生产副本执行 `downgrade_intelligent_schema`。该操作会删除智能运维数据，不能代替生产应用回滚。

## 发布后 Smoke Checklist

- `/health` 返回数据库 `ok`；
- `/ready` 返回 schema `head`，Redis 为 `ok`；
- Worker 与 Scheduler 心跳健康；
- 管理员、主管、工程师登录与权限正确；
- 原故障上报 → 工单 Copilot 流程可用；
- 设备列表、遥测、诊断、预测和智能工单可用；
- 未审批命令未执行，批准后有 Gateway 回执；
- 维修验证通过可关闭工单并生成待审核案例；
- Netlify 不请求 localhost，浏览器无服务端 Secret；
- 数据库记录数与迁移前基线一致或符合预期。

## 已有线上环境

仓库曾提供 Netlify Web 与 Render API 的 v1 演示地址。本次任务不执行生产部署；在按上述顺序完成协同升级前，应把现有线上环境视为旧版演示，不能作为本分支验收结果。
