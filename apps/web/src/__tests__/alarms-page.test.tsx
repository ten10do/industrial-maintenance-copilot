import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AlarmsPage from '@/app/alarms/page';

const mockListAlarms = jest.fn();
const mockAcknowledgeAlarm = jest.fn();
const mockAnalyzeAlarm = jest.fn();
const mockCorrelateAlarms = jest.fn();
const mockReviewAlarm = jest.fn();
const mockCreateAlarmWorkOrder = jest.fn();

jest.mock('@/lib/api', () => ({
  listAlarms: (...args: unknown[]) => mockListAlarms(...args),
  acknowledgeAlarm: (...args: unknown[]) => mockAcknowledgeAlarm(...args),
  analyzeAlarm: (...args: unknown[]) => mockAnalyzeAlarm(...args),
  correlateAlarms: (...args: unknown[]) => mockCorrelateAlarms(...args),
  reviewAlarm: (...args: unknown[]) => mockReviewAlarm(...args),
  createAlarmWorkOrder: (...args: unknown[]) => mockCreateAlarmWorkOrder(...args),
}));

jest.mock('@/lib/auth', () => ({
  useAuth: () => ({
    user: { id: 1, full_name: '安全主管', email: 'sup@test.com', role: 'supervisor', is_active: true },
  }),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: { error: jest.fn(), success: jest.fn() },
}));

const alarmPayload = {
  items: [
    {
      id: 9,
      equipment_id: 3,
      severity: 'CRITICAL',
      message: '工业报警升级为 CRITICAL：设备报警位（Alarm）已置位',
      source: 'opcua-subscription',
      acknowledged: false,
      acknowledged_at: null,
      cleared_at: null,
      created_at: '2026-08-20T12:00:10Z',
    },
    {
      id: 8,
      equipment_id: 5,
      severity: 'WARNING',
      message: '工业报警升级为 WARNING：轴承温度=82.0',
      source: 'opcua-subscription',
      acknowledged: true,
      acknowledged_at: '2026-08-20T12:01:00Z',
      cleared_at: '2026-08-20T12:02:00Z',
      created_at: '2026-08-20T12:00:40Z',
    },
  ],
  total: 2,
  read_only_source: true,
};

