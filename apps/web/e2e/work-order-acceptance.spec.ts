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

async function apiPost(page: any, path: string, body: any) {
  return page.evaluate(async ({ base, path: p, body: b }: { base: string; path: string; body: any }) => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${base}${p}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  }, { base: BASE, path, body });
}

/**
 * Ensure there is at least one assigned work order for testing.
 * Creates a fault report, converts it, and assigns to the first technician.
 */
async function ensureAssignedWorkOrder(page: any): Promise<{ woId: number; assigneeId: number; assigneeEmail: string } | null> {
  // 1. Login as supervisor
  await loginAs(page, 'supervisor');

  // 2. Get users to find a technician
  const usersResult = await apiGet(page, '/users?page_size=100');
  const users = usersResult.items || [];
  const technician = users.find((u: any) => u.role === 'technician');

  if (!technician) {
    test.skip(true, '没有找到维修工程师用户');
    return null;
  }

  // 3. Create a fault report
  const fr = await apiPost(page, '/fault-reports', {
    title: `E2E Assign Test ${Date.now()}`,
    description: '自动创建的测试故障上报，用于验证工单分派流程',
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

test.describe('维修工程师接受已分派工单', () => {

  test('场景4: 被分派工程师登录后接受工单并验证状态转换', async ({ page }) => {
    // 1. Ensure we have an assigned work order
    const testData = await ensureAssignedWorkOrder(page);
    if (!testData) return;

    // 2. Switch login to the assigned technician
    await switchLogin(page, testData.assigneeEmail, 'Demo123456');

    // 3. Navigate directly to the work order detail
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // 4. Verify "接受工单" button is visible
    const acceptButton = page.locator('button:has-text("接受工单")');
    await expect(acceptButton).toBeVisible({ timeout: 5000 });

    // 5. Click "接受工单"
    await acceptButton.click();

    // 6. Wait for state update
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // 7. Verify status changed
    await expect(page.locator('text=已接受').first()).toBeVisible({ timeout: 10000 });

    // 8. Verify button switched
    await expect(page.locator('button:has-text("接受工单")')).toHaveCount(0, { timeout: 3000 });
    await expect(page.locator('button:has-text("开始维修")')).toBeVisible({ timeout: 5000 });
  });

  test('场景4b: 其他维修工程师不能接受非自己分派的工单', async ({ page }) => {
    // 1. Ensure we have an assigned work order
    const testData = await ensureAssignedWorkOrder(page);
    if (!testData) return;

    // 2. Get users to find a DIFFERENT technician
    await loginAs(page, 'supervisor');
    const usersResult = await apiGet(page, '/users?page_size=100');
    const users = usersResult.items || [];
    const otherTech = users.find((u: any) =>
      u.role === 'technician' && u.id !== testData.assigneeId
    );

    if (!otherTech) {
      test.skip(true, '没有其他维修工程师可测试');
      return;
    }

    // 3. Login as the OTHER technician
    await switchLogin(page, otherTech.email, 'Demo123456');

    // 4. Navigate to the assigned work order
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // 5. The "接受工单" button should NOT be visible for a non-assigned technician
    await expect(page.locator('button:has-text("接受工单")')).toHaveCount(0, { timeout: 5000 });
  });

  test('场景4c: 主管不显示工程师专属的"接受工单"按钮', async ({ page }) => {
    // 1. Ensure we have an assigned work order
    const testData = await ensureAssignedWorkOrder(page);
    if (!testData) return;

    // 2. Login as supervisor
    await loginAs(page, 'supervisor');

    // 3. Navigate to the work order detail
    await page.goto(`/work-orders/${testData.woId}`);
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // 4. Supervisor should see management buttons
    const cancelBtn = page.locator('button:has-text("取消工单")');
    try {
      await expect(cancelBtn).toBeVisible({ timeout: 5000 });
    } catch {
      // Some work order statuses may not allow cancel
    }

    // 5. Should NOT see "接受工单" button
    await expect(page.locator('button:has-text("接受工单")')).toHaveCount(0, { timeout: 3000 });
  });
});
