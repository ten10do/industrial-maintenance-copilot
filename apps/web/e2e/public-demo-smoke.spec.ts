import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect, type Page } from '@playwright/test';
import { loginAs } from './helpers/auth';

const captureScreenshots = process.env.PUBLIC_DEMO_SCREENSHOTS === 'true';
const screenshotDir = resolve(process.cwd(), '../../docs/images');

async function capture(page: Page, filename: string) {
  if (!captureScreenshots) return;
  mkdirSync(screenshotDir, { recursive: true });
  await page.screenshot({ path: resolve(screenshotDir, filename), fullPage: true });
}

test.describe('公开演示环境 Smoke Test', () => {
  test.setTimeout(120_000);
  test.use({ viewport: { width: 1440, height: 900 } });

  test.skip(
    process.env.PUBLIC_DEMO_SMOKE !== 'true',
    'Set PUBLIC_DEMO_SMOKE=true and E2E_BASE_URL to run against the public demo.',
  );

  test('主管和维修工程师可完成只读关键路径', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/(login|dashboard)$/);

    await loginAs(page, 'supervisor');
    await expect(page.getByRole('heading', { name: '智能运维驾驶舱' })).toBeVisible();
    await capture(page, 'dashboard.png');

    await page.getByRole('button', { name: '故障上报' }).click();
    await expect(page.getByRole('heading', { name: '故障上报' })).toBeVisible();
    await expect(page.locator('.card')).not.toContainText('加载中...');
    await capture(page, 'fault-report.png');

    await page.getByRole('button', { name: '智能工单中心' }).click();
    await expect(page.getByRole('heading', { name: '智能工单中心' })).toBeVisible();
    await expect(page.getByText('加载中...')).toBeHidden({ timeout: 30_000 });
    const firstWorkOrder = page.locator('tbody tr').first();
    await expect(firstWorkOrder).toBeVisible({ timeout: 30_000 });

    await page.getByRole('button', { name: '运维知识中心' }).click();
    await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible();
    const search = page.getByPlaceholder('搜索标题或内容...');
    await search.fill('E101');
    await search.press('Enter');
    await expect(page.locator('.card').filter({ hasText: 'E101' }).first()).toBeVisible();
    await capture(page, 'knowledge-base.png');

    await page.getByRole('button', { name: '运维 Agent' }).click();
    await page.getByTestId('copilot-question-input').fill('E101 故障如何排查？');
    await page.getByTestId('copilot-submit-button').click();
    await expect(page.getByText('Mock AI 模式')).toBeVisible();
    await expect(page.getByText(/引用来源 \(\d+\)/)).toBeVisible();
    await capture(page, 'copilot.png');

    await loginAs(page, 'technician');
    await page.getByRole('button', { name: '智能工单中心' }).click();
    await expect(page.getByText('加载中...')).toBeHidden({ timeout: 30_000 });
    const technicianWorkOrder = page.locator('tbody tr').first();
    await expect(technicianWorkOrder).toBeVisible({ timeout: 30_000 });
    await technicianWorkOrder.click();
    await expect(page).toHaveURL(/\/work-orders\/\d+$/);
    await expect(page.getByText('故障描述')).toBeVisible();
    await capture(page, 'work-order-detail.png');
  });
});
