> **Historical milestone document.**
> This document describes the July 2026 fault-report-to-work-order milestone.
> It does not represent the current architecture, test baseline, or project status.
> See [README.md](../../README.md) for the current system state.

---
# 故障上报转工单业务闭环 - 完项报告

**项目**: 工业设备运维工单 Copilot
**日期**: 2026-07-27
**分支范围**: 故障上报 → 维修工单 完整业务链路

---

## 一、概览

完成了从"故障上报"到"维修工单创建"的完整业务闭环。涵盖了前端页面（列表/详情/新建）、后端转换端点（含全部业务规则）、安全规则校验、角色权限控制、全局导航、后端自动化测试。

---

## 二、后端实现

### 2.1 新增端点

**`POST /api/v1/fault-reports/{id}/convert-to-work-order`**

文件: `apps/api/app/api/v1/endpoints/fault_reports.py`

| 特性 | 实现细节 |
|---|---|
| 权限控制 | `supervisor_or_admin` 依赖注入，技术员调用返回 403 |
| 事务保证 | 工单创建 + 检查清单 + 状态历史 + 故障状态更新在同一事务中 |
| 重复防护 | 应用层 `existing` 检查 + 数据库 `fault_report_id` 唯一性，返回 409 Conflict（含 `work_order_id`） |
| 状态校验 | `closed` 状态返回 400，已转换状态返回 409 |
| 优先级映射 | urgent→P1, high→P2, medium→P3, low→P4 |
| 安全规则 | `safety_risk` 强制≥P2；`downtime+production` 强制≥P2；用户可上调优先级但不能下调到阈值以下 |
| 检查清单 | 11 项默认安全操作清单（LOTO、断电、测试等）自动生成 |
| 工单编号 | 格式 `WO-{YEAR}-{序号，4位补零}` |
| 安全风险识别 | `has_safety_risk` 标记 + 高危关键词检测（高压/电气/液压/气压/高温/旋转） |
| 字段复制 | title、equipment_id、fault_description、fault_code_id 从 FaultReport 自动复制到 WorkOrder |

### 2.2 Schema 新增

文件: `apps/api/app/schemas/fault.py`

- `FaultReportDetail`: 继承 `FaultReportOut`，新增 `related_work_order_code`、`related_work_order_status`
- `ConvertToWorkOrderRequest`: `assignee_id`, `priority`, `planned_start_at`, `planned_end_at`, `notes`（全部可选）
- `ConvertToWorkOrderResponse`: `fault_report_id`, `work_order_id`, `work_order_code`, `priority`, `status`
- `FaultReportOut`: 新增 `related_work_order_id` 字段

---

## 三、前端实现

### 3.1 故障上报列表页

文件: `apps/web/src/app/fault-reports/page.tsx`

| 功能 | 状态 |
|---|---|
| 分页列表展示（标题/设备/紧急程度/状态/时间） | 完成 |
| 紧急程度彩色标签（critical 红/high 橙/medium 黄/low 灰） | 完成 |
| 影响标记图标（停机/影响生产/安全风险） | 完成 |
| "创建工单"按钮（仅待处理无关联工单时显示） | 完成 |
| "查看工单"按钮（已有关联工单时显示） | 完成 |
| 点击行跳转详情页 | 完成 |
| 空状态引导 | 完成 |
| 409 冲突处理（自动跳转已有工单） | 完成 |

### 3.2 故障上报详情页

文件: `apps/web/src/app/fault-reports/[id]/page.tsx`

| 状态处理 | 行为 |
|---|---|
| 加载中 | 骨架屏/Spinner |
| API 错误 | 错误提示 + 重试按钮 |
| 404（数据不存在） | "故障上报不存在"提示 + 返回列表 |
| 待处理 + 无关联工单 | 显示"转换为工单"按钮（带确认对话框） |
| 待处理 + 有关联工单 | 显示"查看工单"链接 |
| 已转换 | 显示关联工单编号和状态 |
| 安全风险 | 黄色警告横幅 |
| 技术员角色 | 隐藏转换按钮，显示权限不足提示 |

展示内容：标题、设备、故障代码、故障现象、紧急程度、详细描述、停机/生产/安全标记、发生时间、上报人、AI 解析数据（raw_text + parsed_fields JSON）、照片占位

### 3.3 新建故障上报页

文件: `apps/web/src/app/fault-reports/new/page.tsx`

**提交流程**: 创建故障上报 → 若勾选"同时创建工单"则调用 `convertFaultReportToWorkOrder` → 跳转工单详情

**异常处理**:
- 故障创建成功但工单转换失败 → toast 提示 + 跳转故障详情
- 409 冲突 → toast 提示 + 跳转已有工单
- API 错误 → toast 提示错误信息

### 3.4 API 客户端

文件: `apps/web/src/lib/api.ts`

