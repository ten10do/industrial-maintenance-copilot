import { expect, test } from '@playwright/test';
import { loginAs } from './helpers/auth';

/**
 * Portfolio Demo 全流程（真实 API，无 route mock）：
 * Login → /demo → FAULT 场景 → 报警/分析 → Human Review → Work Order → Trace。
 */
test('portfolio demo：fault 场景到工单与完整链路追踪', async ({ page }) => {
  test.setTimeout(240000);
  await loginAs(page, 'supervisor');

  await page.goto('/demo');
  await expect(page.getByTestId('demo-page')).toBeVisible();
  await expect(page.getByTestId('simulation-disclaimer')).toBeVisible();

  // 1. 切换 FAULT 场景（确定性软件模拟器编排）。
  await page.getByTestId('scenario-fault').click();

  // 2. 等待工业报警产生（CRITICAL）。
  await expect(
    page.locator('[data-testid="alarm-panel"]').getByText(/CRITICAL/)
  ).toBeVisible({ timeout: 30000 });

  // 3. 生成报警分析并查看 RCA 与 RAG 证据。
  const generate = page.getByTestId('generate-analysis');
  if (await generate.isVisible().catch(() => false)) {
    await generate.click();
  }
  await expect(
    page.locator('[data-testid="diagnosis-panel"]').getByText(/根因假设/)
  ).toBeVisible({ timeout: 30000 });

  // 4. Human Review：批准建议。
  await page.getByTestId('review-approve').click();
  await expect(
    page.locator('[data-testid="review-panel"]').getByText(/APPROVED|批准/)
  ).toBeVisible({ timeout: 30000 });

  // 5. 创建工单并验证链接。
  await page.getByTestId('create-work-order').click();
  await expect(page.getByTestId('work-order-link')).toBeVisible({
    timeout: 30000,
  });

  // 6. 打开完整链路 Trace，验证关键阶段存在。
  await page.getByTestId('view-full-trace').click();
  await expect(page.locator('[data-testid="trace-detail"]')).toBeVisible();
  for (const stage of [
    'timeline-telemetry',
    'timeline-anomaly',
    'timeline-prediction',
    'timeline-analysis',
    'timeline-work_order',
    'timeline-approval',
  ]) {
    await expect(
      page.locator(`[data-testid="${stage}"]`).first()
    ).toBeVisible({ timeout: 15000 });
  }
});
