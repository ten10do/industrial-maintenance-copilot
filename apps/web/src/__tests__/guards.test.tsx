import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import AuthGuard from '@/lib/guards';

const mockPush = jest.fn();
const mockUseAuth = jest.fn();
const mockUsePathname = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
  usePathname: () => mockUsePathname(),
}));

jest.mock('@/lib/auth', () => ({
  useAuth: () => mockUseAuth(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockUseAuth.mockReset();
  mockUsePathname.mockReset();
});

describe('AuthGuard', () => {
  it('未经认证用户访问受保护路径时重定向到登录', () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    mockUsePathname.mockReturnValue('/dashboard');
    render(<AuthGuard><div data-testid="protected">Protected</div></AuthGuard>);
    expect(mockPush).toHaveBeenCalledWith('/login');
  });

  it('已认证用户访问 /login 时重定向到仪表盘', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, role: 'technician', full_name: '工程师', email: 't@t.com', is_active: true },
      loading: false,
    });
    mockUsePathname.mockReturnValue('/login');
    render(<AuthGuard><div>Login</div></AuthGuard>);
    expect(mockPush).toHaveBeenCalledWith('/dashboard');
  });

  it('已认证用户访问受保护路径时渲染子组件', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, role: 'admin', full_name: '管理员', email: 'a@a.com', is_active: true },
      loading: false,
    });
    mockUsePathname.mockReturnValue('/dashboard');
    render(<AuthGuard><div data-testid="child">Dashboard Content</div></AuthGuard>);
    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('公共路径 /login 未经认证时直接渲染', () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    mockUsePathname.mockReturnValue('/login');
    render(<AuthGuard><div data-testid="login-content">Login Page</div></AuthGuard>);
    expect(screen.getByTestId('login-content')).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('公共路径 / 未经认证时直接渲染', () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    mockUsePathname.mockReturnValue('/');
    render(<AuthGuard><div data-testid="home-content">Home</div></AuthGuard>);
    expect(screen.getByTestId('home-content')).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('loading 时未经认证展示加载中', () => {
    mockUseAuth.mockReturnValue({ user: null, loading: true });
    mockUsePathname.mockReturnValue('/dashboard');
    render(<AuthGuard><div>Should not show</div></AuthGuard>);
    expect(screen.queryByText('Should not show')).not.toBeInTheDocument();
  });

  it('loading 为 true 时不触发重定向', () => {
    mockUseAuth.mockReturnValue({ user: null, loading: true });
    mockUsePathname.mockReturnValue('/fault-reports');
    render(<AuthGuard><div>Should not show</div></AuthGuard>);
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('管理员角色正确渲染子组件', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, role: 'admin', full_name: '管理员', email: 'admin@t.com', is_active: true },
      loading: false,
    });
    mockUsePathname.mockReturnValue('/admin');
    render(<AuthGuard><div data-testid="admin-page">Admin</div></AuthGuard>);
    expect(screen.getByTestId('admin-page')).toBeInTheDocument();
  });

  it('主管角色正确渲染子组件', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 2, role: 'supervisor', full_name: '主管', email: 'sup@t.com', is_active: true },
      loading: false,
    });
    mockUsePathname.mockReturnValue('/work-orders');
    render(<AuthGuard><div data-testid="wo-page">Work Orders</div></AuthGuard>);
    expect(screen.getByTestId('wo-page')).toBeInTheDocument();
  });

  it('工程师角色正确渲染子组件', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 3, role: 'technician', full_name: '工程师', email: 'tech@t.com', is_active: true },
      loading: false,
    });
    mockUsePathname.mockReturnValue('/equipment');
    render(<AuthGuard><div data-testid="eq-page">Equipment</div></AuthGuard>);
    expect(screen.getByTestId('eq-page')).toBeInTheDocument();
  });
});
