import '@testing-library/jest-dom';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FaultReportList from '@/app/fault-reports/page';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
}));

const mockListFaultReports = jest.fn();
const mockConvertFaultReportToWorkOrder = jest.fn();
jest.mock('@/lib/api', () => ({
  listFaultReports: (...args: unknown[]) => mockListFaultReports(...args),
  convertFaultReportToWorkOrder: (...args: unknown[]) => mockConvertFaultReportToWorkOrder(...args),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const pendingItem = {
  id: 1,
  title: 'CNC主轴异响',
  urgency: 'high',
  status: 'pending',
  equipment_name: 'CNC-03',
  description: '加工精度偏差',
  reporter_name: '张三',
  occurred_at: '2026-07-27T08:00:00',
  is_downtime: false,
  affects_production: true,
  has_safety_risk: false,
  related_work_order_id: null,
};

const convertedItem = {
  id: 2,
  title: '传送带卡顿',
  urgency: 'medium',
  status: 'converted',
  equipment_name: 'CV-01',
  description: '间歇性卡顿',
  reporter_name: '李四',
  occurred_at: '2026-07-26T10:00:00',
  is_downtime: true,
  affects_production: true,
  has_safety_risk: true,
  related_work_order_id: 5,
  related_work_order_code: 'WO-2026-0005',
};

const mockItems = [pendingItem, convertedItem];

beforeEach(() => {
  jest.clearAllMocks();
  window.confirm = jest.fn();
});

describe('FaultReportList', () => {
  it('成功加载并展示故障上报列表', async () => {
    mockListFaultReports.mockResolvedValue({ items: mockItems });
    render(<FaultReportList />);
    await waitFor(() => {
      expect(screen.getByText('CNC主轴异响')).toBeInTheDocument();
      expect(screen.getByText('传送带卡顿')).toBeInTheDocument();
    });
  });

  it('空数据时展示空状态', async () => {
    mockListFaultReports.mockResolvedValue({ items: [] });
    render(<FaultReportList />);
    await waitFor(() => {
      expect(screen.getByText('暂无故障上报记录')).toBeInTheDocument();
      expect(screen.getByText('新建故障上报')).toBeInTheDocument();
    });
  });

  it('加载过程中展示加载状态', () => {
    mockListFaultReports.mockReturnValue(new Promise(() => {}));
    render(<FaultReportList />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('API 失败时展示错误 toast', async () => {
    mockListFaultReports.mockRejectedValue(new Error('网络错误'));
    render(<FaultReportList />);
    await waitFor(() => {
      expect(screen.getByText('加载中...')).toBeInTheDocument();
    });
    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.error).toHaveBeenCalledWith('网络错误');
    });
  });

  it('点击列表项进入详情页', async () => {
    mockListFaultReports.mockResolvedValue({ items: mockItems });
    const user = userEvent.setup();
    render(<FaultReportList />);
    await waitFor(() => screen.getByText('CNC主轴异响'));
    await user.click(screen.getByText('CNC主轴异响'));
    expect(mockPush).toHaveBeenCalledWith('/fault-reports/1');
  });

  it('未关联工单时显示创建工单按钮', async () => {
    mockListFaultReports.mockResolvedValue({ items: [pendingItem] });
    render(<FaultReportList />);
    await waitFor(() => {
      expect(screen.getByText('创建工单')).toBeInTheDocument();
    });
  });

  it('已关联工单时显示查看工单按钮', async () => {
    mockListFaultReports.mockResolvedValue({ items: [convertedItem] });
    render(<FaultReportList />);
    await waitFor(() => {
      expect(screen.getByText('查看工单')).toBeInTheDocument();
    });
  });

  it('停机和影响生产标记正确展示', async () => {
    mockListFaultReports.mockResolvedValue({ items: mockItems });
    render(<FaultReportList />);
    await waitFor(() => {
      expect(screen.getAllByText('● 影响生产').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('高风险记录展示安全风险标识', async () => {
    mockListFaultReports.mockResolvedValue({ items: [convertedItem] });
    render(<FaultReportList />);
    await waitFor(() => {
      expect(screen.getByText('▲ 安全风险')).toBeInTheDocument();
    });
  });

  it('创建工单成功后跳转工单详情', async () => {
    mockListFaultReports.mockResolvedValue({ items: [pendingItem] });
    mockConvertFaultReportToWorkOrder.mockResolvedValue({
      work_order_id: 10,
      fault_report_id: 1,
      work_order_code: 'WO-2026-0010',
      priority: 'P2',
      status: 'pending_dispatch',
    });
    (window.confirm as jest.Mock).mockReturnValue(true);
    const user = userEvent.setup();
    render(<FaultReportList />);
    await waitFor(() => screen.getByText('创建工单'));
    await user.click(screen.getByText('创建工单'));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.success).toHaveBeenCalledWith('工单创建成功');
      expect(mockPush).toHaveBeenCalledWith('/work-orders/10');
    });
  });

  it('409 冲突时跳转已有工单', async () => {
    const { ApiError } = require('@/lib/types');
    mockListFaultReports.mockResolvedValue({ items: [pendingItem] });
    mockConvertFaultReportToWorkOrder.mockRejectedValue(
      new ApiError(409, { code: 'DUPLICATE', message: '已存在', work_order_id: 7 })
    );
    (window.confirm as jest.Mock).mockReturnValue(true);
    const user = userEvent.setup();
    render(<FaultReportList />);
    await waitFor(() => screen.getByText('创建工单'));
    await user.click(screen.getByText('创建工单'));
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/work-orders/7');
    });
  });

  it('查看工单按钮跳转到关联工单', async () => {
    mockListFaultReports.mockResolvedValue({ items: [convertedItem] });
    const user = userEvent.setup();
    render(<FaultReportList />);
    await waitFor(() => screen.getByText('查看工单'));
    await user.click(screen.getByText('查看工单'));
    expect(mockPush).toHaveBeenCalledWith('/work-orders/5');
  });

  it('取消确认弹窗时不调用转换接口', async () => {
    mockListFaultReports.mockResolvedValue({ items: [pendingItem] });
    (window.confirm as jest.Mock).mockReturnValue(false);
    const user = userEvent.setup();
    render(<FaultReportList />);
    await waitFor(() => screen.getByText('创建工单'));
    await user.click(screen.getByText('创建工单'));
    expect(window.confirm).toHaveBeenCalled();
    expect(mockConvertFaultReportToWorkOrder).not.toHaveBeenCalled();
  });
});
