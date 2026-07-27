import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FaultReportDetail from '@/app/fault-reports/[id]/page';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
  useParams: jest.fn(() => ({ id: '1' })),
}));

const mockGetFaultReport = jest.fn();
const mockConvertFaultReportToWorkOrder = jest.fn();
jest.mock('@/lib/api', () => ({
  getFaultReport: (...args: unknown[]) => mockGetFaultReport(...args),
  convertFaultReportToWorkOrder: (...args: unknown[]) => mockConvertFaultReportToWorkOrder(...args),
}));

jest.mock('@/lib/auth', () => ({
  useAuth: jest.fn(() => ({ user: { role: 'supervisor', id: 1, full_name: '主管', email: 'sup@test.com', is_active: true } })),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const pendingReport = {
  id: 1,
  title: 'CNC主轴异响',
  urgency: 'high',
  status: 'pending',
  equipment_code: 'CNC-03',
  equipment_name: '3号CNC',
  fault_code_id: 101,
  phenomenon: '异响',
  description: '主轴运转时有异常噪音',
  is_downtime: false,
  affects_production: true,
  has_safety_risk: false,
  reporter_name: '张三',
  contact: '13800001111',
  occurred_at: '2026-07-27T08:00:00',
  created_at: '2026-07-27T08:05:00',
  related_work_order_id: null,
  raw_text: null,
  photos: [],
};

const convertedReport = {
  ...pendingReport,
  status: 'converted',
  related_work_order_id: 5,
  related_work_order_code: 'WO-2026-0005',
  related_work_order_status: 'pending_dispatch',
};

beforeEach(() => {
  jest.clearAllMocks();
  window.confirm = jest.fn();
});

describe('FaultReportDetail', () => {
  it('成功展示详情', async () => {
    mockGetFaultReport.mockResolvedValue(pendingReport);
    render(<FaultReportDetail />);
    await waitFor(() => {
      expect(screen.getByText('CNC主轴异响')).toBeInTheDocument();
      expect(screen.getAllByText('高').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('待处理')).toBeInTheDocument();
    });
  });

  it('加载失败时展示错误状态', async () => {
    mockGetFaultReport.mockRejectedValue(new Error('服务器错误'));
    render(<FaultReportDetail />);
    await waitFor(() => {
      expect(screen.getByText('服务器错误')).toBeInTheDocument();
      expect(screen.getByText('返回列表')).toBeInTheDocument();
    });
  });

  it('report 为 null 时展示不存在状态', async () => {
    mockGetFaultReport.mockResolvedValue(null);
    render(<FaultReportDetail />);
    await waitFor(() => {
      expect(screen.getByText('故障上报不存在')).toBeInTheDocument();
    });
  });

  it('未关联工单时显示创建工单按钮', async () => {
    mockGetFaultReport.mockResolvedValue(pendingReport);
    render(<FaultReportDetail />);
    await waitFor(() => {
      expect(screen.getByText('尚未创建维修工单')).toBeInTheDocument();
    });
    expect(screen.getAllByText('创建维修工单').length).toBeGreaterThanOrEqual(1);
  });

  it('已关联工单时显示查看工单按钮', async () => {
    mockGetFaultReport.mockResolvedValue(convertedReport);
    render(<FaultReportDetail />);
    await waitFor(() => {
      expect(screen.getByText('关联工单')).toBeInTheDocument();
      expect(screen.getByText('查看工单')).toBeInTheDocument();
    });
  });

  it('创建工单成功后跳转工单详情', async () => {
    mockGetFaultReport.mockResolvedValue(pendingReport);
    mockConvertFaultReportToWorkOrder.mockResolvedValue({
      work_order_id: 10,
      fault_report_id: 1,
      work_order_code: 'WO-2026-0010',
      priority: 'P2',
      status: 'pending_dispatch',
    });
    (window.confirm as jest.Mock).mockReturnValue(true);
    const user = userEvent.setup();
    render(<FaultReportDetail />);
    await waitFor(() => { const btns = screen.getAllByText('创建维修工单'); expect(btns.length).toBeGreaterThanOrEqual(1); });
    const btns = screen.getAllByText('创建维修工单');
    await user.click(btns[0]);
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/work-orders/10');
    });
  });

  it('409 冲突时跳转已有工单', async () => {
    const { ApiError } = require('@/lib/types');
    mockGetFaultReport.mockResolvedValue(pendingReport);
    mockConvertFaultReportToWorkOrder.mockRejectedValue(
      new ApiError(409, { code: 'DUPLICATE', message: '已关联', work_order_id: 7 })
    );
    (window.confirm as jest.Mock).mockReturnValue(true);
    const user = userEvent.setup();
    render(<FaultReportDetail />);
    await waitFor(() => { const btns = screen.getAllByText('创建维修工单'); expect(btns.length).toBeGreaterThanOrEqual(1); });
    const btns = screen.getAllByText('创建维修工单');
    await user.click(btns[0]);
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/work-orders/7');
    });
  });

  it('安全风险标记显示警告卡片', async () => {
    const riskyReport = { ...pendingReport, has_safety_risk: true };
    mockGetFaultReport.mockResolvedValue(riskyReport);
    render(<FaultReportDetail />);
    await waitFor(() => {
      expect(screen.getByText('安全风险警告')).toBeInTheDocument();
    });
  });

  it('点击返回列表按钮跳转到列表页', async () => {
    mockGetFaultReport.mockResolvedValue(pendingReport);
    const user = userEvent.setup();
    render(<FaultReportDetail />);
    await waitFor(() => screen.getByText('CNC主轴异响'));
    const backBtns = screen.getAllByText('返回列表');
    await user.click(backBtns[0]);
    expect(mockPush).toHaveBeenCalledWith('/fault-reports');
  });

  it('工程师角色看到权限提示', async () => {
    const useAuth = require('@/lib/auth').useAuth;
    useAuth.mockReturnValue({
      user: { role: 'technician', id: 3, full_name: '工程师', email: 'tech@test.com', is_active: true },
    });
    mockGetFaultReport.mockResolvedValue(pendingReport);
    render(<FaultReportDetail />);
    await waitFor(() => {
      expect(screen.getByText('仅主管和管理员可以创建工单')).toBeInTheDocument();
    });
  });
});
