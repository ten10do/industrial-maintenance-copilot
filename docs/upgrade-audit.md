# 智能运维平台升级审计

审计日期：2026-07-31

## 仓库与 Git 基线

- 仓库：`industrial-maintenance-copilot`
- 当前工作目录：仓库根目录
- 升级前分支：`master`
- 默认分支：远端未配置 `origin/HEAD`，根据上游跟踪关系与 CI 配置判定为 `master`
- 升级前 HEAD：`35ab3159784501788d839b5eb35acc0e6e882d71`
- 远端：`origin`（GitHub）
- 升级前工作区：干净
- 已修改文件：无
- 未跟踪文件：无
- 暂存区：无
- 安全备份：因工作区无未提交修改，不需要创建差异备份或备份分支
- 开发分支：`feat/intelligent-maintenance-platform`

本文不记录本地绝对路径、密钥、令牌或环境变量实际值。

## 目录与技术栈

```text
apps/
  api/          FastAPI API、SQLAlchemy 模型、迁移、服务与 pytest
  web/          Next.js App Router、React、TypeScript、Jest、Playwright
docs/           部署、发布和产品文档
infrastructure/ 基础设施配置
sample-data/    示例数据
scripts/        演示数据维护脚本
.github/        GitHub Actions
```

| 范围 | 当前实现 |
| --- | --- |
| 前端 | Next.js 15、React 19、TypeScript、Tailwind CSS、React Query、Recharts |
| 后端 | Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2 |
| 数据库 | 本地 SQLite；部署与 CI 支持 PostgreSQL 16 |
| 迁移 | Alembic 依赖已安装；当前运行时使用幂等 `upgrade_schema` 兼容旧库 |
| AI Provider | OpenAI 兼容 Chat Completions 客户端；无 Key 自动降级 Mock |
| RAG | 知识文章分块模型；关键词检索、设备类型和故障代码加权；相似历史工单检索 |
| 测试 | pytest、Jest、Testing Library、Playwright |
| 交付 | Docker、Docker Compose、GitHub Actions、Netlify Web、Render API |

## 当前有效功能

- 登录、角色权限和管理员/主管/工程师工作台
- 故障自然语言上报、Mock/真实 AI 结构化解析
- 故障上报转工单
- 工单创建、分派、接单、执行、暂停、恢复、提交、验收、退回和取消
- 安全检查清单、维修日志、工时、备件、附件、维修报告
- 设备台账、设备二维码和设备历史摘要
- 知识库、关键词 RAG、带引用的 Copilot 问答
- Mock AI 零配置运行、SQLite 零配置运行
- 升级前验证：后端 `82 passed`；前端验证命令需在 Windows 使用 `npm.cmd`

## 升级映射

| 原能力 | 升级后位置 | 增量能力 |
| --- | --- | --- |
| 运维管理仪表盘 | 智能运维驾驶舱 | 设备健康、实时告警、风险预测、维护窗口 |
| 设备台账 | 设备资产中心 | 额定参数、健康分、传感器、遥测、风险与维护计划 |
| 故障上报 | 异常与故障中心 | 规则检测自动上报、证据链、诊断与预测关联 |
| 维修工单 | 智能工单中心 | 异常自动建单、人员/备件建议、预测性工单 |
| AI 助手 | 运维 Agent | 诊断、RAG、维修策略、风险解释与效果验证 |
| 知识库 | 运维知识中心 | 手册/SOP/案例检索和维修闭环沉淀 |
| 无设备接入 | Equipment Gateway | 固定随机种子的电机/轴承软件仿真 |
| 人工安全清单 | 审批与安全控制 | 高风险设备命令强制人工审批、留痕后执行 |

## 首期架构边界

- 设备接入统一经 `EquipmentGateway`；首期仅启用可重复的 Mock 设备仿真。
- AI 调用继续经统一 Provider；CI 和无 Key 环境固定使用 Mock。
- 消息通知经 Gateway 抽象；首期落库到站内通知。
- 遥测、规则异常检测、确定性预测和工单编排不依赖付费服务。
- AI 只生成诊断和建议，不直接执行高风险设备命令。
- 新模型沿用 SQLAlchemy 与现有数据库，不引入消息队列、时序数据库或额外中间件。

