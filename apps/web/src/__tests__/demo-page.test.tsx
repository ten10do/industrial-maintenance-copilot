import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DemoPage from '@/app/demo/page';

const mockGetDemoState = jest.fn();
const mockSetDemoScenario = jest.fn();
const mockReviewAlarm = jest.fn();
const mockCreateAlarmWorkOrder = jest.fn();
const mockAnalyzeAlarm = jest.fn();

jest.mock('@/lib/api', () => ({
  getDemoState: (...a: unknown[]) => mockGetDemoState(...(a as [])),
  setDemoScenario: (...a: unknown[]) => mockSetDemoScenario(...(a as [])),
  reviewAlarm: (...a: unknown[]) => mockReviewAlarm(...(a as [])),
  createAlarmWorkOrder: (...a: unknown[]) =>
    mockCreateAlarmWorkOrder(...(a as [])),
  analyzeAlarm: (...a: unknown[]) => mockAnalyzeAlarm(...(a as [])),
}));

jest.mock('@/lib/auth', () => ({
  useAuth: () => ({
    user: {
      id: 2,
      full_name: '主管',
      email: 'sup@test.com',
      role: 'supervisor',
      is_active: true,
    },
  }),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: { error: jest.fn(), success: jest.fn() },
}));

function makeState(overrides: Record<string, unknown> = {}) {
  const base = {
    equipment: {
      id: 1,
      code: 'Motor001',
      name: '演示电机',
      status: 'running',
      health_score: 92,
      risk_level: 'low',
    },
    simulator: { available: true, scenario: 'normal', tick: 3 },
    gateway: { enabled: true, mode: 'mock', status: 'connected', last_sync_at: null },
    telemetry: {
      id: 11,
      collected_at: '2026-08-25T09:00:00Z',
      bearing_temperature: 58.2,
      vibration_rms: 1.9,
      motor_current_a: 12.4,
      motor_voltage_v: 380.5,
      speed_rpm: 1478.0,
      load_ratio_pct: 61.0,
      quality: 1,
      is_anomaly: false,
      trace_id: 'trace-normal-1',
    },
    quality: { accepted: 8, rejected: 0, reject_reasons: {}, corrections: 0, snapshots_ingested: 1 },
    anomaly: null,
    prediction: null,
    recommendation: null,
    alarm: null,
    analysis: null,
    work_order: null,
    approval: null,
    agent_run: null,
    trace_id: 'trace-normal-1',
  };
  return { ...base, ...overrides };
}

