export type Role = 'admin' | 'supervisor' | 'technician';
export type WorkOrderStatus = 'pending_dispatch' | 'assigned' | 'accepted' | 'in_progress' | 'pending_acceptance' | 'completed' | 'cancelled' | 'returned' | 'paused';
export type Priority = 'P1' | 'P2' | 'P3' | 'P4';
export type LogType = 'inspect' | 'diagnose' | 'repair' | 'replace' | 'test' | 'note';
export type EquipmentStatus = 'running' | 'fault' | 'under_repair' | 'stopped' | 'scrapped';
export type Urgency = 'low' | 'medium' | 'high' | 'critical';
export type FaultReportStatus = 'pending' | 'converted' | 'closed';

export interface User {
  id: number; email: string; full_name: string; phone?: string; role: Role; is_active: boolean;
}

export interface AuthState {
  token: string | null; user: User | null; role: Role | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

export interface ApiErrorBody {
  code?: string;
  message?: string;
  work_order_id?: number;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  workOrderId?: number;

  constructor(status: number, body: ApiErrorBody | string) {
    const msg = typeof body === 'string' ? body : (body.message || `HTTP ${status}`);
    super(msg);
    this.name = 'ApiError';
    this.status = status;
    if (typeof body !== 'string') {
      this.code = body.code;
      this.workOrderId = body.work_order_id;
    }
  }
}

export interface ConvertToWorkOrderRequest {
  assignee_id?: number;
  priority?: Priority;
  planned_start_at?: string;
  planned_end_at?: string;
  notes?: string;
}

export interface ConvertToWorkOrderResponse {
  fault_report_id: number;
  work_order_id: number;
  work_order_code: string;
  priority: string;
  status: string;
}

export const STATUS_LABELS: Record<string, string> = {
  pending_dispatch: '待分派', assigned: '已分派', accepted: '已接受', in_progress: '处理中',
  pending_acceptance: '待验收', completed: '已完成', cancelled: '已取消', returned: '已退回', paused: '暂停',
};
export const PRIORITY_LABELS: Record<string, string> = {
  P1: 'P1 紧急', P2: 'P2 高', P3: 'P3 中', P4: 'P4 低',
};
export const LOG_TYPE_LABELS: Record<string, string> = {
  inspect: '检查', diagnose: '诊断', repair: '维修', replace: '更换', test: '测试', note: '备注',
};
export const URGENCY_LABELS: Record<string, string> = {
  low: '低', medium: '中', high: '高', critical: '紧急',
};
export const FAULT_REPORT_STATUS_LABELS: Record<string, string> = {
  pending: '待处理', converted: '已转工单', closed: '已关闭',
};
