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
  missing_requirements?: string[];
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

export const KNOWLEDGE_CATEGORY_LABELS: Record<string, string> = {
  manual: '维修手册', sop: '标准作业程序', safety: '安全规程', case: '维修案例',
  fault_code: '故障代码', experience: '维护经验',
};

export const CHECKLIST_CATEGORY_LABELS: Record<string, string> = {
  safety: '安全检查',
  diagnosis: '故障诊断',
  repair: '维修执行',
  testing: '功能测试',
};

export interface Citation {
  source_type: string;
  source_id: number;
  title: string;
  excerpt?: string;
  relevance_score: number;
  url?: string;
}

export interface AskResult {
  answer: string;
  confidence: number;
  citations: Citation[];
  warnings: string[];
  is_mock: boolean;
  disclaimer: string;
}

// ---- Work Order types ----

export interface ChecklistItem {
  id: number;
  work_order_id: number;
  category: string;
  content: string;
  order: number;
  is_required: boolean;
  is_completed: boolean;
  remark?: string;
  completed_at?: string;
  completed_by?: number;
}

export interface MaintenanceLog {
  id: number;
  work_order_id: number;
  log_type: LogType;
  content: string;
  raw_content?: string;
  ai_polished?: string;
  photos?: string[];
  operator_id?: number;
  operator_name?: string;
  logged_at?: string;
  created_at?: string;
}

export interface LaborEntry {
  id: number;
  work_order_id: number;
  started_at?: string;
  ended_at?: string;
  hours: number;
  is_downtime: boolean;
  operator_id?: number;
  operator_name?: string;
  remark?: string;
}

export interface SparePartUsage {
  id: number;
  work_order_id: number;
  spare_part_id?: number;
  spare_part_code?: string;
  spare_part_name?: string;
  quantity: number;
  unit: string;
  remark?: string;
}

export interface StatusHistoryEntry {
  id: number;
  from_status?: string;
  to_status: string;
  changed_by?: number;
  changed_at?: string;
  remark?: string;
}

export interface WorkOrder {
  id: number;
  code: string;
  title: string;
  equipment_id?: number;
  equipment_name?: string;
  equipment_code?: string;
  fault_report_id?: number;
  fault_description?: string;
  fault_code_id?: number;
  fault_code?: string;
  order_type: string;
  priority: Priority;
  status: WorkOrderStatus;
  created_by_id?: number;
  creator_name?: string;
  assignee_id?: number;
  assignee_name?: string;
  planned_start_at?: string;
  planned_end_at?: string;
  actual_start_at?: string;
  actual_end_at?: string;
  safety_risk?: string;
  ai_diagnosis_summary?: string;
  maintenance_steps?: unknown[];
  acceptance_criteria?: string;
  root_cause?: string;
  action_taken?: string;
  replaced_parts?: string;
  test_result?: string;
  equipment_status_after?: string;
  follow_up_advice?: string;
  needs_observation: boolean;
  completion_photos?: string[];
  rejection_reason?: string;
  submitted_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface WorkOrderDetail extends WorkOrder {
  checklist_items: ChecklistItem[];
  logs: MaintenanceLog[];
  labor_entries: LaborEntry[];
  spare_parts: SparePartUsage[];
  status_history: StatusHistoryEntry[];
}

export interface CompletionValidationError {
  code: string;
  message: string;
  missing_requirements: string[];
}

export interface ReportSection {
  title: string;
  content: string;
}

export interface WorkOrderReport {
  work_order_id: number;
  work_order_code: string;
  summary: string;
  sections: ReportSection[];
  generation_method: string;
  version: number;
  is_mock: boolean;
}
