import '@testing-library/jest-dom';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import KnowledgeList from '@/app/knowledge/page';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
  usePathname: jest.fn(() => '/knowledge'),
}));

const mockListKnowledge = jest.fn();
const mockListEquipmentTypes = jest.fn();
const mockListFaultCodes = jest.fn();
jest.mock('@/lib/api', () => ({
  listKnowledge: (...args: unknown[]) => mockListKnowledge(...args),
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

const mockItems = [
  {
    id: 1, title: 'CNC 主轴维修手册', category: 'manual', status: 'published',
    summary: '主轴维修详细步骤', tags: ['主轴', '维修'],
    source: '厂家资料', updated_at: '2026-07-20T08:00:00',
    equipment_type_id: 1, fault_code_id: null,
  },
  {
    id: 2, title: '传送带安全操作规程', category: 'sop', status: 'published',
    summary: '传送带操作安全规范', tags: ['传送带', '安全'],
    source: null, updated_at: '2026-07-19T10:00:00',
    equipment_type_id: null, fault_code_id: null,
  },
  {
    id: 3, title: '液压系统故障案例', category: 'case', status: 'draft',
    summary: '液压系统常见故障汇总', tags: ['液压', '故障'],
    source: '维修记录', updated_at: '2026-07-18T14:00:00',
    equipment_type_id: 2, fault_code_id: 1,
  },
];

beforeEach(() => {
  jest.clearAllMocks();
  mockUseAuth.mockReturnValue({
    user: { role: 'admin', id: 1, full_name: '管理员', email: 'admin@test.com', is_active: true },
  });
  mockListKnowledge.mockResolvedValue({ items: mockItems, total: 3 });
  mockListEquipmentTypes.mockResolvedValue([
    { id: 1, name: 'CNC机床' }, { id: 2, name: '液压站' },
  ]);
  mockListFaultCodes.mockResolvedValue([
    { id: 1, code: 'E001', name: '主轴异响' }, { id: 2, code: 'E002', name: '压力异常' },
  ]);
});

describe('KnowledgeList', () => {
  // 基础渲染
  it('渲染页面标题', async () => {
    render(<KnowledgeList />);
    expect(screen.getByText('知识库')).toBeInTheDocument();
  });

  // 加载状态
  it('加载过程中展示加载状态', () => {
    mockListKnowledge.mockImplementation(() => new Promise(() => {})); // never resolves
    render(<KnowledgeList />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  // 成功加载列表
  it('成功加载并展示知识条目列表', async () => {
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('CNC 主轴维修手册')).toBeInTheDocument();
    });
    expect(screen.getByText('传送带安全操作规程')).toBeInTheDocument();
    expect(screen.getByText('液压系统故障案例')).toBeInTheDocument();
  });

  // 展示分类标签
  it('展示正确的分类标签', async () => {
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('CNC 主轴维修手册')).toBeInTheDocument();
    });
    expect(screen.getAllByText('维修手册').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('标准作业程序').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('维修案例').length).toBeGreaterThanOrEqual(2);
  });

  // 展示状态标签
  it('展示已发布/草稿状态标签', async () => {
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('CNC 主轴维修手册')).toBeInTheDocument();
    });
    const publishedBadges = screen.getAllByText('已发布');
    expect(publishedBadges.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('草稿')).toBeInTheDocument();
  });

  // 展示摘要信息
  it('展示条目的摘要信息', async () => {
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('CNC 主轴维修手册')).toBeInTheDocument();
    });
    expect(screen.getByText('主轴维修详细步骤')).toBeInTheDocument();
    expect(screen.getByText('来源: 厂家资料')).toBeInTheDocument();
  });

  // 空状态
  it('知识库为空时展示空状态提示', async () => {
    mockListKnowledge.mockResolvedValue({ items: [], total: 0 });
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('知识库中暂无内容')).toBeInTheDocument();
    });
  });

  // 管理员可见新建按钮
  it('管理员可见新建条目按钮', async () => {
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('CNC 主轴维修手册')).toBeInTheDocument();
    });
    expect(screen.getByText('新建条目')).toBeInTheDocument();
  });

  // 主管可见新建按钮
  it('主管可见新建条目按钮', async () => {
    mockUseAuth.mockReturnValue({
      user: { role: 'supervisor', id: 2, full_name: '主管', email: 'sup@test.com', is_active: true },
    });
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('CNC 主轴维修手册')).toBeInTheDocument();
    });
    expect(screen.getByText('新建条目')).toBeInTheDocument();
  });

  // 维修工程师不可见新建按钮
  it('维修工程师不可见新建条目按钮', async () => {
    mockUseAuth.mockReturnValue({
      user: { role: 'technician', id: 3, full_name: '工程师', email: 'tech@test.com', is_active: true },
    });
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('CNC 主轴维修手册')).toBeInTheDocument();
    });
    expect(screen.queryByText('新建条目')).not.toBeInTheDocument();
  });

  // 搜索框存在
  it('展示搜索输入框和分类筛选', () => {
    render(<KnowledgeList />);
    const searchInput = screen.getByPlaceholderText('搜索标题或内容...');
    expect(searchInput).toBeInTheDocument();
  });

  // 分类筛选下拉
  it('展示分类筛选下拉选项', () => {
    render(<KnowledgeList />);
    expect(screen.getByText('全部类型')).toBeInTheDocument();
    expect(screen.getByText('全部设备类型')).toBeInTheDocument();
    expect(screen.getByText('全部故障代码')).toBeInTheDocument();
  });

  // API 错误处理
  it('API 请求失败时调用 toast.error', async () => {
    const toast = require('react-hot-toast').default;
    mockListKnowledge.mockRejectedValue(new Error('网络错误'));
    mockListEquipmentTypes.mockRejectedValue(new Error('网络错误'));
    mockListFaultCodes.mockRejectedValue(new Error('网络错误'));
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });

  // 点击条目跳转详情页
  it('点击知识条目跳转到详情页', async () => {
    const user = userEvent.setup();
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('CNC 主轴维修手册')).toBeInTheDocument();
    });
    await user.click(screen.getByText('CNC 主轴维修手册'));
    expect(mockPush).toHaveBeenCalledWith('/knowledge/1');
  });

  // 点击新建跳转创建页
  it('点击新建条目跳转到创建页', async () => {
    const user = userEvent.setup();
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('新建条目')).toBeInTheDocument();
    });
    await user.click(screen.getByText('新建条目'));
    expect(mockPush).toHaveBeenCalledWith('/knowledge/new');
  });

  // 分页展示（total > 20）
  it('条目总数超过20时展示分页控件', async () => {
    const manyItems = Array.from({ length: 25 }, (_, i) => ({
      id: i + 1, title: `条目 ${i + 1}`, category: 'manual', status: 'published',
      summary: null, tags: [], source: null, updated_at: '2026-07-01T00:00:00',
      equipment_type_id: null, fault_code_id: null,
    }));
    mockListKnowledge.mockResolvedValue({ items: manyItems.slice(0, 20), total: 25 });
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('条目 1')).toBeInTheDocument();
    });
    expect(screen.getByText('上一页')).toBeInTheDocument();
    expect(screen.getByText('下一页')).toBeInTheDocument();
  });

  // 搜索无结果
  it('搜索无结果时展示未找到提示', async () => {
    const user = userEvent.setup();
    mockListKnowledge.mockResolvedValue({ items: [], total: 0 });
    render(<KnowledgeList />);
    await waitFor(() => {
      expect(screen.getByText('知识库中暂无内容')).toBeInTheDocument();
    });
    // Type a keyword and press Enter to trigger search
    const searchInput = screen.getByPlaceholderText('搜索标题或内容...');
    await user.type(searchInput, '不存在的关键词');
    // After search with keyword, should show "未找到匹配的知识条目"
    await waitFor(() => {
      expect(screen.getByText('未找到匹配的知识条目')).toBeInTheDocument();
    });
  });
});
