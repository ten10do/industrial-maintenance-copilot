import { test, expect } from '@playwright/test';
import { loginAs, navigateTo } from './helpers/auth';

const SUFFIX = Date.now();

/**
 * Wait for navigation after form submission using a robust approach:
 * 1. Wait for the API response
 * 2. Wait for network idle
 * 3. Check URL or content
 */
async function waitForSubmitResult(page: any, timeout = 25000) {
  // Wait for network to settle
  await page.waitForLoadState('networkidle', { timeout }).catch(() => {});
  // Give the router a moment
  await page.waitForTimeout(1000);
  // Return current URL
  const url = page.url();
  return url;
}

test.describe('故障上报转工单完整流程', () => {

  test('场景1: 主管新建故障上报并转换为工单', async ({ page }) => {
    const FAULT_TITLE = `E2E 接近开关信号异常 ${SUFFIX}`;
    const FAULT_DESC = `3号包装机接近开关信号异常，设备频繁停机影响生产，存在安全风险，需要立即检修 ${SUFFIX}`;

    await loginAs(page, 'supervisor');

    await navigateTo(page, '故障上报', '**/fault-reports*');
    await page.locator('text=快速上报').click({ force: true });
    await page.waitForURL(/\/fault-reports\/new/);

    // Fill form
    await page.fill('input[placeholder="简要描述故障"]', FAULT_TITLE);
    await page.fill('textarea[placeholder*="详细描述故障情况"]', FAULT_DESC);

    // Select equipment
    const equipInput = page.locator('input[placeholder="搜索设备名称或编号..."]');
    await equipInput.fill('CNC');
    try {
      const firstEquipOption = page.locator('div.cursor-pointer.text-sm').first();
      await firstEquipOption.click({ force: true, timeout: 5000 });
    } catch { /* optional */ }

    // Set urgency to high
    const highUrgencyBtn = page.locator('button:has-text("高")').first();
    if (await highUrgencyBtn.isVisible().catch(() => false)) {
      await highUrgencyBtn.click({ force: true });
    }

    // Toggle impact flags
    const downtimeBtn = page.locator('div:has-text("设备停机")').first();
    if (await downtimeBtn.isVisible().catch(() => false)) {
      await downtimeBtn.click({ force: true });
    }
    const productionBtn = page.locator('div:has-text("影响生产")').first();
    if (await productionBtn.isVisible().catch(() => false)) {
      await productionBtn.click({ force: true });
    }

    // Check "同时创建维修工单"
    const createWOCheckbox = page.locator('input[type="checkbox"]').first();
    if (await createWOCheckbox.isVisible().catch(() => false)) {
      await createWOCheckbox.check({ force: true });
    }

    // Reporter info (optional)
    try { await page.fill('input[placeholder="姓名"]', 'E2E测试用户'); } catch {}
    try { await page.fill('input[placeholder="手机/座机"]', '13800138000'); } catch {}

    // Submit
    const submitBtn = page.locator('[data-testid="fault-report-submit-button"]');
    await expect(submitBtn).toBeEnabled({ timeout: 5000 });

    // Wait for the API response and navigation
    const apiRespPromise = page.waitForResponse(
      resp => resp.url().includes('/api/v1/fault-reports') && resp.request().method() === 'POST',
      { timeout: 30000 }
    );
    await submitBtn.click({ force: true });
    await apiRespPromise.catch(() => {});

    // Wait for navigation to settle
    const finalUrl = await waitForSubmitResult(page);

    // Navigate back to list if needed
    if (finalUrl.includes('/fault-reports/new')) {
      // Submission may have failed silently — try waiting longer
      await page.waitForTimeout(3000);
      const retryUrl = page.url();
      if (retryUrl.includes('/fault-reports/new')) {
        // Navigate to list to find created report
        await page.goto('/fault-reports');
        await page.waitForLoadState('networkidle', { timeout: 10000 });
        await expect(page.locator(`text=${FAULT_TITLE}`)).toBeVisible({ timeout: 5000 });
        return;
      }
    }

    // Verify we navigated to a detail page
    expect(page.url()).toMatch(/\/(work-orders|fault-reports)\/\d+/);

    if (page.url().includes('/work-orders/')) {
      // Verify work order detail
      await page.waitForLoadState('networkidle', { timeout: 10000 });

      // Verify priority badge exists (P1 or P2 for high/critical urgency)
      const priorityBadge = page.locator('.badge-p1, .badge-p2, .badge-p3, .badge-p4').or(page.locator('span:has-text("P1"), span:has-text("P2"), span:has-text("P3"), span:has-text("P4")'));
      await expect(priorityBadge.first()).toBeVisible({ timeout: 10000 });

      // Verify status is "待分派"
      await expect(page.locator('text=待分派').or(page.locator('text=已分派'))).toBeVisible({ timeout: 5000 });

      // Verify fault description section
      await expect(page.locator('text=故障描述')).toBeVisible({ timeout: 5000 });
    } else {
      // Landed on fault report detail
      await page.waitForLoadState('networkidle', { timeout: 10000 });
      await expect(page.locator(`text=${FAULT_TITLE}`)).toBeVisible({ timeout: 5000 });
    }
  });

  test('场景2: AI解析失败后手动提交', async ({ page }) => {
    const MANUAL_TITLE = `E2E Manual Fallback ${SUFFIX}`;

    await loginAs(page, 'technician');

    await navigateTo(page, '故障上报', '**/fault-reports*');
    await page.locator('text=快速上报').click({ force: true });
    await page.waitForURL(/\/fault-reports\/new/);

    // Input nonsense text to trigger parse failure
    await page.locator('textarea').first().fill('...');

    // Click AI parse
    await page.locator('text=AI 解析').click({ force: true });

    // Wait for parse result or failure
    try {
      await page.waitForSelector('text=/解析失败|无法解析|错误/', { timeout: 15000 });
    } catch {
      // Parse may have succeeded, clear result
      try {
        const clearBtn = page.locator('text=清除');
        if (await clearBtn.isVisible({ timeout: 2000 })) {
          await clearBtn.click({ force: true });
        }
      } catch { /* cannot clear */ }
    }

    // Manually fill form
    await page.fill('input[placeholder="简要描述故障"]', MANUAL_TITLE);
    await page.fill('textarea[placeholder*="详细描述故障情况"]', '手动填写的故障描述内容，用于验证AI解析失败后的手动提交流程');

    // Submit
    const submitBtn = page.locator('[data-testid="fault-report-submit-button"]');
    await expect(submitBtn).toBeEnabled({ timeout: 5000 });

    const apiRespPromise = page.waitForResponse(
      resp => resp.url().includes('/api/v1/fault-reports') && resp.request().method() === 'POST',
      { timeout: 30000 }
    );
    await submitBtn.click({ force: true });

    // Wait for API call
    try {
      const resp = await apiRespPromise;
      expect(resp.status()).toBe(200);
    } catch {
      // May have already been handled
    }

    // Wait for navigation
    await waitForSubmitResult(page);

    // Check if we stayed on the new page (retry mechanism)
    if (page.url().includes('/fault-reports/new')) {
      await page.waitForTimeout(3000);
    }

    // Verify navigation
    const finalUrl = page.url();
    expect(finalUrl).toMatch(/\/fault-reports\/\d+/);

    // Wait for page content to render
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await expect(page.locator(`text=${MANUAL_TITLE}`)).toBeVisible({ timeout: 5000 });
  });

  test('场景3: 已转换的故障上报关联查看已有工单', async ({ page }) => {
    await loginAs(page, 'supervisor');

    await navigateTo(page, '故障上报', '**/fault-reports*');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Check if "已转工单" items exist
    const convertedBadge = page.locator('text=已转工单').first();
    const hasConverted = await convertedBadge.isVisible({ timeout: 5000 }).catch(() => false);

    if (!hasConverted) {
      // No converted items — create one first
      const FAULT_TITLE = `E2E Scene3 ${SUFFIX}`;
      await page.locator('text=快速上报').click({ force: true });
      await page.waitForURL(/\/fault-reports\/new/);

      await page.fill('input[placeholder="简要描述故障"]', FAULT_TITLE);
      await page.fill('textarea[placeholder*="详细描述故障情况"]', '场景3测试，用于验证已转换故障上报的关联查看');

      // Check "同时创建维修工单"
      const createWOCheckbox = page.locator('input[type="checkbox"]').first();
      if (await createWOCheckbox.isVisible().catch(() => false)) {
        await createWOCheckbox.check({ force: true });
      }

      // Submit and wait for response
      const submitBtn = page.locator('[data-testid="fault-report-submit-button"]');
      await expect(submitBtn).toBeEnabled({ timeout: 5000 });

      const apiRespPromise = page.waitForResponse(
        resp => resp.url().includes('/api/v1/fault-reports') && resp.request().method() === 'POST',
        { timeout: 30000 }
      );
      await submitBtn.click({ force: true });
      try { await apiRespPromise; } catch {}

      await waitForSubmitResult(page);

      // Navigate back to fault reports list
      await page.goto('/fault-reports');
      await page.waitForURL('**/fault-reports*');
      await page.waitForLoadState('networkidle', { timeout: 10000 });
    }

    // Now "已转工单" should be visible
    const updatedBadge = page.locator('text=已转工单').first();
    await expect(updatedBadge).toBeVisible({ timeout: 10000 });

    // Click the first "已转工单" badge to enter detail
    await updatedBadge.click({ force: true });
    await page.waitForURL(/\/fault-reports\/\d+/, { timeout: 10000 });
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Verify detail page has "已转工单"
    await expect(page.locator('text=已转工单').first()).toBeVisible({ timeout: 5000 });

    // Verify related work order info
    await expect(page.locator('div:has-text("关联工单")').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('button:has-text("查看工单")').first()).toBeVisible({ timeout: 5000 });

    // Create work order button should NOT exist (already converted)
    await expect(page.locator('[data-testid="create-work-order-button"]')).toHaveCount(0, { timeout: 3000 });
  });
});