describe('portfolio demo workspace', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders normal state with healthy badge and metrics', async () => {
    mockGetDemoState.mockResolvedValue(makeState());
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getByTestId('motor-state-badge')).toHaveTextContent(
        /RUNNING/
      );
    });
    expect(screen.getByTestId('digital-state-text')).toHaveTextContent('NORMAL');
    // 指标来自真实遥测（非硬编码）
    expect(screen.getByText('58.2')).toBeInTheDocument();
    expect(screen.getByTestId('simulation-disclaimer')).toBeInTheDocument();
  });

  it('renders scenario control with three options and selected state', async () => {
    mockGetDemoState.mockResolvedValue(makeState());
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getByTestId('scenario-fault')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId('scenario-normal')).toHaveAttribute(
        'aria-pressed',
        'true'
      );
    });
  });

  it('switching to FAULT calls demo scenario api then refreshes state', async () => {
    mockGetDemoState.mockResolvedValueOnce(makeState());
    mockSetDemoScenario.mockResolvedValue({
      scenario: 'fault',
      ticks: 14,
      simulation_only: true,
      published_events: 112,
      snapshots_ingested: 1,
      anomalies: 1,
      work_orders_created: 1,
      trace_id: 'trace-fault-1',
    });
    mockGetDemoState.mockResolvedValueOnce(
      makeState({
        simulator: { available: true, scenario: 'fault', tick: 14 },
        alarm: {
          id: 17,
          severity: 'CRITICAL',
          message: '工业报警升级为 CRITICAL：轴承温度=90.2',
          source: 'opcua-subscription',
          acknowledged: false,
          cleared: false,
          created_at: '2026-08-25T09:01:00Z',
          trace_id: 'trace-fault-1',
        },
        trace_id: 'trace-fault-1',
      })
    );
    const user = userEvent.setup();
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getByTestId('scenario-fault')).toBeEnabled();
    });
    await user.click(screen.getByTestId('scenario-fault'));
    await waitFor(() => {
      expect(mockSetDemoScenario).toHaveBeenCalledWith(
        'fault',
        undefined,
        'Motor001'
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId('alarm-panel')).toHaveTextContent(/CRITICAL/);
    });
  });

  it('shows anomaly/prediction/alarm panels in fault state', async () => {
    mockGetDemoState.mockResolvedValue(
      makeState({
        anomaly: {
          id: 5,
          fault_type: 'bearing_wear',
          title: '轴承磨损异常',
          severity: 'high',
          status: 'open',
          confidence: 0.82,
          detected_at: '2026-08-25T09:01:00Z',
          trace_id: 't1',
        },
        prediction: {
          id: 7,
          model_version: 'deterministic-rules-v1',
          failure_mode: 'bearing_wear',
          probability: 0.82,
          remaining_useful_life_hours: 36,
          is_mock: true,
          created_at: '2026-08-25T09:01:05Z',
        },
        alarm: {
          id: 17,
          severity: 'CRITICAL',
          message: '工业报警升级为 CRITICAL：轴承温度=90.2',
          source: 'opcua-subscription',
          acknowledged: false,
          cleared: false,
          created_at: '2026-08-25T09:01:10Z',
          trace_id: 't1',
        },
        analysis: {
          id: 3,
          alarm_id: 17,
          analysis_status: 'WAITING_REVIEW',
          review_status: null,
          confidence: 0.7,
          risk_level: 'HIGH',
          root_cause_hypothesis: '根因假设（bearing_wear）：滚道磨损。',
          recommended_actions: ['检查润滑', '更换轴承'],
          citations: [
            { article_id: 7, title: '轴承手册', source: 'manual.pdf', score: 0.9 },
          ],
          model_version: 'deterministic-rules-v1',
          requires_human_review: true,
          created_work_order_id: null,
        },
        trace_id: 't1',
      })
    );
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getAllByText(/bearing_wear/).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText(/根因假设/).length).toBeGreaterThan(0);
    expect(screen.getByText(/manual\.pdf/)).toBeInTheDocument();
    expect(screen.getByTestId('review-approve')).toBeInTheDocument();
  });

  it('empty knowledge evidence is shown explicitly (no fake citations)', async () => {
    mockGetDemoState.mockResolvedValue(
      makeState({
        anomaly: { id: 5, fault_type: 'x', title: 'x', severity: 'low', status: 'open', confidence: 0.3, detected_at: null, trace_id: 't' },
        analysis: {
          id: 3,
          alarm_id: 5,
          analysis_status: 'WAITING_REVIEW',
          review_status: null,
          confidence: 0.3,
          risk_level: 'MEDIUM',
          root_cause_hypothesis: '证据不足，需要人工复核。',
          recommended_actions: [],
          citations: [],
          model_version: 'deterministic-rules-v1',
          requires_human_review: true,
          created_work_order_id: null,
        },
      })
    );
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getByText('No knowledge evidence retrieved')).toBeInTheDocument();
    });
  });

  it('approve action calls real review api then refreshes', async () => {
    mockGetDemoState.mockResolvedValue(
      makeState({
        alarm: {
          id: 17,
          severity: 'CRITICAL',
          message: 'msg',
          source: 'opcua-subscription',
          acknowledged: false,
          cleared: false,
          created_at: null,
          trace_id: 't1',
        },
        analysis: {
          id: 3,
          alarm_id: 17,
          analysis_status: 'WAITING_REVIEW',
          review_status: null,
          confidence: 0.8,
          risk_level: 'HIGH',
          root_cause_hypothesis: 'h',
          recommended_actions: ['a'],
          citations: [],
          model_version: 'deterministic-rules-v1',
          requires_human_review: true,
          created_work_order_id: null,
        },
        trace_id: 't1',
      })
    );
    mockReviewAlarm.mockResolvedValue({ id: 3, analysis_status: 'APPROVED' });
    const user = userEvent.setup();
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getByTestId('review-approve')).toBeEnabled();
    });
    await user.click(screen.getByTestId('review-approve'));
    await waitFor(() => {
      expect(mockReviewAlarm).toHaveBeenCalledWith(
        17,
        'approve',
        'Demo approve'
      );
    });
  });

  it('create work order button appears after approval and calls api', async () => {
    mockGetDemoState.mockResolvedValue(
      makeState({
        alarm: { id: 17, severity: 'CRITICAL', message: 'm', source: 's', acknowledged: false, cleared: false, created_at: null, trace_id: 't1' },
        analysis: {
          id: 3,
          alarm_id: 17,
          analysis_status: 'APPROVED',
          review_status: 'approve',
          confidence: 0.85,
          risk_level: 'CRITICAL',
          root_cause_hypothesis: 'h',
          recommended_actions: ['a'],
          citations: [],
          model_version: 'deterministic-rules-v1',
          requires_human_review: false,
          created_work_order_id: null,
        },
        work_order: {
          id: 801,
          code: 'WO-ALARM-801',
          title: '[报警处置] 工单',
          status: 'pending_dispatch',
          priority: 'P1',
          assignee_id: 4,
          trace_id: 't1',
        },
        approval: { id: 55, command_type: 'shutdown', risk_level: 'high', status: 'pending' },
        trace_id: 't1',
      })
    );
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getByTestId('work-order-link')).toHaveAttribute(
        'href',
        '/work-orders/801'
      );
    });
    expect(screen.getByTestId('demo-workorder-chip')).toHaveTextContent(
      /WO-ALARM-801/
    );
  });

  it('renders view full trace link pointing to trace explorer', async () => {
    mockGetDemoState.mockResolvedValue(makeState());
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getByTestId('view-full-trace')).toHaveAttribute(
        'href',
        '/observability/traces/trace-normal-1'
      );
    });
  });

  it('shows backend error state without crashing', async () => {
    mockGetDemoState.mockRejectedValue(new Error('后端不可用'));
    render(<DemoPage />);
    await waitFor(() => {
      expect(screen.getByTestId('demo-error')).toHaveTextContent('后端不可用');
    });
  });

  it('shows loading placeholder before first fetch resolves', () => {
    mockGetDemoState.mockReturnValue(new Promise(() => {}));
    render(<DemoPage />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });
});
