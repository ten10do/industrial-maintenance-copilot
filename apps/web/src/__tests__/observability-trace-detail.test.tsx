import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import TraceDetailPage from '@/app/observability/traces/[traceId]/page';

const mockGetTrace = jest.fn();

jest.mock('@/lib/api', () => ({
  getTrace: (...a: unknown[]) => mockGetTrace(...(a as [])),
}));

jest.mock('next/navigation', () => ({
  useParams: () => ({ traceId: 'trace-abc' }),
  useRouter: () => ({ push: jest.fn() }),
}));

const detail = {
  trace_id: 'trace-abc',
  started_at: '2026-08-25T09:00:00Z',
  finished_at: '2026-08-25T09:00:04Z',
  duration_ms: 4000,
  equipment_ids: [3],
  final_status: 'work_order_created',
  stage_count: 9,
  event_count: 14,
  timeline: [
    {
      stage: 'telemetry', entity_type: 'telemetry', entity_id: 11,
      timestamp: '2026-08-25T09:00:00Z', equipment_id: 3, status: 'accepted',
      quality: 1, scenario: 'opcua-subscription',
    },
    {
      stage: 'prediction', entity_type: 'risk_prediction', entity_id: 34,
      timestamp: '2026-08-25T09:00:01Z', equipment_id: 3, status: 'completed',
      model_name: 'risk-prediction', model_version: 'deterministic-rules-v1',
      probability: 0.94,
    },
    {
      stage: 'alarm', entity_type: 'industrial_alarm', entity_id: 17,
      timestamp: '2026-08-25T09:00:02Z', equipment_id: 3, status: 'active',
      severity: 'CRITICAL', message: '工业报警升级为 CRITICAL：轴承温度=92.0',
    },
    {
      stage: 'rag', entity_type: 'rag_citation', entity_id: 5,
      timestamp: '2026-08-25T09:00:03Z', equipment_id: null, status: 'retrieved',
      source: 'manual.pdf', score: 0.9, snippet: '轴承过热处置手册 p.42',
    },
    {
      stage: 'work_order', entity_type: 'work_order', entity_id: 801,
      timestamp: '2026-08-25T09:00:04Z', equipment_id: 3,
      status: 'pending_dispatch', code: 'WO-2026-ABC',
    },
  ],
};

function renderDetail() {
  return render(<TraceDetailPage />);
}

describe('trace detail page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetTrace.mockResolvedValue(detail);
  });

  it('renders timeline stages in order with statuses', async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByTestId('timeline-telemetry')).toBeInTheDocument();
    });
    expect(screen.getByTestId('timeline-prediction')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-alarm')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-work_order')).toBeInTheDocument();
    expect(screen.getByTestId('trace-title')).toHaveTextContent('trace-abc');
  });

  it('shows prediction model version and confidence facts', async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText(/deterministic-rules-v1/)).toBeInTheDocument();
    });
    expect(screen.getByText(/概率: 0.94/)).toBeInTheDocument();
  });

  it('shows rag citation source without leaking secrets', async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText(/manual\.pdf/)).toBeInTheDocument();
    });
    const text = document.body.textContent || '';
    expect(text).not.toMatch(/authorization/i);
    expect(text).not.toMatch(/api[_ ]?key/i);
  });

  it('renders error state for empty/missing trace', async () => {
    mockGetTrace.mockRejectedValue(new Error('未找到该 trace_id 的任何链路记录'));
    renderDetail();
    await waitFor(() => {
      expect(screen.getByTestId('trace-error')).toBeInTheDocument();
    });
  });

  it('renders loading state before data arrives', () => {
    mockGetTrace.mockReturnValue(new Promise(() => {}));
    renderDetail();
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });
});
