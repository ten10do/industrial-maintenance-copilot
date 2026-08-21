import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AlarmsPage from '@/app/alarms/page';

const mockListAlarms = jest.fn();
const mockAcknowledgeAlarm = jest.fn();

jest.mock('@/lib/api', () => ({
  listAlarms: (...args: unknown[]) => mockListAlarms(...args),
  acknowledgeAlarm: (...args: unknown[]) => mockAcknowledgeAlarm(...args),
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
