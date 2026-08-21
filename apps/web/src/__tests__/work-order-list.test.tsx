import '@testing-library/jest-dom';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkOrderList from '@/app/work-orders/page';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
}));

const mockListWorkOrders = jest.fn();
const mockListTechnicians = jest.fn();
const mockAssignWorkOrder = jest.fn();
const mockCancelWorkOrder = jest.fn();
jest.mock('@/lib/api', () => ({
  listWorkOrders: (...args: unknown[]) => mockListWorkOrders(...args),
  listTechnicians: (...args: unknown[]) => mockListTechnicians(...args),
  assignWorkOrder: (...args: unknown[]) => mockAssignWorkOrder(...args),
  cancelWorkOrder: (...args: unknown[]) => mockCancelWorkOrder(...args),
}));

const mockUseAuth = jest.fn();
jest.mock('@/lib/auth', () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const mockWos = [
  { id: 1, title: 'CNC主轴异响', code: 'WO-001', equipment_name: 'CNC-03', priority: 'P1', status: 'pending_dispatch', assignee_name: null, created_at: '2026-07-27T08:00:00' },
  { id: 2, title: '传送带卡顿', code: 'WO-002', equipment_name: 'CV-01', priority: 'P2', status: 'in_progress', assignee_name: '工程师', created_at: '2026-07-26T10:00:00' },
  { id: 3, title: '包装机故障', code: 'WO-003', equipment_name: 'PK-01', priority: 'P3', status: 'completed', assignee_name: '李四', created_at: '2026-07-25T14:00:00' },
];

beforeEach(() => {
  jest.clearAllMocks();
  mockUseAuth.mockReturnValue({
    user: { role: 'supervisor', id: 1, full_name: '主管', email: 'sup@test.com', is_active: true },
  });
  mockListWorkOrders.mockResolvedValue({ items: mockWos, total: 3 });
});

describe('WorkOrderList', () => {
  it('成功加载并展示工单列表', async () => {
    render(<WorkOrderList />);
    await waitFor(() => {
      expect(screen.getByText('CNC主轴异响')).toBeInTheDocument();
      expect(screen.getByText('传送带卡顿')).toBeInTheDocument();
      expect(screen.getByText('包装机故障')).toBeInTheDocument();
    });
  });

  it('加载过程中展示加载状态', () => {
    mockListWorkOrders.mockReturnValue(new Promise(() => {}));
    render(<WorkOrderList />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('空数据展示空状态', async () => {
    mockListWorkOrders.mockResolvedValue({ items: [], total: 0 });
    render(<WorkOrderList />);
    await waitFor(() => {
      expect(screen.getByText('暂无工单')).toBeInTheDocument();
    });
  });

  it('API 失败时展示错误 toast', async () => {
    mockListWorkOrders.mockRejectedValue(new Error('网络错误'));
    render(<WorkOrderList />);
    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.error).toHaveBeenCalledWith('网络错误');
    });
  });

  it('展示状态筛选按钮', async () => {
    render(<WorkOrderList />);
    expect(screen.getByText('全部')).toBeInTheDocument();
    expect(screen.getByText('待分派')).toBeInTheDocument();
    expect(screen.getByText('已分派')).toBeInTheDocument();
    expect(screen.getAllByText('处理中').length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('CNC主轴异响')).toBeInTheDocument();
  });

  it('点击状态筛选重新加载', async () => {
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('CNC主轴异响'));

    await user.click(screen.getAllByText('处理中')[0]);

    await waitFor(() => {
      expect(mockListWorkOrders).toHaveBeenCalledWith(
        expect.objectContaining({ status_filter: 'in_progress' })
      );
    });
  });

  it('搜索框回车触发查询', async () => {
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('CNC主轴异响'));

    const searchInput = screen.getByPlaceholderText('搜索工单...');
    await user.type(searchInput, '主轴');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(mockListWorkOrders).toHaveBeenCalledWith(
        expect.objectContaining({ keyword: '主轴' })
      );
    });
  });

  it('点击工单行跳转详情', async () => {
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('CNC主轴异响'));
    await user.click(screen.getByText('CNC主轴异响'));
    expect(mockPush).toHaveBeenCalledWith('/work-orders/1');
  });

  it('新建工单按钮跳转故障上报', async () => {
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await user.click(screen.getByText('新建工单'));
    expect(mockPush).toHaveBeenCalledWith('/fault-reports/new');
    expect(await screen.findByText('CNC主轴异响')).toBeInTheDocument();
  });

  it('主管看到待分派工单的分派按钮', async () => {
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('CNC主轴异响'));
    expect(screen.getByText('分派')).toBeInTheDocument();
  });

  it('已分派的工单不显示分派按钮', async () => {
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('CNC主轴异响'));
    const rows = screen.getAllByRole('row');
    const buttons = screen.getAllByText('分派');
    expect(buttons.length).toBe(1); // only for pending_dispatch
  });

  it('工程师角色不显示分派按钮', async () => {
    mockUseAuth.mockReturnValue({
      user: { role: 'technician', id: 3, full_name: '工程师', email: 't@t.com', is_active: true },
    });
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('CNC主轴异响'));
    expect(screen.queryByText('分派')).not.toBeInTheDocument();
  });

  it('工程师看到仅看我的按钮', async () => {
    mockUseAuth.mockReturnValue({
      user: { role: 'technician', id: 3, full_name: '工程师', email: 't@t.com', is_active: true },
    });
    render(<WorkOrderList />);
    expect(screen.getByText('仅看我的')).toBeInTheDocument();
    expect(await screen.findByText('CNC主轴异响')).toBeInTheDocument();
  });

  it('点击仅看我的切换筛选', async () => {
    mockUseAuth.mockReturnValue({
      user: { role: 'technician', id: 3, full_name: '工程师', email: 't@t.com', is_active: true },
    });
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await user.click(screen.getByText('仅看我的'));
    await waitFor(() => {
      expect(mockListWorkOrders).toHaveBeenCalledWith(
        expect.objectContaining({ mine: 'true' })
      );
    });
  });

  it('点击分派打开技术人员列表', async () => {
    mockListTechnicians.mockResolvedValue([
      { user_id: 10, full_name: '王工', active_work_orders: 2, skills: [{ name: 'CNC' }], availability: 'available' },
    ]);
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('分派'));
    await user.click(screen.getByText('分派'));
    await waitFor(() => {
      expect(screen.getByText('分派给维修工程师')).toBeInTheDocument();
      expect(screen.getByText('王工')).toBeInTheDocument();
    });
  });

  it('分派成功', async () => {
    mockListTechnicians.mockResolvedValue([
      { user_id: 10, full_name: '王工', active_work_orders: 2, skills: [{ name: 'CNC' }], availability: 'available' },
    ]);
    mockAssignWorkOrder.mockResolvedValue({});
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('分派'));
    await user.click(screen.getByText('分派'));
    await waitFor(() => screen.getByText('王工'));
    await user.click(screen.getByText('王工'));
    await waitFor(() => {
      expect(mockAssignWorkOrder).toHaveBeenCalledWith(1, { assignee_id: 10 });
      const toast = require('react-hot-toast').default;
      expect(toast.success).toHaveBeenCalledWith('分派成功');
    });
  });

  it('分派失败展示错误', async () => {
    mockListTechnicians.mockResolvedValue([
      { user_id: 10, full_name: '王工', active_work_orders: 2, skills: [{ name: 'CNC' }], availability: 'available' },
    ]);
    mockAssignWorkOrder.mockRejectedValue(new Error('分派失败'));
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('分派'));
    await user.click(screen.getByText('分派'));
    await waitFor(() => screen.getByText('王工'));
    await user.click(screen.getByText('王工'));
    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.error).toHaveBeenCalledWith('分派失败');
    });
  });

  it('点击遮罩关闭分派弹窗', async () => {
    mockListTechnicians.mockResolvedValue([
      { user_id: 10, full_name: '王工', active_work_orders: 2, skills: [{ name: 'CNC' }], availability: 'available' },
    ]);
    const user = userEvent.setup();
    render(<WorkOrderList />);
    await waitFor(() => screen.getByText('分派'));
    await user.click(screen.getByText('分派'));
    await waitFor(() => screen.getByText('分派给维修工程师'));

    const backdrop = document.querySelector('.fixed.inset-0');
    await user.click(backdrop!);
    await waitFor(() => {
      expect(screen.queryByText('分派给维修工程师')).not.toBeInTheDocument();
    });
  });
});
