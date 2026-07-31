import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkOrderDetail from '@/app/work-orders/[id]/page';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: mockPush })),
  useParams: jest.fn(() => ({ id: '1' })),
}));

const mockGetWorkOrder = jest.fn();
const mockAcceptWorkOrder = jest.fn();
const mockStartWorkOrder = jest.fn();
const mockPauseWorkOrder = jest.fn();
const mockResumeWorkOrder = jest.fn();
const mockSubmitWorkOrder = jest.fn();
const mockApproveWorkOrder = jest.fn();
const mockRejectWorkOrder = jest.fn();
const mockCancelWorkOrder = jest.fn();
const mockUpdateChecklistItem = jest.fn();
const mockAddMaintenanceLog = jest.fn();
const mockAddLaborEntry = jest.fn();
const mockAddSparePartUsage = jest.fn();
const mockCopilotDiagnose = jest.fn();
const mockCopilotRewriteLog = jest.fn();
const mockGetWorkOrderReport = jest.fn();
const mockRegenerateWorkOrderReport = jest.fn();
const mockAddAttachment = jest.fn();

jest.mock('@/lib/api', () => ({
  getWorkOrder: (...args: unknown[]) => mockGetWorkOrder(...args),
  acceptWorkOrder: (...args: unknown[]) => mockAcceptWorkOrder(...args),
  startWorkOrder: (...args: unknown[]) => mockStartWorkOrder(...args),
  pauseWorkOrder: (...args: unknown[]) => mockPauseWorkOrder(...args),
  resumeWorkOrder: (...args: unknown[]) => mockResumeWorkOrder(...args),
  submitWorkOrder: (...args: unknown[]) => mockSubmitWorkOrder(...args),
  approveWorkOrder: (...args: unknown[]) => mockApproveWorkOrder(...args),
  rejectWorkOrder: (...args: unknown[]) => mockRejectWorkOrder(...args),
  cancelWorkOrder: (...args: unknown[]) => mockCancelWorkOrder(...args),
  updateChecklistItem: (...args: unknown[]) => mockUpdateChecklistItem(...args),
  addMaintenanceLog: (...args: unknown[]) => mockAddMaintenanceLog(...args),
  addLaborEntry: (...args: unknown[]) => mockAddLaborEntry(...args),
  addSparePartUsage: (...args: unknown[]) => mockAddSparePartUsage(...args),
  copilotDiagnose: (...args: unknown[]) => mockCopilotDiagnose(...args),
  copilotRewriteLog: (...args: unknown[]) => mockCopilotRewriteLog(...args),
  getWorkOrderReport: (...args: unknown[]) => mockGetWorkOrderReport(...args),
  regenerateWorkOrderReport: (...args: unknown[]) => mockRegenerateWorkOrderReport(...args),
  addAttachment: (...args: unknown[]) => mockAddAttachment(...args),
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

const assignedWo = {
  id: 1,
  title: 'CNC主轴异响',
  code: 'WO-001',
  equipment_name: 'CNC-03',
  equipment_id: 1,
  priority: 'P1',
  status: 'assigned',
  order_type: 'fault_repair',
  fault_description: '主轴运转时有异常噪音',
  fault_code: 'E101',
  assignee_id: 3,
  assignee_name: '工程师',
  planned_end_at: '2026-08-01T00:00:00',
  safety_risk: null,
  checklist_items: [
    { id: 1, content: '检查主轴轴承', is_completed: false, is_required: true, remark: null },
    { id: 2, content: '检查润滑系统', is_completed: false, is_required: false, remark: null },
  ],
  logs: [],
  labor_entries: [],
  spare_parts: [],
  status_history: [
    { changed_at: '2026-07-27T08:00:00', from_status: null, to_status: 'pending_dispatch' },
    { changed_at: '2026-07-27T09:00:00', from_status: 'pending_dispatch', to_status: 'assigned' },
  ],
};

const inProgressWo = {
  ...assignedWo,
  status: 'in_progress',
  assignee_id: 3,
  logs: [
    { id: 1, log_type: 'diagnose', content: '确认主轴轴承磨损', operator_name: '工程师', logged_at: '2026-07-27T10:00:00.000' },
  ],
  labor_entries: [{ id: 1, hours: 2, operator_name: '工程师' }],
  spare_parts: [{ id: 1, spare_part_name: '轴承', quantity: 2, unit: '个' }],
};

const pendingAcceptanceWo = {
  ...inProgressWo,
  status: 'pending_acceptance',
  assignee_id: 3,
  root_cause: '轴承疲劳磨损',
  action_taken: '更换主轴轴承',
  test_result: '精度恢复正常',
  replaced_parts: '主轴轴承 6205',
  follow_up_advice: '一个月后复查',
  needs_observation: true,
};

const completedWo = {
  ...pendingAcceptanceWo,
  status: 'completed',
};

const mockReport = {
  work_order_id: 1,
  work_order_code: 'WO-001',
  summary: 'CNC主轴异响故障已通过更换主轴轴承完成维修，测试结果正常。',
  sections: [
    { title: '故障原因', content: '轴承疲劳磨损导致主轴运转时产生异常噪音。' },
    { title: '维修措施', content: '更换主轴轴承（型号6205），重新校准主轴精度。' },
    { title: '测试结果', content: '空载及负载测试均正常，精度恢复至出厂标准。' },
    { title: '后续建议', content: '建议一个月后复查主轴精度。' },
  ],
  generation_method: 'template',
  version: 1,
  is_mock: false,
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('WorkOrderDetail', () => {
  describe('Loading & Error States', () => {
    it('加载中展示加载状态', () => {
      mockGetWorkOrder.mockReturnValue(new Promise(() => {}));
      mockUseAuth.mockReturnValue({
        user: { role: 'supervisor', id: 1, full_name: '主管', email: 's@t.com', is_active: true },
      });
      render(<WorkOrderDetail />);
      expect(screen.getByText('加载中...')).toBeInTheDocument();
    });

    it('工单不存在时展示提示', async () => {
      mockGetWorkOrder.mockResolvedValue(null);
      mockUseAuth.mockReturnValue({
        user: { role: 'supervisor', id: 1, full_name: '主管', email: 's@t.com', is_active: true },
      });
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('工单不存在')).toBeInTheDocument();
      });
    });

    it('获取失败时展示错误 toast', async () => {
      mockGetWorkOrder.mockRejectedValue(new Error('网络错误'));
      mockUseAuth.mockReturnValue({
        user: { role: 'supervisor', id: 1, full_name: '主管', email: 's@t.com', is_active: true },
      });
      render(<WorkOrderDetail />);
      await waitFor(() => {
        const toast = require('react-hot-toast').default;
        expect(toast.error).toHaveBeenCalledWith('网络错误');
      });
    });
  });

  describe('Basic Display', () => {
    beforeEach(() => {
      mockGetWorkOrder.mockResolvedValue(assignedWo);
      mockUseAuth.mockReturnValue({
        user: { role: 'supervisor', id: 1, full_name: '主管', email: 's@t.com', is_active: true },
      });
    });

    it('展示工单标题和编号', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('CNC主轴异响')).toBeInTheDocument();
        expect(screen.getByText('WO-001', { exact: false })).toBeInTheDocument();
      });
    });

    it('展示状态和优先级标签', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('已分派')).toBeInTheDocument();
        const priorityBadges = screen.getAllByText('P1 紧急');
        expect(priorityBadges.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('展示基本信息区域', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('基本信息')).toBeInTheDocument();
        expect(screen.getByText('故障维修')).toBeInTheDocument();
        expect(screen.getByText('工程师')).toBeInTheDocument();
      });
    });

    it('展示安全检查清单', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('维修检查清单')).toBeInTheDocument();
        expect(screen.getByText('检查主轴轴承')).toBeInTheDocument();
        // 必填项用 * 标记
        const checklistItem = screen.getByTestId('checklist-item-1');
        expect(checklistItem).toBeInTheDocument();
        expect(checklistItem.querySelector('.text-red-400')).toBeInTheDocument();
      });
    });

    it('展示状态历史', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('状态历史')).toBeInTheDocument();
      });
    });

    it('AI 诊断面板存在', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('AI 诊断建议')).toBeInTheDocument();
      });
    });
  });

  describe('Action Buttons - Assigned State', () => {
    beforeEach(() => {
      mockGetWorkOrder.mockResolvedValue(assignedWo);
      mockUseAuth.mockReturnValue({
        user: { role: 'technician', id: 3, full_name: '工程师', email: 't@t.com', is_active: true },
      });
    });

    it('负责人看到接受工单按钮', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('接受工单')).toBeInTheDocument();
      });
    });

    it('接受工单成功', async () => {
      mockAcceptWorkOrder.mockResolvedValue({});
      mockGetWorkOrder.mockResolvedValueOnce(assignedWo).mockResolvedValueOnce({ ...assignedWo, status: 'accepted' });
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('接受工单'));
      await user.click(screen.getByText('接受工单'));
      await waitFor(() => {
        expect(mockAcceptWorkOrder).toHaveBeenCalledWith(1);
      });
    });

    it('管理员/主管看不到接受按钮（非负责人）', async () => {
      mockUseAuth.mockReturnValue({
        user: { role: 'supervisor', id: 1, full_name: '主管', email: 's@t.com', is_active: true },
      });
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('CNC主轴异响'));
      expect(screen.queryByText('接受工单')).not.toBeInTheDocument();
    });
  });

  describe('Action Buttons - In Progress State', () => {
    beforeEach(() => {
      mockGetWorkOrder.mockResolvedValue(inProgressWo);
      mockUseAuth.mockReturnValue({
        user: { role: 'technician', id: 3, full_name: '工程师', email: 't@t.com', is_active: true },
      });
    });

    it('负责人看到暂停和提交完工按钮', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('暂停')).toBeInTheDocument();
        expect(screen.getAllByText('提交完工').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('暂停工单', async () => {
      mockPauseWorkOrder.mockResolvedValue({});
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('暂停'));
      await user.click(screen.getByText('暂停'));
      await waitFor(() => {
        expect(mockPauseWorkOrder).toHaveBeenCalledWith(1);
      });
    });

    it('展示完工信息表单', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('完工信息')).toBeInTheDocument();
        expect(screen.getByText('根本原因 *')).toBeInTheDocument();
        expect(screen.getByText('处理措施 *')).toBeInTheDocument();
        expect(screen.getByText('测试结果 *')).toBeInTheDocument();
      });
    });

    it('未填写必填项时 toast 错误', async () => {
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByTestId('submit-completion-button'));
      await user.click(screen.getByTestId('submit-completion-button'));
      await waitFor(() => {
        const toast = require('react-hot-toast').default;
        expect(toast.error).toHaveBeenCalledWith('请填写根本原因、处理措施和测试结果');
      });
    });

    it('无维修记录时提交被阻止', async () => {
      mockGetWorkOrder.mockResolvedValue({ ...inProgressWo, logs: [] });
      // 后端校验：无维修记录返回 422，missing_requirements 使用后端编码
      const validationError: any = new Error('工单尚未满足完工条件');
      validationError.status = 422;
      validationError.response = { data: { missing_requirements: ['maintenance_log'] } };
      mockSubmitWorkOrder.mockRejectedValue(validationError);
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByTestId('submit-completion-button'));

      const rootCauseInput = screen.getByPlaceholderText('故障的根本原因');
      await user.type(rootCauseInput, '轴承磨损');
      const actionInput = screen.getByPlaceholderText('采取的处理措施');
      await user.type(actionInput, '更换轴承');
      const testInput = screen.getByPlaceholderText('测试结果');
      await user.type(testInput, '正常');

      await user.click(screen.getByTestId('submit-completion-button'));
      await waitFor(() => {
        // 完工校验错误：missing_requirements 映射为中文提示
        expect(screen.getByText('至少需要一条维修过程记录')).toBeInTheDocument();
      });
    });

    it('填写完整后提交成功', async () => {
      mockSubmitWorkOrder.mockResolvedValue({});
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByTestId('submit-completion-button'));

      await user.type(screen.getByPlaceholderText('故障的根本原因'), '轴承磨损');
      await user.type(screen.getByPlaceholderText('采取的处理措施'), '更换轴承');
      await user.type(screen.getByPlaceholderText('测试结果'), '正常');
      await user.click(screen.getByTestId('submit-completion-button'));

      await waitFor(() => {
        expect(mockSubmitWorkOrder).toHaveBeenCalledWith(1, expect.objectContaining({
          root_cause: '轴承磨损',
          action_taken: '更换轴承',
          test_result: '正常',
        }));
      });
    });
  });

  describe('Maintenance Log', () => {
    beforeEach(() => {
      mockGetWorkOrder.mockResolvedValue(inProgressWo);
      mockUseAuth.mockReturnValue({
        user: { role: 'technician', id: 3, full_name: '工程师', email: 't@t.com', is_active: true },
      });
    });

    it('展示已有维修记录', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('维修过程记录')).toBeInTheDocument();
        expect(screen.getByText('确认主轴轴承磨损')).toBeInTheDocument();
      });
    });

    it('添加维修记录', async () => {
      mockAddMaintenanceLog.mockResolvedValue({});
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('维修过程记录'));

      const textarea = screen.getByPlaceholderText('记录维修过程...');
      await user.type(textarea, '更换完成');
      await user.click(screen.getByText('添加记录'));

      await waitFor(() => {
        expect(mockAddMaintenanceLog).toHaveBeenCalledWith(1, expect.objectContaining({
          content: '更换完成',
          log_type: 'note',
        }));
      });
    });

    it('空内容添加时 toast 错误', async () => {
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('添加记录'));
      await user.click(screen.getByText('添加记录'));
      await waitFor(() => {
        const toast = require('react-hot-toast').default;
        expect(toast.error).toHaveBeenCalledWith('请输入内容');
      });
    });
  });

  describe('Labor & Spare Parts', () => {
    beforeEach(() => {
      mockGetWorkOrder.mockResolvedValue(inProgressWo);
      mockUseAuth.mockReturnValue({
        user: { role: 'technician', id: 3, full_name: '工程师', email: 't@t.com', is_active: true },
      });
    });

    it('展示工时记录', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('工时记录')).toBeInTheDocument();
      });
    });

    it('记录工时', async () => {
      mockAddLaborEntry.mockResolvedValue({});
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('工时记录'));

      const hourInput = screen.getByPlaceholderText('工时(小时)');
      await user.type(hourInput, '1.5');
      await user.click(screen.getByText('记录工时'));

      await waitFor(() => {
        expect(mockAddLaborEntry).toHaveBeenCalledWith(1, expect.objectContaining({ hours: 1.5 }));
      });
    });

    it('空工时 toast 错误', async () => {
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('记录工时'));
      await user.click(screen.getByText('记录工时'));
      await waitFor(() => {
        const toast = require('react-hot-toast').default;
        expect(toast.error).toHaveBeenCalledWith('请输入有效工时');
      });
    });

    it('添加备件', async () => {
      mockAddSparePartUsage.mockResolvedValue({});
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('备件使用'));

      await user.type(screen.getByPlaceholderText('备件名称'), '密封圈');
      await user.click(screen.getByText('添加备件'));

      await waitFor(() => {
        expect(mockAddSparePartUsage).toHaveBeenCalledWith(1, expect.objectContaining({
          spare_part_name: '密封圈',
        }));
      });
    });
  });

  describe('AI Diagnosis', () => {
    beforeEach(() => {
      mockGetWorkOrder.mockResolvedValue(assignedWo);
      mockUseAuth.mockReturnValue({
        user: { role: 'technician', id: 3, full_name: '工程师', email: 't@t.com', is_active: true },
      });
    });

    it('获取 AI 诊断建议', async () => {
      mockCopilotDiagnose.mockResolvedValue({
        possible_causes: [{ cause: '轴承磨损', confidence: 0.85 }],
        inspection_order: ['检查主轴轴承'],
        safety_notes: ['停机操作'],
        similar_cases: [{ work_order_id: 5, code: 'WO-005', title: '主轴维修', similarity: 0.72 }],
        disclaimer: 'AI建议仅供参考',
      });
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('获取建议'));
      await user.click(screen.getByText('获取建议'));

      await waitFor(() => {
        expect(screen.getByText('可能原因')).toBeInTheDocument();
        expect(screen.getByText('轴承磨损')).toBeInTheDocument();
        expect(screen.getByText('建议排查顺序')).toBeInTheDocument();
      });
    });

    it('AI 诊断加载中', async () => {
      mockCopilotDiagnose.mockReturnValue(new Promise(() => {}));
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('获取建议'));
      await user.click(screen.getByText('获取建议'));

      await waitFor(() => {
        expect(screen.getByText('分析中...')).toBeInTheDocument();
      });
    });
  });

  describe('Approval Flow', () => {
    beforeEach(() => {
      mockGetWorkOrder.mockResolvedValue(pendingAcceptanceWo);
      mockUseAuth.mockReturnValue({
        user: { role: 'supervisor', id: 2, full_name: '主管', email: 's@t.com', is_active: true },
      });
    });

    it('主管看到验收区域', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('主管验收')).toBeInTheDocument();
        const approveBtns = screen.getAllByText('验收通过');
        expect(approveBtns.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('展示完工信息', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('轴承疲劳磨损')).toBeInTheDocument();
        expect(screen.getByText('更换主轴轴承')).toBeInTheDocument();
      });
    });

    it('验收通过', async () => {
      mockApproveWorkOrder.mockResolvedValue({});
      const user = userEvent.setup();
      render(<WorkOrderDetail />);
      await waitFor(() => { const btns = screen.getAllByText('验收通过'); expect(btns.length).toBeGreaterThanOrEqual(1); });
      const approveBtns = screen.getAllByText('验收通过');
      await user.click(approveBtns[0]);
      await waitFor(() => {
        expect(mockApproveWorkOrder).toHaveBeenCalledWith(1);
      });
    });
  });

  describe('Completed State', () => {
    beforeEach(() => {
      mockGetWorkOrder.mockResolvedValue(completedWo);
      mockGetWorkOrderReport.mockResolvedValue(mockReport);
      mockUseAuth.mockReturnValue({
        user: { role: 'supervisor', id: 2, full_name: '主管', email: 's@t.com', is_active: true },
      });
    });

    it('展示维修报告', async () => {
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('维修报告')).toBeInTheDocument();
      });
      // 验证报告内容
      expect(screen.getByText('摘要')).toBeInTheDocument();
      expect(screen.getByText('CNC主轴异响故障已通过更换主轴轴承完成维修，测试结果正常。')).toBeInTheDocument();
      // 生成方式和版本在同一 <p> 内，用 substring 匹配
      expect(screen.getByText('模板生成', { exact: false })).toBeInTheDocument();
      expect(screen.getByText('故障原因')).toBeInTheDocument();
      expect(screen.getByText('维修措施')).toBeInTheDocument();
      expect(screen.getByText('测试结果')).toBeInTheDocument();
      expect(screen.getByText('后续建议')).toBeInTheDocument();
    });

    it('报告加载失败时展示错误并允许重试', async () => {
      mockGetWorkOrderReport.mockRejectedValue(new Error('报告生成失败'));
      render(<WorkOrderDetail />);
      await waitFor(() => {
        expect(screen.getByText('报告生成失败')).toBeInTheDocument();
        expect(screen.getByText('重试')).toBeInTheDocument();
      });
      // 工单主体应不受影响
      expect(screen.getByText('CNC主轴异响')).toBeInTheDocument();
    });
  });

  describe('Safety Risk Display', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { role: 'supervisor', id: 1, full_name: '主管', email: 's@t.com', is_active: true },
      });
    });

    it('有安全风险时展示警告', async () => {
      mockGetWorkOrder.mockResolvedValue({ ...assignedWo, safety_risk: '高温烫伤风险' });
      render(<WorkOrderDetail />);
      await waitFor(() => {
        const riskWarning = screen.getByTestId('safety-risk-warning');
        expect(riskWarning).toBeInTheDocument();
        expect(screen.getByText('安全风险')).toBeInTheDocument();
        expect(screen.getByText('高温烫伤风险')).toBeInTheDocument();
      });
    });

    it('无安全风险时不展示', async () => {
      mockGetWorkOrder.mockResolvedValue(assignedWo);
      render(<WorkOrderDetail />);
      await waitFor(() => screen.getByText('CNC主轴异响'));
      expect(screen.queryByText(/安全风险:/)).not.toBeInTheDocument();
    });
  });
});
