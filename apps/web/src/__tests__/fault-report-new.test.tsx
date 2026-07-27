import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NewFaultReport from '@/app/fault-reports/new/page';

const mockPush = jest.fn();
const mockBack = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush, back: mockBack })),
}));

const mockParseFaultText = jest.fn();
const mockCreateFaultReport = jest.fn();
const mockConvertFaultReportToWorkOrder = jest.fn();
const mockListEquipment = jest.fn();
const mockListFaultCodes = jest.fn();
jest.mock('@/lib/api', () => ({
  parseFaultText: (...args: unknown[]) => mockParseFaultText(...args),
  createFaultReport: (...args: unknown[]) => mockCreateFaultReport(...args),
  convertFaultReportToWorkOrder: (...args: unknown[]) => mockConvertFaultReportToWorkOrder(...args),
  listEquipment: (...args: unknown[]) => mockListEquipment(...args),
  listFaultCodes: (...args: unknown[]) => mockListFaultCodes(...args),
}));

jest.mock('react-hot-toast', () => ({
  __esModule: true,
  default: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const mockEquipment = [
  { id: 1, code: 'CNC-03', name: '3号CNC', status: 'running', plant: 'A车间' },
  { id: 2, code: 'CNC-04', name: '4号CNC', status: 'fault', plant: 'B车间' },
];

const mockFaultCodes = [
  { id: 101, code: 'E101', description: '主轴故障' },
  { id: 103, code: 'E103', description: '接近开关异常' },
];

beforeEach(() => {
  jest.clearAllMocks();
  mockListEquipment.mockResolvedValue({ items: mockEquipment });
  mockListFaultCodes.mockResolvedValue(mockFaultCodes);
});

describe('NewFaultReport', () => {
  it('手动填写并提交故障上报', async () => {
    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    render(<NewFaultReport />);

    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    const titleInput = screen.getByPlaceholderText('简要描述故障');
    await user.type(titleInput, 'CNC主轴异响');
    const descInput = screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等');
    await user.type(descInput, '加工精度偏差0.05mm');

    const submitBtn = screen.getByText('提交上报');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(mockCreateFaultReport).toHaveBeenCalled();
      const payload = mockCreateFaultReport.mock.calls[0][0];
      expect(payload.title).toBe('CNC主轴异响');
      expect(payload.description).toBe('加工精度偏差0.05mm');
      expect(payload.urgency).toBe('medium');
    });

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/fault-reports/1');
    });
  });

  it('AI 解析成功后填充字段', async () => {
    mockParseFaultText.mockResolvedValue({
      title: '接近开关信号异常',
      description: '3号包装机接近开关无信号输出',
      phenomenon: '信号丢失',
      urgency: 'high',
      equipment_id: 1,
      fault_code: 'E103',
      is_downtime: true,
      affects_production: true,
      has_safety_risk: false,
      confidence: 0.85,
    });
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('AI 智能解析')).toBeInTheDocument());

    const textarea = screen.getByPlaceholderText(/CNC-03主轴异响/);
    await user.type(textarea, '3号包装机接近开关信号异常');
    await user.click(screen.getByText('AI 解析'));

    await waitFor(() => {
      expect(screen.getByText('解析完成')).toBeInTheDocument();
      expect(screen.getByText(/85%/)).toBeInTheDocument();
    });

    expect(mockParseFaultText).toHaveBeenCalledWith('3号包装机接近开关信号异常');
  });

  it('AI 解析失败后仍可手动填写', async () => {
    mockParseFaultText.mockRejectedValue(new Error('AI 服务不可用'));
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('AI 智能解析')).toBeInTheDocument());

    const textarea = screen.getByPlaceholderText(/CNC-03主轴异响/);
    await user.type(textarea, '测试描述');
    await user.click(screen.getByText('AI 解析'));

    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.error).toHaveBeenCalledWith('AI 服务不可用');
    });

    // Form should still be usable
    expect(screen.getByPlaceholderText('简要描述故障')).toBeInTheDocument();
  });

  it('解析结果展示置信度', async () => {
    mockParseFaultText.mockResolvedValue({
      title: '测试',
      description: '测试描述',
      urgency: 'low',
      confidence: 0.45,
    });
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('AI 智能解析')).toBeInTheDocument());
    await user.type(screen.getByPlaceholderText(/CNC-03主轴异响/), 'test');
    await user.click(screen.getByText('AI 解析'));

    await waitFor(() => {
      expect(screen.getByText('解析完成')).toBeInTheDocument();
      expect(screen.getByText(/45%/)).toBeInTheDocument();
    });
  });

  it('设备搜索结果正常展示', async () => {
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    const equipInput = screen.getByPlaceholderText('搜索设备名称或编号...');
    await user.type(equipInput, 'CNC');

    await waitFor(() => {
      expect(screen.getByText('CNC-03 - 3号CNC')).toBeInTheDocument();
      expect(screen.getByText('CNC-04 - 4号CNC')).toBeInTheDocument();
    });
  });

  it('点击设备搜索结果选择设备', async () => {
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    const equipInput = screen.getByPlaceholderText('搜索设备名称或编号...');
    await user.type(equipInput, 'CNC-03');
    await waitFor(() => screen.getByText('CNC-03 - 3号CNC'));
    await user.click(screen.getByText('CNC-03 - 3号CNC'));

    await waitFor(() => {
      expect(equipInput).toHaveValue('CNC-03 3号CNC');
    });
  });

  it('故障代码字符串正确映射', async () => {
    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试标题');
    await user.type(screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等'), '测试描述');
    await user.type(screen.getByPlaceholderText('如：E103'), 'E103');
    await user.click(screen.getByText('提交上报'));

    await waitFor(() => {
      const payload = mockCreateFaultReport.mock.calls[0][0];
      expect(payload.fault_code_id).toBe(103);
    });
  });

  it('必填字段缺失时阻止提交', async () => {
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    const submitBtn = screen.getByText('提交上报');
    expect(submitBtn).toBeDisabled();

    // Only fill title, not description
    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试');
    expect(submitBtn).toBeDisabled();
  });

  it('提交期间禁用提交按钮', async () => {
    mockCreateFaultReport.mockReturnValue(new Promise(() => {})); // never resolves
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试标题');
    await user.type(screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等'), '测试描述');
    await user.click(screen.getByText('提交上报'));

    await waitFor(() => {
      expect(screen.getByText('提交中...')).toBeInTheDocument();
    });
  });

  it('未勾选同时创建工单时只创建故障上报', async () => {
    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试标题');
    await user.type(screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等'), '测试描述');
    await user.click(screen.getByText('提交上报'));

    await waitFor(() => {
      expect(mockCreateFaultReport).toHaveBeenCalled();
      expect(mockConvertFaultReportToWorkOrder).not.toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith('/fault-reports/1');
    });
  });

  it('勾选时创建故障上报后调用转换接口', async () => {
    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    mockConvertFaultReportToWorkOrder.mockResolvedValue({
      work_order_id: 10,
      fault_report_id: 1,
      work_order_code: 'WO-2026-0010',
      priority: 'P2',
      status: 'pending_dispatch',
    });
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试标题');
    await user.type(screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等'), '测试描述');

    const checkbox = screen.getByRole('checkbox');
    await user.click(checkbox);

    await user.click(screen.getByText('上报并创建工单'));

    await waitFor(() => {
      expect(mockCreateFaultReport).toHaveBeenCalled();
      expect(mockConvertFaultReportToWorkOrder).toHaveBeenCalledWith(1);
      expect(mockPush).toHaveBeenCalledWith('/work-orders/10');
    });
  });

  it('转换成功时显示成功提示', async () => {
    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    mockConvertFaultReportToWorkOrder.mockResolvedValue({
      work_order_id: 10, fault_report_id: 1, work_order_code: 'WO-2026-0010', priority: 'P2', status: 'pending_dispatch',
    });
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试标题');
    await user.type(screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等'), '测试描述');
    await user.click(screen.getByRole('checkbox'));

    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    await user.click(screen.getByText('上报并创建工单'));

    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.success).toHaveBeenCalledWith('故障已上报并生成工单');
    });
  });

  it('409 时跳转已有工单', async () => {
    const { ApiError } = require('@/lib/types');
    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    mockConvertFaultReportToWorkOrder.mockRejectedValue(
      new ApiError(409, { code: 'DUPLICATE', message: '已存在', work_order_id: 7 })
    );
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试标题');
    await user.type(screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等'), '测试描述');
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByText('上报并创建工单'));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/work-orders/7');
    });
  });

  it('创建成功但转换失败时展示部分成功提示', async () => {
    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    mockConvertFaultReportToWorkOrder.mockRejectedValue(new Error('服务器内部错误'));
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试标题');
    await user.type(screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等'), '测试描述');
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByText('上报并创建工单'));

    await waitFor(() => {
      const toast = require('react-hot-toast').default;
      expect(toast.error).toHaveBeenCalledWith('故障已上报，但工单创建失败，请在详情页手动创建');
    });
  });

  it('部分成功时跳转故障上报详情', async () => {
    mockCreateFaultReport.mockResolvedValue({ id: 1 });
    mockConvertFaultReportToWorkOrder.mockRejectedValue(new Error('创建工单失败'));
    const user = userEvent.setup();
    render(<NewFaultReport />);
    await waitFor(() => expect(screen.getByText('故障详情')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('简要描述故障'), '测试标题');
    await user.type(screen.getByPlaceholderText('详细描述故障情况、发生经过、已采取的临时措施等'), '测试描述');
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByText('上报并创建工单'));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/fault-reports/1');
    });
  });
});