新增功能:
- `ApiError` 类（status, code, workOrderId）结构化错误处理
- `ConvertToWorkOrderRequest/Response` 类型
- `convertFaultReportToWorkOrder(frId, data?)` 函数
- `request()` 函数增强：解析 `ApiErrorBody` 结构体

### 3.5 类型定义

文件: `apps/web/src/lib/types.ts`

新增:
- `Urgency` 类型 + `URGENCY_LABELS` 标签映射
- `FaultReportStatus` 类型 + `FAULT_REPORT_STATUS_LABELS` 标签映射
- `ApiErrorBody` 接口
- `ApiError` 类
- `ConvertToWorkOrderRequest/Response` 接口

---

## 四、全局导航

文件: `apps/web/src/app/app-layout.tsx`

| 特性 | 实现 |
|---|---|
| 桌面端 | 224px 固定侧边栏，含 Logo、用户信息、导航菜单、退出 |
| 移动端 | 固定顶栏 + 汉堡菜单 + 右滑抽屉 |
| 角色过滤 | 管理员看全部菜单，主管/技术员看不到"系统管理" |
| 路由高亮 | `pathname.startsWith()` 精确匹配 |
| 建设中标记 | 知识库显示"建设中"标签 |
| 登录页 | 无侧边栏 |
| 动画 | 移动端 `slide-in` CSS 动画 |

---

## 五、测试

### 5.1 后端测试

文件: `apps/api/tests/test_fault_report_conversion.py`
结果: **21 / 21 passed** (4.74s)

```
test_convert_success                                    PASSED
test_convert_copies_fields                              PASSED
test_convert_maps_priority                              PASSED
test_user_can_override_priority                         PASSED
test_safety_risk_enforces_minimum_priority              PASSED
test_shutdown_and_production_impact_enforces_priority   PASSED
test_convert_updates_fault_report_status                PASSED
test_convert_creates_status_history                     PASSED
test_convert_creates_checklist                           PASSED
test_admin_can_convert                                   PASSED
test_convert_with_notes                                  PASSED
test_technician_cannot_convert                           PASSED
test_unauthenticated_cannot_convert                      PASSED
test_missing_fault_report                                PASSED
test_duplicate_conversion_returns_conflict               PASSED
test_closed_fault_report_cannot_convert                  PASSED
test_converted_report_cannot_convert_again               PASSED
test_convert_with_assignee                               PASSED
test_convert_with_planned_dates                          PASSED
test_safety_risk_flag_adds_safety_note                   PASSED
test_high_risk_keywords_add_safety_note                  PASSED
```

测试修复:
- `equipment` fixture 补充 `qr_token` 字段（NOT NULL 约束）
- 引擎改用 `StaticPool` 确保 SQLite `:memory:` 连接共享

### 5.2 前端验证

| 项目 | 结果 |
|---|---|
| TypeScript 类型检查 (`tsc --noEmit`) | 零错误通过 |
| Next.js 构建 (`next build`) | 编译成功，12 页面静态生成通过 |
| ESLint | 未安装（构建已 ignoreDuringBuilds） |

---

## 六、待完成项

| 项 | 优先级 | 说明 |
|---|---|---|
| 前端单元测试 | 中 | 需配置 Jest + React Testing Library |
| E2E 测试 | 中 | 需配置 Playwright |
| ESLint 配置 | 低 | 安装 eslint + eslint-config-next |
| Docker Compose 验证 | 低 | `infrastructure/docker/` 目录为空 |
| Git 提交 | 中 | 按 Conventional Commits 格式 |

---

## 七、文件变更清单

### 后端

| 文件 | 变更 |
|---|---|
| `apps/api/app/api/v1/endpoints/fault_reports.py` | 重写，新增 `convert_to_work_order` 端点 |
| `apps/api/app/schemas/fault.py` | 新增 `FaultReportDetail`、`ConvertToWorkOrderRequest/Response` |
| `apps/api/tests/conftest.py` | 新建，测试 fixtures |
| `apps/api/tests/test_fault_report_conversion.py` | 新建，21 个测试用例 |

### 前端

| 文件 | 变更 |
|---|---|
| `apps/web/src/app/fault-reports/page.tsx` | 重写列表页 |
| `apps/web/src/app/fault-reports/[id]/page.tsx` | 新建详情页 |
| `apps/web/src/app/fault-reports/new/page.tsx` | 更新提交流程 |
| `apps/web/src/app/app-layout.tsx` | 重写全局导航 |
| `apps/web/src/app/knowledge/page.tsx` | 新建占位页 |
| `apps/web/src/app/admin/page.tsx` | 新建占位页 |
| `apps/web/src/lib/api.ts` | 新增 `ApiError`、`convertFaultReportToWorkOrder` |
| `apps/web/src/lib/types.ts` | 新增类型和标签映射 |
| `apps/web/src/styles/globals.css` | 新增 `slide-in` 动画 |
| `apps/web/package.json` | 新增 `typecheck` 脚本 |
| `apps/web/next.config.js` | 新增 `eslint.ignoreDuringBuilds` |
