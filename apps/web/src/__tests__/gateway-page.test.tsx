import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import GatewayPage from '@/app/gateway/page';

const mockGetGatewayStatus = jest.fn();
const mockGetGatewayNodes = jest.fn();
const mockTestGatewayConnection = jest.fn();
const mockSyncGateway = jest.fn();
const mockReloadGatewayMappings = jest.fn();

jest.mock('@/lib/api', () => ({
  getGatewayStatus: (...args: unknown[]) => mockGetGatewayStatus(...args),
  getGatewayNodes: (...args: unknown[]) => mockGetGatewayNodes(...args),
  testGatewayConnection: (...args: unknown[]) => mockTestGatewayConnection(...args),
  syncGateway: (...args: unknown[]) => mockSyncGateway(...args),
  reloadGatewayMappings: (...args: unknown[]) => mockReloadGatewayMappings(...args),
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

const statusPayload = {
  connection: {
    id: 1,
    name: 'primary-opcua',
    protocol: 'opcua',
    endpoint: 'mock://opcua-simulator',
    mode: 'mock',
    status: 'connected',
    enabled: true,
    poll_interval_seconds: 5,
    last_connected_at: '2026-08-20T12:00:00Z',
    last_sync_at: '2026-08-20T12:00:05Z',
    last_error: null,
  },
  runtime: {
    mode: 'mock',
    endpoint: 'mock://opcua-simulator',
    connected: true,
    connection_status: 'connected',
    running: true,
    poll_interval_seconds: 5,
    auto_ingest: true,
    read_only: true,
    last_connected_at: '2026-08-20T12:00:00Z',
    last_sync_at: '2026-08-20T12:00:05Z',
    last_error: null,
    consecutive_failures: 0,
    totals: {
      reads_total: 12, accepted: 12, rejected: 0,
      snapshots_ingested: 2, snapshots_skipped: 0,
      anomalies: 0, work_orders_created: 0,
    },
    last_sync: null,
  },
  enabled: true,
  read_only: true,
  seed_error: null,
};

const nodesPayload = {
  nodes: [
    {
      node_id: 'ns=2;s=Motor001.Temperature',
      equipment_code: 'EQ-MTR01',
      metric_name: 'temperature',
      unit: 'celsius',
      enabled: true,
      informational: false,
      last_value: 86.5,
      last_quality: 'good',
      last_timestamp: '2026-08-20T12:00:05Z',
      last_error: null,
    },
    {
      node_id: 'ns=2;s=Motor001.Vibration',
      equipment_code: 'EQ-MTR01',
      metric_name: 'vibration',
      unit: 'mm/s',
      enabled: true,
      informational: false,
      last_value: null,
      last_quality: null,
      last_timestamp: null,
      last_error: 'bad_quality: status_code=2158848000',
    },
  ],
  read_only: true,
};

describe('industrial gateway page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetGatewayStatus.mockResolvedValue(statusPayload);
    mockGetGatewayNodes.mockResolvedValue(nodesPayload);
    mockTestGatewayConnection.mockResolvedValue({
      ok: true,
      endpoint: 'mock://opcua-simulator',
      latency_ms: 3.2,
      probe_node: 'ns=2;s=Motor001.Current',
      sample_value: 12.1,
      error: null,
    });
    mockSyncGateway.mockResolvedValue({
      ok: true, error: null,
      reads_total: 8, accepted: 8, rejected: 0, corrections: 0,
      reject_reasons: {},
      snapshots_ingested: 1, snapshots_skipped: 0,
      anomalies: 0, work_orders_created: 0,
      telemetry_ids: [42], skipped_details: [], duration_ms: 9.1,
    });
  });

  it('renders connection status, device nodes and quality states', async () => {
    render(<GatewayPage />);

    expect(await screen.findByText('工业协议网关（OPC UA）')).toBeInTheDocument();
    expect(await screen.findByText('mock://opcua-simulator')).toBeInTheDocument();
    expect(await screen.findByText(/ns=2;s=Motor001.Temperature/)).toBeInTheDocument();
    expect(screen.getByText('86.5')).toBeInTheDocument();
    // 坏质量节点展示质量异常标记。
    expect(screen.getByTitle('bad_quality: status_code=2158848000')).toBeInTheDocument();
    // read-only 提示。
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
  });

  it('tests the connection via the read-only probe', async () => {
    const user = userEvent.setup();
    render(<GatewayPage />);

    await screen.findByText('工业协议网关（OPC UA）');
    await user.click(screen.getByRole('button', { name: /测试连接/ }));

    await waitFor(() => expect(mockTestGatewayConnection).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('连接测试结果')).toBeInTheDocument();
    expect(screen.getByText('ns=2;s=Motor001.Current')).toBeInTheDocument();
  });

  it('triggers a manual sync that ingests telemetry', async () => {
    const user = userEvent.setup();
    render(<GatewayPage />);

    await screen.findByText('工业协议网关（OPC UA）');
    await user.click(screen.getByRole('button', { name: /立即同步/ }));

    await waitFor(() => expect(mockSyncGateway).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('最近一次同步（读取 → 质量校验 → 遥测入库）')).toBeInTheDocument();
    expect(screen.getByText('入库快照')).toBeInTheDocument();
  });
});
