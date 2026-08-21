export type Role = 'admin' | 'supervisor' | 'technician';
export type WorkOrderStatus = 'pending_dispatch' | 'assigned' | 'accepted' | 'in_progress' | 'pending_acceptance' | 'completed' | 'cancelled' | 'returned' | 'paused';
export type Priority = 'P1' | 'P2' | 'P3' | 'P4';
export type LogType = 'inspect' | 'diagnose' | 'repair' | 'replace' | 'test' | 'note';
export type EquipmentStatus = 'running' | 'idle' | 'warning' | 'fault' | 'maintenance' | 'offline' | 'under_repair' | 'stopped' | 'scrapped';
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
  requires_safety_confirmation?: boolean;
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

export type SimulationScenario =
  | 'normal'
  | 'temperature_rise'
  | 'vibration_spike'
  | 'current_overload'
  | 'bearing_wear'
  | 'voltage_fluctuation'
  | 'sensor_disconnect'
  | 'composite_anomaly';

export interface TelemetryRecord {
  id: number;
  equipment_id: number;
  collected_at: string;
  vibration_rms?: number;
  bearing_temperature?: number;
  motor_current?: number;
  motor_voltage?: number;
  rotational_speed?: number;
  load_ratio?: number;
  ambient_temperature?: number;
  cumulative_runtime_hours: number;
  scenario: SimulationScenario;
  quality: number;
  is_anomaly: boolean;
  anomaly_metrics?: string[];
}

export interface SimulatorStatus {
  running: boolean;
  interval_seconds: number;
  scenario: SimulationScenario;
  seed: number;
  equipment_ids: number[];
  generated_points: number;
  auto_create_work_orders: boolean;
}

export interface MLModelVersion {
  id: number;
  name: string;
  task_type: 'failure_risk' | 'fault_classification' | 'rul';
  algorithm: string;
  version: string;
  dataset_version_id: number;
  training_run_id: number;
  feature_schema_version: string;
  git_commit_sha: string;
  artifact_sha256: string;
  status: 'registered' | 'candidate' | 'staging' | 'production' | 'archived';
  is_production: boolean;
  created_at: string;
}

export interface MLFeatureContribution {
  name: string;
  contribution: number;
}

export interface MLPredictionRecord {
  id: number;
  equipment_id: number;
  model_version_id: number;
  prediction_type: 'failure_risk' | 'fault_classification' | 'rul';
  prediction: string;
  prediction_value?: number;
  probability?: number;
  confidence: number;
  prediction_horizon?: string;
  rul_hours?: number;
  degradation_index?: number;
  feature_timestamp_start: string;
  feature_timestamp_end: string;
  feature_schema_version: string;
  probabilities?: Record<string, number>;
  top_contributing_features?: MLFeatureContribution[];
  created_at: string;
}

// ============ Industrial Gateway (OPC UA, read-only) ============

export interface GatewayConnectionInfo {
  id: number;
  name: string;
  protocol: string;
  endpoint: string;
  mode: string;
  status: 'disconnected' | 'connected' | 'error';
  enabled: boolean;
  poll_interval_seconds: number;
  last_connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
}

export interface GatewayRuntimeInfo {
  mode: string;
  endpoint: string;
  connected: boolean;
  connection_status: string;
  running: boolean;
  poll_interval_seconds: number;
  auto_ingest: boolean;
  read_only: boolean;
  last_connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  totals: {
    reads_total: number;
    accepted: number;
    rejected: number;
    snapshots_ingested: number;
    snapshots_skipped: number;
    anomalies: number;
    work_orders_created: number;
  };
  last_sync: Record<string, unknown> | null;
}

export interface GatewayStatus {
  connection: GatewayConnectionInfo | null;
  runtime: GatewayRuntimeInfo;
  enabled: boolean;
  read_only: boolean;
  seed_error: string | null;
}

export interface GatewayNode {
  node_id: string;
  equipment_code: string | null;
  metric_name: string;
  unit: string;
  enabled: boolean;
  informational: boolean;
  last_value: number | boolean | string | null;
  last_quality: 'good' | 'uncertain' | 'bad' | null;
  last_timestamp: string | null;
  last_error: string | null;
}

export interface GatewayNodes {
  nodes: GatewayNode[];
  read_only: boolean;
}

export interface GatewayTestConnect {
  ok: boolean;
  endpoint: string;
  latency_ms: number;
  probe_node: string | null;
  sample_value: number | boolean | string | null;
  error: string | null;
}

export interface GatewaySyncResult {
  ok: boolean;
  error: string | null;
  reads_total: number;
  accepted: number;
  rejected: number;
  corrections: number;
  reject_reasons: Record<string, number>;
  snapshots_ingested: number;
  snapshots_skipped: number;
  anomalies: number;
  work_orders_created: number;
  telemetry_ids: number[];
  skipped_details: string[];
  duration_ms: number;
}

// ============ OPC UA DataChange Subscription ============

export interface GatewaySubscriptionRow {
  id: number;
  gateway_id: number;
  node_id: string;
  sampling_interval: number;
  status: string;
  last_event_at: string | null;
  event_count: number;
}

export interface GatewaySubscriptionStatus {
  ok: boolean;
  status: string;
  subscription_status: string;
  sampling_interval_ms: number;
  active_nodes: string[];
  buffer_pending: number;
  event_totals: Record<string, number>;
  last_event_at: string | null;
  last_event: string | null;
  error: string | null;
  read_only: boolean;
  rows: GatewaySubscriptionRow[];
}

export interface SubscriptionActionResult {
  ok: boolean;
  status: string;
  already_active?: boolean;
  error?: string | null;
}

// ============ Industrial Alarms ============

export interface IndustrialAlarm {
  id: number;
  equipment_id: number;
  severity: 'WARNING' | 'CRITICAL';
  message: string;
  source: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
  cleared_at: string | null;
  created_at: string;
}

export interface IndustrialAlarmList {
  items: IndustrialAlarm[];
  total: number;
  read_only_source: boolean;
}
