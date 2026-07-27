import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Dashboard from '@/app/dashboard/page';

const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
}));
const mockGetSupervisorDashboard = jest.fn();
const mockGetTechnicianDashboard = jest.fn();
jest.mock('@/lib/api', () => ({
  getSupervisorDashboard: (...args: unknown[]) => mockGetSupervisorDashboard(...args),
  getTechnicianDashboard: (...args: unknown[]) => mockGetTechnicianDashboard(...args),
}));

const mockUseAuth = jest.fn();
jest.mock('@/lib/auth', () => ({
  useAuth: () => mockUseAuth(),
}));

const techData = {
  assigned_to_me: 5,
  today_todo: 2,
  high_priority: 3,
  overdue: 1,
  my_work_orders: [
    { id: 1, title: 'CNC主轴异响', code: 'WO-001', equipment_name: 'CNC-03', status: 'in_progress' },
    { id: 2, title: '传送带卡顿', code: 'WO-002', equipment_name: 'CV-01', status: 'accepted' },
  ],
};

const supervisorData = {
  pending_dispatch: 3,
  in_progress: 5,
  pending_acceptance: 2,
  overdue: 1,
  today_new_faults: 4,
  today_completed: 2,
  avg_repair_hours: 3.5,
  by_priority: [
    { priority: 'P1', count: 2 },
    { priority: 'P2', count: 5 },
    { priority: 'P3', count: 3 },
  ],
  by_equipment_type: [
    { equipment_type: 'CNC', count: 6 },
    { equipment_type: '传送带', count: 4 },
  ],
  recent_work_orders: [
    { id: 1, code: 'WO-001', title: 'CNC主轴异响', status: 'in_progress' },
    { id: 2, code: 'WO-002', title: '传送带卡顿', status: 'completed' },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('Dashboard - Technician View', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { role: 'technician', id: 1, full_name: '工程师', email: 'tech@test.com', is_active: true },
    });
    mockGetTechnicianDashboard.mockResolvedValue(techData);
  });

  it('加载中展示 loading 状态', () => {
    mockGetTechnicianDashboard.mockReturnValue(new Promise(() => {}));
    render(<Dashboard />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('加载失败展示暂无数据', async () => {
    mockGetTechnicianDashboard.mockRejectedValue(new Error('Failed'));
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('暂无数据')).toBeInTheDocument();
    });
  });

  it('展示维修工作台标题', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('维修工作台')).toBeInTheDocument();
    });
  });

  it('展示四个统计卡片', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('分配给我')).toBeInTheDocument();
      expect(screen.getByText('今日待处理')).toBeInTheDocument();
      expect(screen.getByText('高优先级')).toBeInTheDocument();
      expect(screen.getByText('已超时')).toBeInTheDocument();
    });
  });

  it('统计数据正确', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument(); // assigned_to_me
      expect(screen.getByText('2')).toBeInTheDocument(); // today_todo
      expect(screen.getByText('3')).toBeInTheDocument(); // high_priority
      expect(screen.getByText('1')).toBeInTheDocument(); // overdue
    });
  });

  it('快速故障上报按钮跳转', async () => {
    const user = userEvent.setup();
    render(<Dashboard />);
    await waitFor(() => screen.getByText('快速故障上报'));
    await user.click(screen.getByText('快速故障上报'));
    expect(mockPush).toHaveBeenCalledWith('/fault-reports/new');
  });

  it('我的工单按钮跳转', async () => {
    const user = userEvent.setup();
    render(<Dashboard />);
    await waitFor(() => screen.getByText('我的工单'));
    await user.click(screen.getByText('我的工单'));
    expect(mockPush).toHaveBeenCalledWith('/work-orders?mine=true');
  });

  it('展示待处理工单列表', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('CNC主轴异响')).toBeInTheDocument();
      expect(screen.getByText('传送带卡顿')).toBeInTheDocument();
    });
  });

  it('空工单时显示空状态', async () => {
    mockGetTechnicianDashboard.mockResolvedValue({ ...techData, my_work_orders: [] });
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('暂无待处理工单')).toBeInTheDocument();
    });
  });

  it('点击工单行跳转详情', async () => {
    const user = userEvent.setup();
    render(<Dashboard />);
    await waitFor(() => screen.getByText('CNC主轴异响'));
    await user.click(screen.getByText('CNC主轴异响'));
    expect(mockPush).toHaveBeenCalledWith('/work-orders/1');
  });
});

describe('Dashboard - Supervisor View', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { role: 'supervisor', id: 2, full_name: '主管', email: 'sup@test.com', is_active: true },
    });
    mockGetSupervisorDashboard.mockResolvedValue(supervisorData);
  });

  it('展示运维管理仪表盘标题', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('运维管理仪表盘')).toBeInTheDocument();
    });
  });

  it('展示6个统计卡片', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('待分派')).toBeInTheDocument();
      expect(screen.getByText('待验收')).toBeInTheDocument();
      expect(screen.getByText('已超时')).toBeInTheDocument();
      expect(screen.getByText('今日新增')).toBeInTheDocument();
      expect(screen.getByText('今日完成')).toBeInTheDocument();
    });
    // "处理中" appears as both a stat label and a status badge
    const processingElements = screen.getAllByText('处理中');
    expect(processingElements.length).toBeGreaterThanOrEqual(1);
  });

  it('展示平均修复时长', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('平均修复时长: 3.5 小时')).toBeInTheDocument();
    });
  });

  it('点击待分派卡片跳转工单筛选', async () => {
    const user = userEvent.setup();
    render(<Dashboard />);
    await waitFor(() => screen.getByText('待分派'));
    const statCard = screen.getByText('待分派').closest('.card');
    await user.click(statCard!);
    expect(mockPush).toHaveBeenCalledWith('/work-orders?status=pending_dispatch');
  });

  it('展示优先级分布', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('按优先级分布')).toBeInTheDocument();
      expect(screen.getByText('P1 紧急')).toBeInTheDocument();
      expect(screen.getByText('P2 高')).toBeInTheDocument();
      expect(screen.getByText('P3 中')).toBeInTheDocument();
    });
  });

  it('展示设备类型分布', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('按设备类型')).toBeInTheDocument();
      expect(screen.getByText('CNC')).toBeInTheDocument();
      expect(screen.getByText('传送带')).toBeInTheDocument();
    });
  });

  it('展示最近工单列表', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('最近工单')).toBeInTheDocument();
      expect(screen.getByText('CNC主轴异响')).toBeInTheDocument();
      expect(screen.getByText('传送带卡顿')).toBeInTheDocument();
    });
  });

  it('admin 角色也展示主管仪表盘', async () => {
    mockUseAuth.mockReturnValue({
      user: { role: 'admin', id: 1, full_name: '管理员', email: 'admin@test.com', is_active: true },
    });
    mockGetSupervisorDashboard.mockResolvedValue(supervisorData);
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('运维管理仪表盘')).toBeInTheDocument();
    });
  });

  it('无 user 时不做请求', () => {
    mockUseAuth.mockReturnValue({ user: null });
    render(<Dashboard />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
    expect(mockGetTechnicianDashboard).not.toHaveBeenCalled();
    expect(mockGetSupervisorDashboard).not.toHaveBeenCalled();
  });
});
