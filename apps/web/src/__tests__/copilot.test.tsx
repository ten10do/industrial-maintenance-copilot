import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CopilotPage from '@/app/copilot/page';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
}));

const mockCopilotAsk = jest.fn();
const mockListEquipmentTypes = jest.fn();
const mockListFaultCodes = jest.fn();
jest.mock('@/lib/api', () => ({
  copilotAsk: (...args: unknown[]) => mockCopilotAsk(...args),
  listEquipmentTypes: (...args: unknown[]) => mockListEquipmentTypes(...args),
  listFaultCodes: (...args: unknown[]) => mockListFaultCodes(...args),
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

const mockResult = {
  answer: 'E102 故障通常由传感器信号异常或连接线松动引起。建议:\n1. 检查传感器供电电压\n2. 重新紧固连接线\n3. 必要时更换传感器',
  confidence: 0.85,
  citations: [
    {
      source_type: 'knowledge',
      source_id: 1,
      title: 'E102 故障代码诊断手册',
      excerpt: 'E102 表示传感器信号异常，常见原因为供电不稳定或接口松动...',
      relevance_score: 0.92,
      url: '/knowledge/1',
    },
    {
      source_type: 'knowledge',
      source_id: 5,
      title: '传感器维护标准作业程序',
      excerpt: '每季度检查传感器接口紧固状态...',
      relevance_score: 0.78,
    },
  ],
  warnings: ['涉及高压电气设备，维修前务必断开电源并执行 LOTO 程序。'],
  is_mock: true,
  disclaimer: '本回答由 AI 生成，仅供参考。实际维修请以设备手册和安全规范为准。',
};

beforeEach(() => {
  jest.clearAllMocks();
  mockUseAuth.mockReturnValue({
    user: { role: 'technician', id: 1, full_name: '工程师', email: 'tech@test.com', is_active: true },
  });
  mockListEquipmentTypes.mockImplementation(() => new Promise(() => {}));
  mockListFaultCodes.mockImplementation(() => new Promise(() => {}));
  mockCopilotAsk.mockResolvedValue(mockResult);
});

describe('CopilotPage', () => {
  // 基础渲染
  it('渲染页面标题', () => {
    render(<CopilotPage />);
    expect(screen.getByText('AI 维修助手')).toBeInTheDocument();
  });

  // 安全提醒始终可见
  it('始终展示安全提醒信息', () => {
    render(<CopilotPage />);
    expect(screen.getByText(/AI 建议仅供辅助/)).toBeInTheDocument();
  });

  // 问题输入框存在
  it('展示问题输入框', () => {
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    expect(input).toBeInTheDocument();
  });

  // 提交按钮初始禁用
  it('输入为空时提问按钮禁用', () => {
    render(<CopilotPage />);
    const btn = screen.getByTestId('copilot-submit-button');
    expect(btn).toBeDisabled();
  });

  // 输入内容后提交按钮可用
  it('输入内容后提问按钮可用', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, 'E102 故障是什么？');
    const btn = screen.getByTestId('copilot-submit-button');
    expect(btn).not.toBeDisabled();
  });

  // 加载状���
  it('提问后展示检索中状态', async () => {
    const user = userEvent.setup();
    mockCopilotAsk.mockImplementation(() => new Promise(() => {})); // never resolves
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText('检索中...')).toBeInTheDocument();
    });
  });

  // 成功提交后展示回答
  it('成功提交问题后展示回答内容', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, 'E102 故障是什么？');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText(/E102 故障通常由传感器信号异常/)).toBeInTheDocument();
    });
  });

  // 展示 Mock AI 标签
  it('Mock 模式下展示 Mock AI 标识', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText('Mock AI 模式')).toBeInTheDocument();
    });
  });

  // 展示置信度
  it('展示置信度百分比', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText(/置信度:/)).toBeInTheDocument();
      expect(screen.getByText('85%')).toBeInTheDocument();
    });
  });

  // 展示安全警告
  it('展示安全警告信息', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '高压电气维修');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText(/断开电源/)).toBeInTheDocument();
    });
  });

  // 展示引用来源列表
  it('展示引用来源列表', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText(/引用来源/)).toBeInTheDocument();
      expect(screen.getByText('E102 故障代码诊断手册')).toBeInTheDocument();
      expect(screen.getByText('传感器维护标准作业程序')).toBeInTheDocument();
    });
  });

  // 展示引用来源的相关度
  it('展示每个引用来源的相关度百分比', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText('92%')).toBeInTheDocument();
      expect(screen.getByText('78%')).toBeInTheDocument();
    });
  });

  // 无引用来源展示提示
  it('无引用来源时展示证据不足警告', async () => {
    const user = userEvent.setup();
    mockCopilotAsk.mockResolvedValue({
      ...mockResult,
      citations: [],
      confidence: 0.15,
      warnings: [],
    });
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getAllByText(/证据不足/).length).toBeGreaterThanOrEqual(2);
    });
  });

  // 低置信度展示提示
  it('低置信度时展示证据不足提示', async () => {
    const user = userEvent.setup();
    mockCopilotAsk.mockResolvedValue({
      ...mockResult,
      confidence: 0.15,
      citations: [],
      warnings: [],
    });
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText('15%')).toBeInTheDocument();
      expect(screen.getAllByText(/证据不足/).length).toBeGreaterThanOrEqual(2);
    });
  });

  // API 错误处���
  it('API 请求失败时展示错误 toast', async () => {
    const user = userEvent.setup();
    const toast = require('react-hot-toast').default;
    mockCopilotAsk.mockRejectedValue(new Error('服务不可用'));
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });

  // 清空按钮
  it('点击清空按钮重置对话状态', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText(/E102 故障通常/)).toBeInTheDocument();
    });
    // Find the clear button by its Trash2 icon (button with only an icon, no text)
    const allBtns = screen.getAllByRole('button').filter(b => b.querySelector('svg'));
    // The clear button has no text content, only an SVG icon
    const trashBtn = allBtns.find(b => b.textContent === '');
    expect(trashBtn).toBeTruthy();
    if (trashBtn) await user.click(trashBtn);
    // After clearing, input should be empty
    const inputAfter = screen.getByPlaceholderText(/输入维修问题/) as HTMLInputElement;
    expect(inputAfter.value).toBe('');
  });

  // 快捷示例问题
  it('初始状态展示快捷示例问题按钮', () => {
    render(<CopilotPage />);
    expect(screen.getByText('快捷示例')).toBeInTheDocument();
    expect(screen.getByText('E102 故障一般是什么原因？')).toBeInTheDocument();
    expect(screen.getByText('包装机接近开关频繁松动如何处理？')).toBeInTheDocument();
    expect(screen.getByText('更换伺服驱动器前需要完成哪些安全检查？')).toBeInTheDocument();
  });

  // 点击快捷示例提交问题
  it('点击快捷示例问题标签触发提问', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const exampleBtn = screen.getByText('E102 故障一般是什么原因？');
    await user.click(exampleBtn);
    await waitFor(() => {
      expect(screen.getByText(/E102 故障通常由/)).toBeInTheDocument();
    });
  });

  // Enter 键提交
  it('按 Enter 键提交问题', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, 'E102 故障{Enter}');
    await waitFor(() => {
      expect(screen.getByText(/E102 故障通常由/)).toBeInTheDocument();
    });
  });

  // 筛选下拉
  it('展示设备和故障代码筛选下拉', () => {
    render(<CopilotPage />);
    expect(screen.getByText('全部设备类型')).toBeInTheDocument();
    expect(screen.getByText('全部故障代码')).toBeInTheDocument();
  });

  // 免责声明始终展示
  it('回答区域展示免责声明', async () => {
    const user = userEvent.setup();
    render(<CopilotPage />);
    const input = screen.getByPlaceholderText(/输入维修问题/);
    await user.type(input, '问题');
    await user.click(screen.getByTestId('copilot-submit-button'));
    await waitFor(() => {
      expect(screen.getByText(mockResult.disclaimer)).toBeInTheDocument();
    });
  });
});
