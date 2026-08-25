import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import ObservabilityPage from '@/app/observability/page';

const mockGetObservabilityHealth = jest.fn();
const mockGetMetricsSummary = jest.fn();
const mockSearchTraces = jest.fn();

jest.mock('@/lib/api', () => ({
  getObservabilityHealth: (...a: unknown[]) => mockGetObservabilityHealth(...(a as [])),
  getMetricsSummary: (...a: unknown[]) => mockGetMetricsSummary(...(a as [])),
  searchTraces: (...a: unknown[]) => mockSearchTraces(...(a as [])),
}));

const healthPayload = {
  status: 'healthy',
  checked_at: '2026-08-25T10:00:00+08:00',
  components: {
    database: { status: 'healthy' },
    gateway: { status: 'unknown', detail: 'disabled' },
    redis: { status: 'unknown', detail: 'not_configured' },
    worker: { status: 'unknown', detail: 'not_configured' },
    scheduler: { status: 'unknown', detail: 'not_configured' },
    ml_inference: { status: 'unknown', detail: 'ai_provider_mock' },
    rag: { status: 'healthy', detail: 'keyword_baseline_over_knowledge_base' },
    opentelemetry: { status: 'unknown', detail: 'exporter_disabled' },
  },
};

const summaryPayload = {
  telemetry_events: 42,
  alarms_total: 7,
  alarms_active: 2,
  work_orders_total: 5,
  work_orders_open: 1,
  analyses_waiting_review: 1,
  agent_runs_total: 9,
  agent_avg_latency_ms: 12.3,
  traces_tracked: 6,
};

const tracesPayload = {
  total: 1,
  limit: 10,
  offset: 0,
  items: [
    {
      trace_id: '09ab1234-5678-90ab-cdef-1234567890ab',
      started_at: '2026-08-25T09:00:00Z',
      last_activity_at: '2026-08-25T09:00:05Z',
      equipment_ids: [3],
      final_status: 'work_order_created',
      stage_count: 8,
      event_count: 15,
    },
  ],
};

describe('observability overview page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetObservabilityHealth.mockResolvedValue(healthPayload);
    mockGetMetricsSummary.mockResolvedValue(summaryPayload);
    mockSearchTraces.mockResolvedValue(tracesPayload);
  });

  it('renders health component statuses including unknown providers honestly', async () => {
    render(<ObservabilityPage />);
    await waitFor(() => {
      expect(screen.getByTestId('health-database')).toHaveTextContent('healthy');
    });
    expect(screen.getByTestId('health-gateway')).toHaveTextContent('unknown');
    expect(screen.getByTestId('health-opentelemetry')).toHaveTextContent('unknown');
  });

  it('renders core metric summary values', async () => {
    render(<ObservabilityPage />);
    await waitFor(() => {
      expect(screen.getByTestId('metric-telemetry')).toHaveTextContent('42');
    });
    expect(screen.getByTestId('metric-traces')).toHaveTextContent('6');
  });

  it('lists recent traces with view links', async () => {
    render(<ObservabilityPage />);
    await waitFor(() => {
      expect(screen.getByTestId('recent-traces')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('open-trace-09ab1234-5678-90ab-cdef-1234567890ab')
    ).toBeInTheDocument();
  });

  it('shows empty hint when no traces exist', async () => {
    mockSearchTraces.mockResolvedValue({ total: 0, limit: 10, offset: 0, items: [] });
    render(<ObservabilityPage />);
    await waitFor(() => {
      expect(screen.getByTestId('traces-empty')).toBeInTheDocument();
    });
  });

  it('shows error state when all observability APIs fail', async () => {
    mockGetObservabilityHealth.mockRejectedValue(new Error('boom'));
    mockGetMetricsSummary.mockRejectedValue(new Error('boom'));
    mockSearchTraces.mockRejectedValue(new Error('boom'));
    render(<ObservabilityPage />);
    await waitFor(() => {
      expect(screen.getByTestId('observability-error')).toBeInTheDocument();
    });
  });

  it('never renders secret-like values from payloads', async () => {
    render(<ObservabilityPage />);
    await waitFor(() => {
      expect(screen.getByTestId('metric-telemetry')).toBeInTheDocument();
    });
    const text = document.body.textContent || '';
    expect(text).not.toMatch(/password/i);
    expect(text).not.toMatch(/authorization/i);
  });
});
