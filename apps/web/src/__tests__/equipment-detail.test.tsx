import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import EquipmentDetail from '@/app/equipment/[id]/page';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
  useParams: jest.fn(() => ({ id: '1' })),
}));

const mockGetEquipment = jest.fn();
const mockGetEquipmentWorkOrders = jest.fn();
const mockCopilotEquipmentHistory = jest.fn();
jest.mock('@/lib/api', () => ({
  getEquipment: (...args: unknown[]) => mockGetEquipment(...args),
  getEquipmentWorkOrders: (...args: unknown[]) => mockGetEquipmentWorkOrders(...args),
  copilotEquipmentHistory: (...args: unknown[]) => mockCopilotEquipmentHistory(...args),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const eqData = {
  id: 1,
  name: '3号CNC',
  code: 'CNC-03',
  status: 'running',
  risk_level: 'low',
  plant: 'A车间',
  production_line: 'Line 1',
  location: 'A区-3号位',
  manufacturer: 'Fanuc',
  model: 'α-D14MiB5',
  serial_number: 'SN123456',
  commissioning_date: '2024-01-15',
  last_maintenance_at: '2026-06-15',
  responsible_person_name: '王工',
  equipment_type_name: 'CNC',
  remarks: '进口设备',
};

const mockWos = [
  { id: 1, code: 'WO-001', title: '主轴异响', status: 'completed', root_cause: '轴承磨损' },
  { id: 2, code: 'WO-002', title: '润滑不足', status: 'in_progress', root_cause: null },
];

const mockHistory = {
  total_work_orders: 12,
  avg_repair_hours: 3.5,
  frequent_faults: [{ fault: '主轴异响', count: 3 }],
  repeated_faults: [{ fault: '润滑不足', count: 2 }],
  common_parts: [{ part: '主轴轴承', count: 4 }],
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('EquipmentDetail', () => {
  it('加载中展示加载状态', () => {
    mockGetEquipment.mockReturnValue(new Promise(() => {}));
    mockGetEquipmentWorkOrders.mockReturnValue(new Promise(() => {}));
    mockCopilotEquipmentHistory.mockReturnValue(new Promise(() => {}));
    render(<EquipmentDetail />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('设备不存在展示提示', async () => {
    mockGetEquipment.mockResolvedValue(null);
    mockGetEquipmentWorkOrders.mockResolvedValue([]);
    mockCopilotEquipmentHistory.mockResolvedValue(null);
    render(<EquipmentDetail />);
    await waitFor(() => {
      expect(screen.getByText('设备不存在')).toBeInTheDocument();
    });
  });

  it('成功展示设备详情', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('3号CNC')).toBeInTheDocument();
      expect(screen.getByText('基本属性')).toBeInTheDocument();
    });
  });

  it('展示基本属性信息', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('CNC-03')).toBeInTheDocument();
      expect(screen.getByText('运行中')).toBeInTheDocument();
      expect(screen.getByText('A车间')).toBeInTheDocument();
      expect(screen.getByText('Fanuc')).toBeInTheDocument();
      expect(screen.getByText('α-D14MiB5')).toBeInTheDocument();
    });
  });

  it('展示设备历史摘要', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('设备历史摘要')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument(); // total_work_orders
      expect(screen.getByText('平均修复: 3.5h')).toBeInTheDocument();
    });
  });

  it('展示高频故障', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('高频故障')).toBeInTheDocument();
      expect(screen.getByText('3次')).toBeInTheDocument();
    });
  });

  it('展示重复故障', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('重复故障')).toBeInTheDocument();
      expect(screen.getByText('(2次)')).toBeInTheDocument();
    });
  });

  it('展示常见更换部件', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('常见更换部件')).toBeInTheDocument();
      expect(screen.getByText('主轴轴承')).toBeInTheDocument();
    });
  });

  it('无历史摘要时展示空状态', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(null);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('暂无历史摘要')).toBeInTheDocument();
    });
  });

  it('展示历史工单列表', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('历史工单 (2)')).toBeInTheDocument();
      // "主轴异响" appears both in work orders and frequent faults
      const matches = screen.getAllByText('主轴异响');
      expect(matches.length).toBeGreaterThanOrEqual(1);
      const lubeMatches = screen.getAllByText('润滑不足');
      expect(lubeMatches.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('历史工单为空时展示空状态', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue([]);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('暂无工单记录')).toBeInTheDocument();
    });
  });

  it('点击历史工单跳转工单详情', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    const user = userEvent.setup();
    render(<EquipmentDetail />);

    await waitFor(() => screen.getAllByText('主轴异响')[1]);
    // Click index 1: first "主轴异响" is in frequent faults card (non-clickable),
    // second is in work order history list (clickable row)
    await user.click(screen.getAllByText('主轴异响')[1]);
    expect(mockPush).toHaveBeenCalledWith('/work-orders/1');
  });

  it('展示备注信息', async () => {
    mockGetEquipment.mockResolvedValue(eqData);
    mockGetEquipmentWorkOrders.mockResolvedValue(mockWos);
    mockCopilotEquipmentHistory.mockResolvedValue(mockHistory);
    render(<EquipmentDetail />);

    await waitFor(() => {
      expect(screen.getByText('备注: 进口设备')).toBeInTheDocument();
    });
  });

  it('API 失败时展示错误 toast', async () => {
    mockGetEquipment.mockRejectedValue(new Error('网络错误'));
    mockGetEquipmentWorkOrders.mockRejectedValue(new Error('Failed'));
    mockCopilotEquipmentHistory.mockRejectedValue(new Error('Failed'));
    render(<EquipmentDetail />);

    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.error).toHaveBeenCalledWith('网络错误');
    });
  });
});
