import '@testing-library/jest-dom';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from '@/lib/auth';

const mockApiLogin = jest.fn();
const mockGetMe = jest.fn();

jest.mock('@/lib/api', () => ({
  login: (...args: unknown[]) => mockApiLogin(...args),
  getMe: (...args: unknown[]) => mockGetMe(...args),
}));

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  mockGetMe.mockResolvedValue(null);
});

function TestConsumer() {
  const { token, user, login, logout, loading } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="token">{token || 'none'}</span>
      <span data-testid="user">{user?.full_name || 'none'}</span>
      <span data-testid="role">{user?.role || 'none'}</span>
      <button data-testid="login-btn" onClick={() => login('test@email.com', 'pass')}>Login</button>
      <button data-testid="logout-btn" onClick={logout}>Logout</button>
    </div>
  );
}

describe('AuthProvider', () => {
  it('初始状态为 loading，无 token 时 loading 为 false', async () => {
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('token').textContent).toBe('none');
    expect(screen.getByTestId('user').textContent).toBe('none');
  });

  it('localStorage 有 token 时自动恢复用户', async () => {
    localStorage.setItem('token', 'existing-token');
    mockGetMe.mockResolvedValue({
      id: 1, email: 'user@test.com', full_name: '测试用户', role: 'admin', is_active: true,
    });
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => {
      expect(screen.getByTestId('token').textContent).toBe('existing-token');
    });
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('测试用户');
      expect(screen.getByTestId('role').textContent).toBe('admin');
    });
  });

  it('token 恢复失败时清除 localStorage', async () => {
    localStorage.setItem('token', 'bad-token');
    mockGetMe.mockRejectedValue(new Error('Invalid'));
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('login 成功后更新状态和 localStorage', async () => {
    mockApiLogin.mockResolvedValue({
      access_token: 'new-token',
      user_id: 2,
      full_name: '新用户',
      role: 'technician',
    });
    const user = userEvent.setup();
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });

    await user.click(screen.getByTestId('login-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('token').textContent).toBe('new-token');
      expect(screen.getByTestId('user').textContent).toBe('新用户');
      expect(screen.getByTestId('role').textContent).toBe('technician');
      expect(localStorage.getItem('token')).toBe('new-token');
    });
  });

  it('logout 清除状态和 localStorage', async () => {
    localStorage.setItem('token', 'some-token');
    mockGetMe.mockResolvedValue({
      id: 1, email: 'a@b.com', full_name: '用户', role: 'admin', is_active: true,
    });
    const user = userEvent.setup();
    render(<AuthProvider><TestConsumer /></AuthProvider>);
    await waitFor(() => {
      expect(screen.getByTestId('token').textContent).toBe('some-token');
    });

    await user.click(screen.getByTestId('logout-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('token').textContent).toBe('none');
      expect(screen.getByTestId('user').textContent).toBe('none');
      expect(localStorage.getItem('token')).toBeNull();
    });
  });
});