describe('industrial alarm center page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockListAlarms.mockResolvedValue(alarmPayload);
    mockAcknowledgeAlarm.mockResolvedValue({ ok: true, id: 9, acknowledged: true });
    mockCreateAlarmWorkOrder.mockResolvedValue({
      alarm_id: 9, analysis_id: 1, work_order_id: 77,
      work_order_code: 'WO-ALARM-77', status: 'pending_dispatch', created: true,
    });
  });

  it('renders alarm severity, equipment, timestamp and status', async () => {
    render(<AlarmsPage />);

    expect(await screen.findByText('工业报警中心')).toBeInTheDocument();
    expect(await screen.findByText(/设备报警位（Alarm）已置位/)).toBeInTheDocument();
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    expect(screen.getByText('WARNING')).toBeInTheDocument();
    expect(screen.getByText('已解除')).toBeInTheDocument();
    expect(screen.getByText('2 条记录')).toBeInTheDocument();
  });

  it('acknowledges an active alarm via the supervisor action', async () => {
    const user = userEvent.setup();
    render(<AlarmsPage />);

    await screen.findByText('CRITICAL');
    await user.click(screen.getByRole('button', { name: '确认' }));

    await waitFor(() => expect(mockAcknowledgeAlarm).toHaveBeenCalledWith(9));
  });

  it('runs AI analysis and renders understanding, root cause and actions', async () => {
    mockAnalyzeAlarm.mockResolvedValue({
      id: 1,
      alarm_id: 9,
      correlation_group_id: 'abc123',
      summary: 'CRITICAL 级工业报警：轴承温度=92.0、振动 RMS=4.9。原始信息：Alarm 已置位',
      root_cause_hypothesis: '根因假设（bearing_overheat）：轴承温度超过运行阈值。',
      contributing_factors: ['轴承温度=92.0（阈值 75.0）'],
      evidence: {},
      citations: [{ article_id: 3, title: '轴承过热处置手册', score: 0.8 }],
      confidence: 0.8,
      recommended_actions: ['降低负载并安排维护窗口', '处理前确认现场安全条件（LOTO）'],
      suggested_priority: 'P1',
      related_work_order_id: null,
      created_work_order_id: null,
      risk_level: 'CRITICAL',
      analysis_status: 'WAITING_REVIEW',
      review_status: null,
      reviewed_by: null,
      reviewed_at: null,
      review_note: null,
      agent_run_id: 12,
      requires_human_review: true,
      model_version: 'deterministic-rules-v1',
      is_mock: true,
      created_at: '2026-08-20T12:00:20Z',
    });
    const user = userEvent.setup();
    render(<AlarmsPage />);

    await screen.findByText('CRITICAL');
    await user.click(screen.getByTestId('analyze-alarm-9'));

    await waitFor(() => expect(mockAnalyzeAlarm).toHaveBeenCalledWith(9));
    expect(await screen.findByTestId('analysis-panel')).toBeInTheDocument();
    expect(screen.getByText(/轴承温度=92\.0/)).toBeInTheDocument();
    expect(screen.getByText(/bearing_overheat/)).toBeInTheDocument();
    expect(screen.getByText(/轴承过热处置手册/)).toBeInTheDocument();
    expect(screen.getByText(/Human Approval/)).toBeInTheDocument();
    expect(screen.getByTestId('evidence-details')).toBeInTheDocument();
  });

  it('requires review before exposing the controlled work-order action', async () => {
    const waitingAnalysis = {
      id: 1, alarm_id: 9, correlation_group_id: 'abc123',
      summary: '报警理解', root_cause_hypothesis: '证据约束根因假设',
      contributing_factors: [], evidence: {}, citations: [], confidence: 0.6,
      recommended_actions: ['现场复核'], suggested_priority: 'P2',
      related_work_order_id: null, created_work_order_id: null,
      risk_level: 'CRITICAL', analysis_status: 'WAITING_REVIEW', review_status: null,
      reviewed_by: null, reviewed_at: null, review_note: null, agent_run_id: 12,
      requires_human_review: true, model_version: 'deterministic-rules-v1',
      is_mock: true, created_at: '2026-08-20T12:00:20Z',
    };
    mockAnalyzeAlarm.mockResolvedValue(waitingAnalysis);
    mockReviewAlarm.mockResolvedValue({
      ...waitingAnalysis, analysis_status: 'APPROVED', review_status: 'approve',
      reviewed_by: 1, requires_human_review: false,
    });
    const user = userEvent.setup();
    render(<AlarmsPage />);

    await user.click(await screen.findByTestId('analyze-alarm-9'));
    expect(screen.queryByTestId('create-alarm-work-order')).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: '批准分析' }));
    expect(mockReviewAlarm).toHaveBeenCalledWith(9, 'approve');
    await user.click(await screen.findByTestId('create-alarm-work-order'));
    expect(mockCreateAlarmWorkOrder).toHaveBeenCalledWith(9);
    expect(await screen.findByText('已创建工单 #77')).toBeInTheDocument();
  });

  it('runs correlation analysis across active alarms', async () => {
    mockCorrelateAlarms.mockResolvedValue({
      groups: [
        {
          group_id: 'g1',
          reason: 'same_equipment',
          alarm_ids: [9, 8],
          equipment_ids: [3],
          severity: 'CRITICAL',
          window_start: null,
          window_end: null,
          size: 2,
        },
      ],
      total_alarms: 2,
    });
    const user = userEvent.setup();
    render(<AlarmsPage />);

    await screen.findByText('CRITICAL');
    await user.click(screen.getByRole('button', { name: '关联分析' }));

    await waitFor(() => expect(mockCorrelateAlarms).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId('correlation-panel')).toBeInTheDocument();
    expect(screen.getByText(/关联事件组（1 组/)).toBeInTheDocument();
  });

  it('refetches alarms when the status filter changes', async () => {
    const user = userEvent.setup();
    render(<AlarmsPage />);

    await screen.findByText('工业报警中心');
    await user.selectOptions(screen.getByLabelText('报警筛选'), 'cleared');

    await waitFor(() =>
      expect(mockListAlarms).toHaveBeenLastCalledWith({ status: 'cleared' }),
    );
  });
});
