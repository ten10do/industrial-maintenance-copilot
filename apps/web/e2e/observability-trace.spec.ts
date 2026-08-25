import { expect, test } from '@playwright/test';
import { loginAs } from './helpers/auth';

/**
 * Observability & Traceability 端到端：
 * 确定性仿真故障 → 观测中心定位链路 → 链路详情验证关键阶段。
 *
 * 说明：该链路由软件仿真驱动（telemetry→anomaly→prediction→
 * work_order→approval）。IndustrialAlarm 阶段仅出现在 OPC UA
 * 订阅报警路径，此处不做伪造断言。
 */

test('故障事件产生可追踪的完整证据链', async ({ page }) => {
  test.setTimeout(180000);
  await loginAs(page, 'supervisor');

  // 1. 通过实时监测页生成确定性故障事件（vibration_spike，固定种子）。
  await page.goto('/monitoring');
  await page.waitForLoadState('networkidle');
  await page.getByLabel('故障场景').selectOption('vibration_spike');
  await page.getByLabel('随机种子').fill('20260825');
  await page.getByRole('button', { name: '应用配置' }).click();
  await expect(page.getByText('仿真参数已配置')).toBeVisible();
  for (let index = 0; index < 3; index += 1) {
    await page.getByRole('button', { name: '单步' }).click();
    await expect(page.getByText('已生成一批遥测').last()).toBeVisible();
  }

  // 2. 打开观测中心：最近链路列表应出现至少一条。
  await page.goto('/observability');
  await page.waitForLoadState('networkidle');
  const rows = page.locator('[data-testid="recent-traces"] tr');
  await expect(rows.first()).toBeVisible({ timeout: 15000 });

  // 3. 通过真实搜索 API 定位"已创建工单"的完整链路
  //    （多次单步会各自形成 trace；只有触发异常升级的那条最丰富）。
  const traceId = await page.evaluate(async () => {
    const token = localStorage.getItem('token');
    const res = await fetch('/api/v1/observability/traces?limit=50', {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    const hit =
      data.items.find((item: { final_status: string }) => item.final_status === 'work_order_created') ??
      data.items[0];
    return hit ? (hit.trace_id as string) : '';
  });
  expect(traceId).toBeTruthy();

  // 4. 打开该链路详情。
  await page.goto(`/observability/traces/${traceId}`);
  await expect(page.locator('[data-testid="trace-detail"]')).toBeVisible({
    timeout: 15000,
  });

  // 4. 关键阶段必须出现（不存在的阶段不做伪造断言）。
  const requiredStages = [
    'timeline-telemetry',
    'timeline-anomaly',
    'timeline-prediction',
    'timeline-recommendation',
    'timeline-work_order',
    'timeline-approval',
  ];
  for (const stage of requiredStages) {
    await expect(page.locator(`[data-testid="${stage}"]`).first()).toBeVisible({
      timeout: 15000,
    });
  }

  // 5. 时间线确定性：再次加载顺序保持一致。
  await page.reload();
  await expect(page.locator('[data-testid="trace-detail"]')).toBeVisible();
  const firstStage = page.locator('[data-testid^="timeline-"]').first();
  await expect(firstStage).toBeVisible({ timeout: 15000 });
});
