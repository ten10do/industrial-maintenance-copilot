import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import EquipmentList from '@/app/equipment/page';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
}));

const mockListEquipment = jest.fn();
const mockListEquipmentTypes = jest.fn();
jest.mock('@/lib/api', () => ({
  listEquipment: (...args: unknown[]) => mockListEquipment(...args),
  listEquipmentTypes: (...args: unknown[]) => mockListEquipmentTypes(...args),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const mockItems = [
  { id: 1, name: '3号CNC', code: 'CNC-03', status: 'running', location: 'A车间', equipment_type_name: 'CNC', manufacturer: 'Fanuc', model: 'α-D14MiB5' },
  { id: 2, name: '1号传送带', code: 'CV-01', status: 'fault', location: 'B车间', equipment_type_name: '传送带', manufacturer: 'Siemens', model: 'V20' },
  { id: 3, name: '2号包装机', code: 'PK-02', status: 'under_repair', location: 'C车间', equipment_type_name: '包装机', manufacturer: 'Bosch', model: 'PKD' },
];

const mockTypes = [
  { id: 1, name: 'CNC' },
  { id: 2, name: '传送带' },
];

beforeEach(() => {
  jest.clearAllMocks();
  mockListEquipment.mockResolvedValue({ items: mockItems, total: 3 });
  mockListEquipmentTypes.mockResolvedValue(mockTypes);
});

describe('EquipmentList', () => {
  it('成功加载并展示设备列表', async () => {
    render(<EquipmentList />);
    await waitFor(() => {
      expect(screen.getByText('3号CNC')).toBeInTheDocument();
      expect(screen.getByText('1号传送带')).toBeInTheDocument();
      expect(screen.getByText('2号包装机')).toBeInTheDocument();
    });
  });

  it('加载中展示加载状态', () => {
    mockListEquipment.mockReturnValue(new Promise(() => {}));
    render(<EquipmentList />);
    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('空数据展示空状态', async () => {
    mockListEquipment.mockResolvedValue({ items: [], total: 0 });
    render(<EquipmentList />);
    await waitFor(() => {
      expect(screen.getByText('无设备')).toBeInTheDocument();
    });
  });

  it('API 失败时展示错误 toast', async () => {
    mockListEquipment.mockRejectedValue(new Error('网络错误'));
    render(<EquipmentList />);
    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.error).toHaveBeenCalledWith('网络错误');
    });
  });

  it('展示设备状态标签', async () => {
    render(<EquipmentList />);
    await waitFor(() => {
      expect(screen.getByText('运行中')).toBeInTheDocument();
      expect(screen.getByText('故障')).toBeInTheDocument();
      expect(screen.getByText('维修中')).toBeInTheDocument();
    });
  });

  it('展示设备编号、地点和制造商信息', async () => {
    render(<EquipmentList />);
    await waitFor(() => {
      expect(screen.getByText('CNC-03')).toBeInTheDocument();
      expect(screen.getByText('位置: A车间')).toBeInTheDocument();
      expect(screen.getByText('制造商: Fanuc α-D14MiB5')).toBeInTheDocument();
    });
  });

  it('搜索功能', async () => {
    const user = userEvent.setup();
    render(<EquipmentList />);
    await waitFor(() => screen.getByText('3号CNC'));

    const searchInput = screen.getByPlaceholderText('搜索设备编号或名称...');
    await user.type(searchInput, 'CNC');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(mockListEquipment).toHaveBeenCalledWith(
        expect.objectContaining({ keyword: 'CNC' })
      );
    });
  });

  it('设备类型筛选', async () => {
    const user = userEvent.setup();
    render(<EquipmentList />);
    await waitFor(() => screen.getByText('3号CNC'));

    const typeSelect = screen.getByDisplayValue('全部类型');
    await user.selectOptions(typeSelect, '1');

    await waitFor(() => {
      expect(mockListEquipment).toHaveBeenCalledWith(
        expect.objectContaining({ equipment_type_id: '1' })
      );
    });
  });

  it('状态筛选', async () => {
    const user = userEvent.setup();
    render(<EquipmentList />);
    await waitFor(() => screen.getByText('3号CNC'));

    const statusSelect = screen.getByDisplayValue('全部状态');
    await user.selectOptions(statusSelect, 'fault');

    await waitFor(() => {
      expect(mockListEquipment).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'fault' })
      );
    });
  });

  it('点击设备卡片跳转详情', async () => {
    const user = userEvent.setup();
    render(<EquipmentList />);
    await waitFor(() => screen.getByText('3号CNC'));
    await user.click(screen.getByText('3号CNC'));
    expect(mockPush).toHaveBeenCalledWith('/equipment/1');
  });

  it('加载设备类型列表', async () => {
    render(<EquipmentList />);
    await waitFor(() => {
      expect(mockListEquipmentTypes).toHaveBeenCalled();
    });
  });
});
