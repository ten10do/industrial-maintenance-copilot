import { expect, test } from '@playwright/test';
import { loginAs } from './helpers/auth';

const alarm = {
  id: 901,
  equipment_id: 3,
  severity: 'CRITICAL',
  message: '工业报警升级为 CRITICAL：轴承温度=92.0',
  source: 'opcua-subscription',
  acknowledged: false,
  acknowledged_at: null,
  cleared_at: null,
  created_at: '2026-08-24T08:00:00Z',
  risk_level: null,
  analysis_status: 'NEW',
  correlation_group_id: null,
  correlated_alarm_count: 0,
};

const waitingAnalysis = {
  id: 501,
  alarm_id: alarm.id,
  correlation_group_id: 'group-901',
  summary: 'CRITICAL 级工业报警：轴承温度=92.0',
  root_cause_hypothesis: '根因假设（bearing_overheat）：轴承温度越限。',
  contributing_factors: ['轴承温度=92.0（阈值 75.0）'],
  evidence: {
    telemetry_fields: { bearing_temperature: 92, vibration_rms: 4.9 },
    prediction_context: { failure_mode: 'bearing_overheat', probability: 0.82 },
    risk_assessment: { reasons: ['industrial_alarm=CRITICAL', 'fault_probability>=0.70'] },
  },
  citations: [{ article_id: 7, title: '轴承过热处置手册', source: 'manual', snippet: '检查润滑与轴承状态', score: 0.9 }],
  confidence: 0.8,
  recommended_actions: ['现场复核轴承与润滑状态'],
  suggested_priority: 'P1',
  related_work_order_id: null,
  created_work_order_id: null,
  risk_level: 'CRITICAL',
  analysis_status: 'WAITING_REVIEW',
  review_status: null,
  reviewed_by: null,
  reviewed_at: null,
  review_note: null,
  agent_run_id: 301,
  requires_human_review: true,
  model_version: 'deterministic-rules-v1',
  is_mock: true,
  created_at: '2026-08-24T08:00:01Z',
};

test('报警分析必须人工批准后才能创建受控工单', async ({ page }) => {
  await loginAs(page, 'supervisor');
  let approved = false;
  await page.route('**/api/v1/alarms**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/alarms') {
      await route.fulfill({ json: { items: [alarm], total: 1, read_only_source: true } });
    } else if (path.endsWith('/analyze')) {
      await route.fulfill({ json: waitingAnalysis });
    } else if (path.endsWith('/review')) {
      approved = true;
      await route.fulfill({
        json: { ...waitingAnalysis, analysis_status: 'APPROVED', review_status: 'approve' },
      });
    } else if (path.endsWith('/create-work-order') && approved) {
      await route.fulfill({
        json: {
          alarm_id: alarm.id,
          analysis_id: waitingAnalysis.id,
          work_order_id: 801,
          work_order_code: 'WO-ALARM-801',
          status: 'pending_dispatch',
          created: true,
        },
      });
    } else {
      await route.fallback();
    }
  });

  await page.goto('/alarms');
  await page.getByTestId(`analyze-alarm-${alarm.id}`).click();
  await expect(page.getByTestId('evidence-details')).toBeVisible();
  await expect(page.getByTestId('create-alarm-work-order')).not.toBeVisible();
  await page.getByRole('button', { name: '批准分析' }).click();
  await expect(page.getByTestId('create-alarm-work-order')).toBeVisible();
  await page.getByTestId('create-alarm-work-order').click();
  await expect(page.getByText('已创建工单 #801')).toBeVisible();
});
