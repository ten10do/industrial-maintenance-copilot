import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ApprovalsPage from '@/app/approvals/page';

const mockListOperationApprovals = jest.fn();
const mockApproveOperation = jest.fn();
const mockRejectOperation = jest.fn();
const mockReconcileOperation = jest.fn();

jest.mock('@/lib/api', () => ({
  listOperationApprovals: (...args: unknown[]) => mockListOperationApprovals(...args),
  approveOperation: (...args: unknown[]) => mockApproveOperation(...args),
  rejectOperation: (...args: unknown[]) => mockRejectOperation(...args),
  reconcileOperation: (...args: unknown[]) => mockReconcileOperation(...args),
}));

jest.mock('@/lib/auth', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      full_name: '安全主管',
      email: 'supervisor@test.com',
      role: 'supervisor',
      is_active: true,
    },
  }),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: { error: jest.fn(), success: jest.fn() },
}));

describe('high-risk operation reconciliation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockListOperationApprovals.mockResolvedValue([
      {
        id: 7,
        equipment_name: '压缩机 A',
        equipment_code: 'EQ-007',
        command_type: 'shutdown',
        command_payload: { reason: 'temperature' },
        risk_level: 'critical',
        risk_reason: '命令超时，现场状态未知',
        status: 'execution_unknown',
        requested_by_name: 'Maintenance Agent',
        reviewed_by_name: '安全主管',
        review_note: '批准停机',
        command_executed: false,
        execution_attempt: 1,
      },
    ]);
    mockReconcileOperation.mockResolvedValue({ status: 'pending' });
  });

  it('submits the observed device state and explicit reconciliation outcome', async () => {
    const user = userEvent.setup();
    render(<ApprovalsPage />);

    expect(
      await screen.findByRole('heading', { name: /压缩机 A/ }),
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('核验结论'), 'confirmed_not_executed');
    await user.type(screen.getByLabelText('现场设备状态'), '设备仍在运行，PLC 运行位为 1');
    await user.type(screen.getByLabelText('核验说明'), '已与现场负责人核对历史记录');
    await user.click(screen.getByRole('button', { name: '提交人工核验' }));

    await waitFor(() =>
      expect(mockReconcileOperation).toHaveBeenCalledWith(7, {
        outcome: 'confirmed_not_executed',
        note: '已与现场负责人核对历史记录',
        observed_device_state: '设备仍在运行，PLC 运行位为 1',
      }),
    );
  });
});
