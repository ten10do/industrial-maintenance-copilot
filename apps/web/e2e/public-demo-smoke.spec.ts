import { test, expect } from '@playwright/test';
import { loginAs } from './helpers/auth';

test.describe('公开演示环境 Smoke Test', () => {
  test.skip(
    process.env.PUBLIC_DEMO_SMOKE !== 'true',
    'Set PUBLIC_DEMO_SMOKE=true and E2E_BASE_URL to run against the public demo.',
  );

  test('主管和维修工程师可完成只读关键路径', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/(login|dashboard)$/);

    await loginAs(page, 'supervisor');
    await expect(page.getByRole('heading', { name: '运维管理仪表盘' })).toBeVisible();

    await page.getByRole('link', { name: '故障上报' }).click();
    await expect(page.getByRole('heading', { name: '故障上报' })).toBeVisible();
    await expect(page.locator('.card')).not.toContainText('加载中...');

    await page.getByRole('link', { name: '维修工单' }).click();
    await expect(page.getByRole('heading', { name: '工单管理' })).toBeVisible();
    const firstWorkOrder = page.locator('tbody tr').first();
    await expect(firstWorkOrder).toBeVisible();

    await page.getByRole('link', { name: '知识库' }).click();
    await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible();
    const search = page.getByPlaceholder('搜索标题或内容...');
    await search.fill('E101');
    await search.press('Enter');
    await expect(page.locator('.card').filter({ hasText: 'E101' }).first()).toBeVisible();

    await page.getByRole('link', { name: 'AI 助手' }).click();
    await page.getByTestId('copilot-question-input').fill('E101 故障如何排查？');
    await page.getByTestId('copilot-submit-button').click();
    await expect(page.getByText('Mock AI 模式')).toBeVisible();
    await expect(page.getByText(/引用来源 \(\d+\)/)).toBeVisible();

    await loginAs(page, 'technician');
    await page.getByRole('link', { name: '维修工单' }).click();
    const technicianWorkOrder = page.locator('tbody tr').first();
    await expect(technicianWorkOrder).toBeVisible();
    await technicianWorkOrder.click();
    await expect(page).toHaveURL(/\/work-orders\/\d+$/);
    await expect(page.getByText('故障描述')).toBeVisible();
  });
});
