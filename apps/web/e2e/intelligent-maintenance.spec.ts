import { expect, test } from '@playwright/test';
import { loginAs, navigateTo, switchLogin } from './helpers/auth';

const BASE = '/api/v1';

async function api(page: any, method: string, path: string, body?: any) {
  return page.evaluate(async ({ base, method: requestMethod, path: requestPath, body: requestBody }) => {
    const token = localStorage.getItem('token');
    const response = await fetch(`${base}${requestPath}`, {
      method: requestMethod,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: requestBody === undefined ? undefined : JSON.stringify(requestBody),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`API ${response.status}: ${JSON.stringify(payload)}`);
    return payload;
  }, { base: BASE, method, path, body });
}

test.describe('智能运维与预测性维护闭环', () => {
  test('主管通过软件仿真生成异常、预测、智能工单与待审批操作', async ({ page }) => {
    await loginAs(page, 'supervisor');
    await navigateTo(page, '实时状态监测', '**/monitoring');
    await expect(page.getByRole('heading', { name: '实时状态监测与设备仿真' })).toBeVisible();

    await page.getByLabel('故障场景').selectOption('vibration_spike');
    await page.getByLabel('随机种子').fill('20260731');
    await page.getByRole('button', { name: '应用配置' }).click();
    await expect(page.getByText('仿真参数已配置')).toBeVisible();

    for (let index = 0; index < 3; index += 1) {
      await page.getByRole('button', { name: '单步' }).click();
      await expect(page.getByText('已生成一批遥测').last()).toBeVisible();
    }
    await expect(page.getByText('振动 RMS', { exact: true }).first()).toBeVisible();

    await navigateTo(page, '预测性维护', '**/predictive-maintenance');
    await expect(page.getByRole('heading', { name: '预测性维护中心' })).toBeVisible();
    await expect(page.getByText('转子不平衡').first()).toBeVisible();
    await expect(page.getByRole('button', { name: /查看智能工单/ }).first()).toBeVisible();

    await navigateTo(page, '操作审批中心', '**/approvals');
    await expect(page.getByRole('heading', { name: '高风险操作审批中心' })).toBeVisible();
    await expect(page.getByText('受控停机').first()).toBeVisible();
    await page.getByRole('button', { name: '批准并执行' }).first().click();
    await expect(page.getByText('请先填写审批意见和现场安全确认')).toBeVisible();
  });

  test('轴承磨损从遥测到审批、维修验证和知识草稿形成完整闭环', async ({ page }) => {
    test.setTimeout(180000);
    await loginAs(page, 'supervisor');

    const equipmentPage = await api(page, 'GET', '/equipment?page_size=100');
    const motor = equipmentPage.items.find((item: any) => item.code.includes('MTR'))
      ?? equipmentPage.items[0];
    expect(motor).toBeTruthy();

    await api(page, 'POST', '/intelligence/simulator/configure', {
      equipment_ids: [motor.id],
      interval_seconds: 1,
      scenario: 'bearing_wear',
      seed: 20260731,
      auto_create_work_orders: true,
    });
    for (let index = 0; index < 14; index += 1) {
      await api(page, 'POST', '/intelligence/simulator/tick', {});
    }

    const equipmentIntelligence = await api(page, 'GET', `/intelligence/equipment/${motor.id}`);
    expect(equipmentIntelligence.health_score).toBeLessThan(90);
    const anomaly = equipmentIntelligence.anomalies.find(
      (item: any) => item.fault_type === 'bearing_wear',
    );
    expect(anomaly).toBeTruthy();
    expect(anomaly.diagnosis.rag_citations.length).toBeGreaterThan(0);

    const recommendations = await api(page, 'GET', '/intelligence/recommendations');
    const recommendation = recommendations.find(
      (item: any) => item.equipment_id === motor.id
        && item.auto_work_order_id
        && item.title.includes('轴承磨损'),
    );
    expect(recommendation).toBeTruthy();
    expect(recommendation.dispatch_suggestion.recommended_technician_id).toBeTruthy();
    expect(recommendation.part_reservations.length).toBeGreaterThan(0);

    await page.goto('/predictive-maintenance');
    await expect(page.getByText('结构化诊断与 RAG 证据').first()).toBeVisible();
    await expect(page.getByText(/来源：工业电机轴承/).first()).toBeVisible();

    const approvals = await api(page, 'GET', '/intelligence/approvals?status=pending');
    const shutdown = approvals.find(
      (item: any) => item.work_order_id === recommendation.auto_work_order_id
        && item.command_type === 'shutdown',
    );
    expect(shutdown.command_executed).toBe(false);

    const approvedShutdown = await api(
      page,
      'POST',
      `/intelligence/approvals/${shutdown.id}/approve`,
      { note: '已确认维护窗口、能源隔离和 LOTO 负责人' },
    );
    expect(approvedShutdown.command_executed).toBe(true);

    for (const commandType of ['reset_alarm', 'restart']) {
      const requested = await api(page, 'POST', '/intelligence/approvals', {
        equipment_id: motor.id,
        work_order_id: recommendation.auto_work_order_id,
        recommendation_id: recommendation.id,
        command_type: commandType,
        command_payload: { reason: '模拟维修完成' },
        risk_level: 'high',
        risk_reason: '维修后复位与启动仍属于高风险设备操作，必须人工确认',
      });
      const approved = await api(
        page,
        'POST',
        `/intelligence/approvals/${requested.id}/approve`,
        { note: '现场检查完成，批准模拟执行' },
      );
      expect(approved.command_executed).toBe(true);
    }
    const recoveredTick = await api(page, 'POST', '/intelligence/simulator/tick', {});
    expect(recoveredTick.generated).toBe(1);

    const workOrder = await api(
      page,
      'GET',
      `/work-orders/${recommendation.auto_work_order_id}`,
    );
    const users = await api(page, 'GET', '/users?page_size=100');
    const assignee = users.items.find((item: any) => item.id === workOrder.assignee_id);
    expect(assignee).toBeTruthy();
    await switchLogin(page, assignee.email, 'Demo123456');

    await api(page, 'POST', `/work-orders/${workOrder.id}/accept`, {});
    await api(page, 'POST', `/work-orders/${workOrder.id}/start`, {});
    const activeOrder = await api(page, 'GET', `/work-orders/${workOrder.id}`);
    for (const item of activeOrder.checklist_items) {
      await api(page, 'PUT', `/work-orders/${workOrder.id}/checklist/${item.id}`, {
        is_completed: true,
        remark: '模拟闭环已完成',
      });
    }
    await api(page, 'POST', `/work-orders/${workOrder.id}/logs`, {
      log_type: 'repair',
      content: '完成轴承检查、更换、润滑和对中。',
      photos: ['mock://maintenance-result.jpg'],
    });
    await api(page, 'POST', `/work-orders/${workOrder.id}/labor`, {
      hours: 2,
      is_downtime: true,
      remark: '软件仿真维修',
    });
    const submitted = await api(page, 'POST', `/work-orders/${workOrder.id}/submit`, {
      root_cause: '轴承滚道磨损并伴随润滑退化',
      action_taken: '更换轴承、补充润滑并完成轴系对中',
      replaced_parts: '轴承 1 个',
      test_result: '维修后遥测恢复正常，空载和负载测试通过',
      equipment_status_after: 'running',
      needs_observation: false,
      completion_photos: ['mock://maintenance-result.jpg'],
    });
    expect(submitted.status).toBe('pending_acceptance');

    await switchLogin(page, 'supervisor@example.com', 'Demo123456');
    const verification = await api(page, 'POST', '/intelligence/verifications', {
      work_order_id: workOrder.id,
      notes: '维修后健康分与关键遥测已恢复',
      create_knowledge_case: true,
    });
    expect(verification.result).toBe('passed');

    const closedOrder = await api(page, 'GET', `/work-orders/${workOrder.id}`);
    expect(closedOrder.status).toBe('completed');
    const caseDraft = await api(
      page,
      'GET',
      `/knowledge/${verification.knowledge_article_id}`,
    );
    expect(caseDraft.status).toBe('draft');
    expect(caseDraft.title).toContain('待审核');
  });
});
