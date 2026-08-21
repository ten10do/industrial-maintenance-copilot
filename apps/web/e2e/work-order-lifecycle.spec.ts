import { test, expect } from '@playwright/test';
import { loginAs, switchLogin } from './helpers/auth';

const BASE = '/api/v1';

/**
 * Use the page's existing auth token to make API calls.
 */
async function apiGet(page: any, path: string) {
  return page.evaluate(async ({ base, path: p }: { base: string; path: string }) => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${base}${p}`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  }, { base: BASE, path });
}

async function apiPost(page: any, path: string, body: any = {}) {
  return page.evaluate(async ({ base, path: p, body: b }: { base: string; path: string; body: any }) => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${base}${p}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(`API ${res.status}: ${JSON.stringify(errorData)}`);
    }
    return res.json();
  }, { base: BASE, path, body });
}

async function apiPut(page: any, path: string, body: any) {
  return page.evaluate(async ({ base, path: p, body: b }: { base: string; path: string; body: any }) => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${base}${p}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  }, { base: BASE, path, body });
}

/**
 * Create a work order that goes through full lifecycle:
 * fault-report → convert → assign → (ready for technician)
 */
async function createWorkOrderForLifecycle(page: any): Promise<{
  woId: number;
  assigneeId: number;
  assigneeEmail: string;
} | null> {
  // 1. Login as supervisor
  await loginAs(page, 'supervisor');

  // 2. Get users to find a technician
  const usersResult = await apiGet(page, '/users?page_size=100');
  const users = usersResult.items || [];
  const technician = users.find((u: any) => u.role === 'technician');

  if (!technician) {
    test.skip(true, 'No technician user found');
    return null;
  }

  // 3. Create a fault report
  const fr = await apiPost(page, '/fault-reports', {
    title: `E2E Lifecycle Test ${Date.now()}`,
    description: '自动创建的测试故障上报，用于验证工单完整生命周期。包含高温烫伤风险，需确认安全防护。',
    urgency: 'high',
  });

  // 4. Convert to work order
  const converted = await apiPost(page, `/fault-reports/${fr.id}/convert-to-work-order`, {});

  // 5. Assign to technician
  const assigned = await apiPost(page, `/work-orders/${converted.work_order_id}/assign`, {
    assignee_id: technician.id,
  });

  return {
    woId: assigned.id,
    assigneeId: technician.id,
    assigneeEmail: technician.email,
  };
}

/**
 * Helper: fill in the submission form
 */
async function fillSubmitForm(page: any) {
  await page.fill('[data-testid="root-cause-input"]', '电机轴承磨损严重，导致运转不平衡');
  await page.fill('[data-testid="action-taken-input"]', '更换电机轴承，重新校准传动系统');
  await page.fill('[data-testid="test-result-input"]', '更换后设备运行平稳，振动值恢复至正常范围(≤2.5mm/s)');
}

async function uploadCompletionPhoto(page: any) {
  const onePixelPng = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );
  await page.locator('[data-testid="completion-photo-input"]').setInputFiles({
    name: 'completion.png',
    mimeType: 'image/png',
    buffer: onePixelPng,
  });
  await expect(page.getByText('已上传 1 张')).toBeVisible({ timeout: 10000 });
}

/**
 * Helper: complete all required checklist items
 */
async function completeAllChecklistItems(page: any) {
  // Wait for checklist items to be visible
  await page.waitForSelector('[data-testid^="checklist-item-"]', { timeout: 10000 });

  // Capture stable test IDs because each successful update refreshes and may reorder the list.
  const items = page.locator('[data-testid^="checklist-item-"]');
  const itemTestIds = await items.evaluateAll((elements: Element[]) =>
    elements
      .map(element => element.getAttribute('data-testid'))
      .filter((testId): testId is string => testId !== null)
  );

  for (const testId of itemTestIds) {
    const checkbox = page.locator(
      `[data-testid="${testId}"] input[type="checkbox"]`
    );
    const isChecked = await checkbox.isChecked();

    if (!isChecked && !(await checkbox.isDisabled())) {
      const updateResponse = page.waitForResponse(
        (response: any) =>
          response.request().method() === 'PUT'
          && response.url().includes('/checklist/')
      );
      await checkbox.check({ force: true });
      expect((await updateResponse).ok()).toBeTruthy();
      await page.waitForLoadState('networkidle', { timeout: 10000 });
      await expect(checkbox).toBeChecked({ timeout: 5000 });
    }
  }
}

async function completeSafetyChecklistItems(page: any) {
  const group = page.locator('[data-testid="checklist-group-safety"]');
  await expect(group).toBeVisible({ timeout: 10000 });
  const checkboxes = group.locator('input[type="checkbox"]');
  const count = await checkboxes.count();

  for (let index = 0; index < count; index += 1) {
    const checkbox = checkboxes.nth(index);
    if (!(await checkbox.isChecked())) {
      const updateResponse = page.waitForResponse(
        (response: any) => response.request().method() === 'PUT' && response.url().includes('/checklist/'),
      );
      await checkbox.check({ force: true });
      expect((await updateResponse).ok()).toBeTruthy();
      await page.waitForLoadState('networkidle', { timeout: 10000 });
    }
  }
}

async function confirmHighRiskExecution(
  page: any,
  triggerText = '开始维修',
  confirmationText = '确认安全措施并开始维修',
) {
  await page.locator(`button:has-text("${triggerText}")`).click({ force: true });
  const panel = page.locator('[data-testid="high-risk-safety-confirmation"]');
  await expect(panel).toBeVisible({ timeout: 5000 });
  await panel.locator('input[type="checkbox"]').check();
  await panel.locator('textarea').fill('已现场核对停机、能源隔离、LOTO 和个人防护措施');
  await panel.getByRole('button', { name: confirmationText }).click();
  await page.waitForLoadState('networkidle', { timeout: 10000 });
}

/**
 * Helper: add a maintenance log, labor entry, and spare part through the UI
 */
async function addMaintenanceRecords(page: any) {
  // 1. Add maintenance log
  await page.waitForSelector('[data-testid="add-log-form"]', { timeout: 5000 });
  await page.fill('[data-testid="log-content-input"]', '排查发现电机轴承磨损，决定更换轴承并重新校准');
  await page.locator('[data-testid="add-log-button"]').click({ force: true });
  await page.waitForTimeout(500);

  // 2. Add labor record
  await page.waitForSelector('[data-testid="add-labor-form"]', { timeout: 5000 });
  await page.fill('[data-testid="labor-hours-input"]', '3.5');
  await page.locator('[data-testid="add-labor-button"]').click({ force: true });
  await page.waitForTimeout(500);

  // 3. Add spare part (optional, but good to have)
  await page.waitForSelector('[data-testid="add-spare-form"]', { timeout: 5000 });
  await page.fill('[data-testid="spare-name-input"]', 'SKF轴承6205');
  await page.locator('[data-testid="add-spare-button"]').click({ force: true });
  await page.waitForTimeout(500);
}


// ============================================================
// Scenario 1: Full repair & acceptance lifecycle
// ============================================================
test.describe('工单完整生命周期', () => {
  test.setTimeout(120000);

  test('场景1: 完整维修验收流程 (assigned → accepted → in_progress → pending_acceptance → completed)', async ({ page }) => {
    // Step 0: Create test work order (supervisor)
    const testData = await createWorkOrderForLifecycle(page);
    if (!testData) return;

    // --------------------------------------------------------
    // Phase 1: Technician accepts and starts work
    // --------------------------------------------------------
    // Login as assigned technician
    await switchLogin(page, testData.assigneeEmail, 'Demo123456');

    // Navigate to work order detail
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Verify status is "已分派"
    await expect(page.getByText('已分派', { exact: true })).toBeVisible({ timeout: 5000 });

    // Click "接受工单"
    const acceptBtn = page.locator('[data-testid="accept-work-order-button"]');
    await expect(acceptBtn).toBeVisible({ timeout: 5000 });
    await acceptBtn.click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Verify status changed to "已接受"
    await expect(page.getByText('已接受', { exact: true })).toBeVisible({ timeout: 10000 });

    // 完成安全检查，并将现场确认与“开始维修”原子提交
    await completeSafetyChecklistItems(page);
    await confirmHighRiskExecution(page);

    // Verify status changed to "处理中"
    await expect(page.getByText('处理中', { exact: true })).toBeVisible({ timeout: 10000 });

    // --------------------------------------------------------
    // Phase 2: Technician completes checklist, logs, labor
    // --------------------------------------------------------
    // Complete all checklist items
    await completeAllChecklistItems(page);

    // Add maintenance records
    await addMaintenanceRecords(page);

    // --------------------------------------------------------
    // Phase 3: Technician submits completion
    // --------------------------------------------------------
    // Fill submit form
    await fillSubmitForm(page);
    await uploadCompletionPhoto(page);

    // Click submit button in submit section
    const submitBtn = page.locator('[data-testid="submit-completion-button"]');
    await expect(submitBtn).toBeVisible({ timeout: 5000 });
    await submitBtn.click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Verify status changed to "待验收"
    await expect(page.getByText('待验收', { exact: true })).toBeVisible({ timeout: 10000 });

    // --------------------------------------------------------
    // Phase 4: Supervisor approves
    // --------------------------------------------------------
    // Switch to supervisor
    await switchLogin(page, 'supervisor@example.com', 'Demo123456');

    // Navigate to work order
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Verify approval section is visible
    await expect(page.locator('[data-testid="approval-section"]')).toBeVisible({ timeout: 5000 });

    // Verify completion summary is displayed
    await expect(page.locator('text=电机轴承磨损严重')).toBeVisible({ timeout: 5000 });

    // Click approve
    const approveBtn = page.locator('[data-testid="approve-button"]');
    await expect(approveBtn).toBeVisible({ timeout: 5000 });
    await approveBtn.click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Verify status changed to "已完成"
    await expect(page.getByText('已完成', { exact: true })).toBeVisible({ timeout: 10000 });

    // Verify MaintenanceReport is rendered (for completed status)
    await expect(page.locator('[data-testid="maintenance-report"]')).toBeVisible({ timeout: 10000 });
  });
});


// ============================================================
// Scenario 2: Completion conditions insufficient
// ============================================================
test.describe('完工条件不足验证', () => {
  test.setTimeout(120000);

  test('场景2a: 未填写必填字段提交时显示前端校验错误', async ({ page }) => {
    const testData = await createWorkOrderForLifecycle(page);
    if (!testData) return;

    // Login as technician, accept, start
    await switchLogin(page, testData.assigneeEmail, 'Demo123456');
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Accept
    await page.locator('[data-testid="accept-work-order-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Start
    await completeSafetyChecklistItems(page);
    await confirmHighRiskExecution(page);

    await expect(page.getByText('处理中', { exact: true })).toBeVisible({ timeout: 10000 });

    // Try to submit with empty form - should show toast error
    // Use the submit button in the submit section (which is the one with data-testid)
    await page.waitForSelector('[data-testid="submit-section"]', { timeout: 5000 });
    await page.locator('[data-testid="submit-completion-button"]').click({ force: true });

    // Frontend validation error toast
    await expect(page.locator('text=请填写根本原因、处理措施和测试结果')).toBeVisible({ timeout: 5000 });
  });

  test('场景2b: 未完成检查清单和维修记录时提交返回422后端校验', async ({ page }) => {
    const testData = await createWorkOrderForLifecycle(page);
    if (!testData) return;

    // Login as technician, accept, start
    await switchLogin(page, testData.assigneeEmail, 'Demo123456');
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    await page.locator('[data-testid="accept-work-order-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await completeSafetyChecklistItems(page);
    await confirmHighRiskExecution(page);

    // Fill submit form (to pass frontend validation)
    await fillSubmitForm(page);

    // But do NOT complete checklist items or add logs/labor
    // Click submit - should trigger backend 422
    const submitBtn = page.locator('[data-testid="submit-completion-button"]');
    await expect(submitBtn).toBeVisible({ timeout: 5000 });
    await submitBtn.click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Verify completion validation error is displayed
    await expect(page.locator('[data-testid="completion-validation"]')).toBeVisible({ timeout: 10000 });

    // Verify status is still "处理中" (not submitted)
    await expect(page.getByText('处理中', { exact: true })).toBeVisible({ timeout: 5000 });
  });
});


// ============================================================
// Scenario 3: Rejection flow
// ============================================================
test.describe('验收驳回到重新处理流程', () => {
  test.setTimeout(180000);

  test('场景3: 主管驳回后技术员重新处理并重新提交验收通过', async ({ page }) => {
    const testData = await createWorkOrderForLifecycle(page);
    if (!testData) return;

    // --------------------------------------------------------
    // Phase 1: Technician completes all work and submits
    // --------------------------------------------------------
    await switchLogin(page, testData.assigneeEmail, 'Demo123456');
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Accept → Start
    await page.locator('[data-testid="accept-work-order-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await completeSafetyChecklistItems(page);
    await confirmHighRiskExecution(page);

    // Complete checklist, add logs/labor
    await completeAllChecklistItems(page);
    await addMaintenanceRecords(page);

    // Fill and submit
    await fillSubmitForm(page);
    await uploadCompletionPhoto(page);
    await page.locator('[data-testid="submit-completion-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    await expect(page.getByText('待验收', { exact: true })).toBeVisible({ timeout: 10000 });

    // --------------------------------------------------------
    // Phase 2: Supervisor rejects with reason
    // --------------------------------------------------------
    await switchLogin(page, 'supervisor@example.com', 'Demo123456');
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Verify approval section
    await expect(page.locator('[data-testid="approval-section"]')).toBeVisible({ timeout: 5000 });

    // Fill rejection reason
    const rejectReason = '处理措施不够详细，请补充更换过程的具体步骤';
    await page.fill('[data-testid="reject-reason-input"]', rejectReason);

    // Verify reject button becomes enabled
    const rejectBtn = page.locator('[data-testid="reject-button"]');
    await expect(rejectBtn).toBeEnabled({ timeout: 3000 });

    // Click reject
    await rejectBtn.click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Verify status changed to "已退回"
    await expect(page.getByText('已退回', { exact: true })).toBeVisible({ timeout: 10000 });

    // Verify rejection reason is displayed
    await expect(page.locator('[data-testid="rejection-reason"]')).toBeVisible({ timeout: 5000 });
    await expect(page.locator(`text=${rejectReason}`)).toBeVisible({ timeout: 5000 });

    // --------------------------------------------------------
    // Phase 3: Technician re-starts and re-submits
    // --------------------------------------------------------
    await switchLogin(page, testData.assigneeEmail, 'Demo123456');
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Verify "重新处理" button is visible
    const redoBtn = page.locator('button:has-text("重新处理")');
    await expect(redoBtn).toBeVisible({ timeout: 5000 });
    await confirmHighRiskExecution(page, '重新处理');

    // Verify back to "处理中"
    await expect(page.getByText('处理中', { exact: true })).toBeVisible({ timeout: 10000 });

    // Wait for submit section to appear
    await page.waitForSelector('[data-testid="submit-section"]', { timeout: 10000 });

    // Update the submit form with improved content
    await page.fill('[data-testid="root-cause-input"]', '电机轴承磨损严重，经拆解发现内圈有剥落痕迹');
    await page.fill('[data-testid="action-taken-input"]', '1. 停机断电锁定 2. 拆卸旧轴承 3. 清洁轴承座 4. 安装新SKF轴承6205 5. 重新校准传动系统');
    await page.fill('[data-testid="test-result-input"]', '更换后设备运行平稳，振动值恢复至正常范围(≤2.5mm/s)，空载和负载测试均通过');

    // Re-submit
    await page.locator('[data-testid="submit-completion-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    await expect(page.getByText('待验收', { exact: true })).toBeVisible({ timeout: 10000 });

    // --------------------------------------------------------
    // Phase 4: Supervisor approves (final)
    // --------------------------------------------------------
    await switchLogin(page, 'supervisor@example.com', 'Demo123456');
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    await expect(page.locator('[data-testid="approval-section"]')).toBeVisible({ timeout: 5000 });
    await page.locator('[data-testid="approve-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Final: completed
    await expect(page.getByText('已完成', { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="maintenance-report"]')).toBeVisible({ timeout: 10000 });
  });
});


// ============================================================
// Scenario 4: Permission isolation
// ============================================================
test.describe('权限隔离验证', () => {
  test.setTimeout(120000);

  test('场景4a: 非分派技术员看不到接单按钮', async ({ page }) => {
    const testData = await createWorkOrderForLifecycle(page);
    if (!testData) return;

    // Login as supervisor to find another technician
    await loginAs(page, 'supervisor');
    const usersResult = await apiGet(page, '/users?page_size=100');
    const users = usersResult.items || [];
    const otherTech = users.find((u: any) =>
      u.role === 'technician' && u.id !== testData.assigneeId
    );

    if (!otherTech) {
      test.skip(true, 'No other technician available for permission test');
      return;
    }

    // Login as the OTHER technician
    await switchLogin(page, otherTech.email, 'Demo123456');

    // Navigate to the assigned work order
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Should NOT see "接受工单" button
    await expect(page.locator('[data-testid="accept-work-order-button"]')).toHaveCount(0, { timeout: 5000 });
  });

  test('场景4b: 主管不显示工程师专属操作按钮但显示管理按钮', async ({ page }) => {
    const testData = await createWorkOrderForLifecycle(page);
    if (!testData) return;

    // Login as supervisor
    await loginAs(page, 'supervisor');

    // Navigate to the assigned work order
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Should NOT see "接受工单" button (technician-only)
    await expect(page.locator('[data-testid="accept-work-order-button"]')).toHaveCount(0, { timeout: 5000 });

    // Should see "取消工单" button (supervisor management button)
    await expect(page.locator('button:has-text("取消工单")')).toBeVisible({ timeout: 5000 });
  });

  test('场景4c: 已完成工单不显示任何操作按钮', async ({ page }) => {
    const testData = await createWorkOrderForLifecycle(page);
    if (!testData) return;

    // Full lifecycle: accept → start → complete → submit → approve
    // Login as technician, do the work
    await switchLogin(page, testData.assigneeEmail, 'Demo123456');
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    await page.locator('[data-testid="accept-work-order-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await completeSafetyChecklistItems(page);
    await confirmHighRiskExecution(page);

    await completeAllChecklistItems(page);
    await addMaintenanceRecords(page);
    await fillSubmitForm(page);
    await uploadCompletionPhoto(page);
    await page.locator('[data-testid="submit-completion-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    await expect(page.getByText('待验收', { exact: true })).toBeVisible({ timeout: 10000 });

    // Supervisor approves
    await switchLogin(page, 'supervisor@example.com', 'Demo123456');
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    await expect(page.locator('[data-testid="approval-section"]')).toBeVisible({ timeout: 5000 });
    await page.locator('[data-testid="approve-button"]').click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Verify completed
    await expect(page.getByText('已完成', { exact: true })).toBeVisible({ timeout: 10000 });

    // Action buttons container should NOT exist
    await expect(page.locator('[data-testid="action-buttons"]')).toHaveCount(0, { timeout: 5000 });
  });
});
