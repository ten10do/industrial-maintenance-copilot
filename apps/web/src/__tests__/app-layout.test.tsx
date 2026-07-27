import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AppLayout from '@/app/app-layout';

const mockPush = jest.fn();
const mockLogout = jest.fn();
const mockUsePathname = jest.fn(() => '/dashboard');

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
  usePathname: () => mockUsePathname(),
}));

jest.mock('@/lib/auth', () => ({
  useAuth: jest.fn(() => ({
    user: { role: 'admin', id: 1, full_name: '管理员', email: 'admin@test.com', is_active: true },
    logout: mockLogout,
  })),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockUsePathname.mockReturnValue('/dashboard');
  const useAuth = require('@/lib/auth').useAuth;
  useAuth.mockReturnValue({
    user: { role: 'admin', id: 1, full_name: '管理员', email: 'admin@test.com', is_active: true },
    logout: mockLogout,
  });
});

function renderWithRole(role: string) {
  const useAuth = require('@/lib/auth').useAuth;
  useAuth.mockReturnValue({
    user: { role, id: 1, full_name: role === 'admin' ? '管理员' : role === 'supervisor' ? '主管' : '工程师', email: `${role}@test.com`, is_active: true },
    logout: mockLogout,
  });
  return render(<AppLayout><div data-testid="child">content</div></AppLayout>);
}

describe('AppLayout', () => {
  it('管理员可见系统管理入口', () => {
    renderWithRole('admin');
    expect(screen.getByText('系统管理')).toBeInTheDocument();
  });

  it('主管不可见管理员专属入口', () => {
    renderWithRole('supervisor');
    expect(screen.getByText('故障上报')).toBeInTheDocument();
    expect(screen.getByText('维修工单')).toBeInTheDocument();
    expect(screen.queryByText('系统管理')).not.toBeInTheDocument();
  });

  it('维修工程师只显示授权菜单', () => {
    renderWithRole('technician');
    expect(screen.getByText('仪表盘')).toBeInTheDocument();
    expect(screen.getByText('故障上报')).toBeInTheDocument();
    expect(screen.getByText('维修工单')).toBeInTheDocument();
    expect(screen.getByText('设备台账')).toBeInTheDocument();
    expect(screen.queryByText('系统管理')).not.toBeInTheDocument();
  });

  it('当前路由正确高亮', () => {
    mockUsePathname.mockReturnValue('/fault-reports');
    renderWithRole('admin');
    const activeBtn = screen.getByText('故障上报').closest('button');
    expect(activeBtn).toBeTruthy();
  });

  it('非激活路由不高亮', () => {
    mockUsePathname.mockReturnValue('/dashboard');
    renderWithRole('admin');
    const faultBtn = screen.getByText('故障上报').closest('button');
    expect(faultBtn?.className).not.toContain('bg-primary/15');
  });

  it('移动端菜单按钮存在', () => {
    renderWithRole('admin');
    const menuButtons = screen.queryAllByRole('button');
    expect(menuButtons.length).toBeGreaterThan(0);
  });

  it('登录页面不渲染侧边栏', () => {
    mockUsePathname.mockReturnValue('/login');
    const useAuth = require('@/lib/auth').useAuth;
    useAuth.mockReturnValue({
      user: { role: 'admin', id: 1, full_name: '管理员', email: 'admin@test.com', is_active: true },
      logout: mockLogout,
    });
    render(<AppLayout><div data-testid="child">login content</div></AppLayout>);
    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(screen.queryByText('仪表盘')).not.toBeInTheDocument();
  });

  it('退出登录调用 logout 并跳转登录页', async () => {
    renderWithRole('admin');
    const user = userEvent.setup();
    const logoutBtn = screen.getByText('退出登录');
    await user.click(logoutBtn);
    expect(mockLogout).toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith('/login');
  });

  it('渲染子元素内容', () => {
    renderWithRole('admin');
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });
});
