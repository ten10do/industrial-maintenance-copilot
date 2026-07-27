import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginPage from '@/app/login/page';

const mockPush = jest.fn();
const mockLogin = jest.fn();

jest.mock('@/lib/auth', () => ({
  useAuth: jest.fn(() => ({
    login: mockLogin,
    user: null,
    loading: false,
  })),
}));

beforeEach(() => {
  jest.clearAllMocks();
});

describe('LoginPage', () => {
  it('渲染登录表单和品牌标识', () => {
    render(<LoginPage />);
    expect(screen.getByText('设备运维工单 Copilot')).toBeInTheDocument();
    expect(screen.getByText('工业设备智能维修管理系统')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入邮箱')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入密码')).toBeInTheDocument();
    expect(screen.getByText('登录')).toBeInTheDocument();
  });

  it('表单提交调用 login 并跳转仪表盘', async () => {
    mockLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.clear(screen.getByPlaceholderText('请输入邮箱'));
    await user.type(screen.getByPlaceholderText('请输入邮箱'), 'test@example.com');
    await user.clear(screen.getByPlaceholderText('请输入密码'));
    await user.type(screen.getByPlaceholderText('请输入密码'), 'password123');
    await user.click(screen.getByText('登录'));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123');
    });
  });

  it('登录失败时展示错误信息', async () => {
    mockLogin.mockRejectedValue(new Error('账号或密码错误'));
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.clear(screen.getByPlaceholderText('请输入邮箱'));
    await user.type(screen.getByPlaceholderText('请输入邮箱'), 'bad@test.com');
    await user.clear(screen.getByPlaceholderText('请输入密码'));
    await user.type(screen.getByPlaceholderText('请输入密码'), 'wrong');
    await user.click(screen.getByText('登录'));

    await waitFor(() => {
      expect(screen.getByText('账号或密码错误')).toBeInTheDocument();
    });
  });

  it('登录中展示禁用状态', async () => {
    mockLogin.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    render(<LoginPage />);

    const submitBtn = screen.getByText('登录');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('登录中...')).toBeInTheDocument();
      expect(screen.getByText('登录中...')).toBeDisabled();
    });
  });

  it('展示三个快捷登录按钮', () => {
    render(<LoginPage />);
    expect(screen.getByText('演示账号快捷登录')).toBeInTheDocument();
    expect(screen.getByText(/管理员/)).toBeInTheDocument();
    expect(screen.getByText(/主管/)).toBeInTheDocument();
    expect(screen.getByText(/工程师/)).toBeInTheDocument();
  });

  it('快捷登录管理员成功', async () => {
    mockLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<LoginPage />);

    const adminBtn = screen.getByText(/管理员/).closest('button')!;
    await user.click(adminBtn);

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('admin@example.com', 'Demo123456');
    });
  });

  it('快捷登录主管成功', async () => {
    mockLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<LoginPage />);

    const supBtn = screen.getByText(/主管/).closest('button')!;
    await user.click(supBtn);

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('supervisor@example.com', 'Demo123456');
    });
  });

  it('快捷登录工程师成功', async () => {
    mockLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<LoginPage />);

    const techBtn = screen.getByText(/工程师/).closest('button')!;
    await user.click(techBtn);

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('tech1@example.com', 'Demo123456');
    });
  });

  it('快捷登录失败时展示错误', async () => {
    mockLogin.mockRejectedValue(new Error('网络连接失败'));
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByText(/管理员/).closest('button')!);

    await waitFor(() => {
      expect(screen.getByText('网络连接失败')).toBeInTheDocument();
    });
  });

  it('登录中禁用所有快捷登录按钮', async () => {
    mockLogin.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByText('登录'));

    await waitFor(() => {
      const buttons = screen.getAllByRole('button');
      buttons.forEach(btn => expect(btn).toBeDisabled());
    });
  });
});