## 验收目标

1. 正常及八类异常场景可由软件模拟器稳定复现。
2. 遥测可被持久化并形成异常、诊断、预测、维修建议和自动工单。
3. 人员与备件建议可追溯；高风险命令未经批准无法执行。
4. 维修后可比较前后遥测和健康分，结果可沉淀为知识案例。
5. 原有工单生命周期和 Copilot 功能继续通过既有测试。
6. 后端测试、前端测试、类型检查、Lint 和生产构建全部真实通过。

## 升级验证结果

| 验证项 | 结果 |
| --- | --- |
| Ruff format / lint | passed（升级涉及的 Python 代码） |
| MyPy strict | passed（7 个新增核心模块） |
| 后端 pytest | 96 passed |
| 后端覆盖率 | 73.38%；智能运维服务 85% |
| 前端 Jest | 16 suites / 220 passed |
| 前端覆盖率 | Statements 52.47%，Branches 49.11%，Functions 39.50%，Lines 53.01% |
| TypeScript | passed |
| ESLint | passed |
| Next.js production build | passed，19 个应用路由 |
| Playwright 本地 E2E | 23 passed / 1 个公开环境 Smoke 按配置跳过 |
| 智能运维专项 E2E | 轴承磨损遥测 → 诊断/RAG → 预测 → 调度/预留 → 审批 → 维修 → 验证 → 案例草稿 |
| SQLite 迁移往返 | upgrade → downgrade → upgrade passed，旧工单数据保留 |
| Docker CLI | 当前执行环境未安装，未执行容器构建 |

当前仓库使用 Netlify Web、Render API 与 PostgreSQL 的协同部署结构，且没有 Sites 托管清单。为避免只发布前端而连接到旧 API，本次未覆盖现有线上环境；发布时应按 `docs/deployment.md` 同步升级 API、数据库和 Web。

## 最终交付审计

- 最终开发分支：`feat/intelligent-maintenance-platform`
- 最终验收前安全分支：`backup/pre-intelligent-maintenance-finalization`
- 未提交工作区的完整 diff 与未跟踪文件清单已保存到仓库外；本文不记录本地路径。
- Git 历史未重写，未执行 hard reset、clean、force push 或生产部署。

| 验收能力 | 真实实现 |
| --- | --- |
| 设备资产、传感器、遥测持久化 | SQLAlchemy 模型、API 与资产/监测页面 |
| 固定种子八类仿真 | `MockEquipmentGateway` 与仿真控制器 |
| 数据质量、异常、健康分 | 确定性规则与重复开放异常去重 |
| 风险、剩余寿命、维护窗口 | 可重复的规则预测记录 |
| 结构化诊断与 RAG | `FaultDiagnosis`、已发布知识引用、低置信度人工复核 |
| Agent 策略与审计 | `AgentRun`、`ToolInvocation` 逐步骤留痕 |
| 工单自动化与调度 | 高风险自动工单、技能/负载匹配 |
| 备件推荐与预留 | `SparePartReservation` 记录预留和缺口，不产生负库存 |
| 高风险审批 | 未批准不调用 Gateway；主管批准后执行；重复批准幂等 |
| 维修验证 | 通过关闭工单；失败转 `returned` 重新处理 |
| 知识沉淀 | 自动生成 `draft` 案例，等待人工审核 |
| 原工单 Copilot | 原 API、页面、状态机、RAG 引用与既有测试保留 |
| Mock 完整闭环 | 后端专项测试与 Playwright 完整轴承磨损流程 |

### 迁移结论

早期仓库虽然安装了 Alembic 依赖，但没有可安全接管既有数据库的 revision 历史。本次继续使用可审计的幂等兼容迁移入口：先补齐旧表字段，再创建智能运维表。提供测试用安全 downgrade，仅删除智能运维表并保留旧工单表和增量兼容列。生产回滚推荐保留新表、只回退应用。

SQLite 的空库升级、旧表补列、幂等执行、降级/再升级、外键、索引和 UTC 类型均已本地验证。PostgreSQL 验证配置在 GitHub Actions 中，只有对应 CI job 实际成功后才可声明 PostgreSQL 与 Docker Compose 通过。
