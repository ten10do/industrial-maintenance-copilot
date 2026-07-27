import { User, WorkOrderStatus, Priority, Role, ApiError, ConvertToWorkOrderRequest, ConvertToWorkOrderResponse } from './types';

const BASE = '/api/v1';

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts.headers as Record<string, string> || {}),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    if (body && typeof body === 'object' && body.detail) {
      const detail = body.detail;
      if (typeof detail === 'object') {
        throw new ApiError(res.status, detail);
      }
      throw new ApiError(res.status, detail as string);
    }
    throw new ApiError(res.status, `HTTP ${res.status}`);
  }
  return res.json();
}

// Auth
export async function login(email: string, password: string) {
  return request<{ access_token: string; role: string; user_id: number; full_name: string }>('/auth/login', {
    method: 'POST', body: JSON.stringify({ email, password }),
  });
}
export async function getMe() { return request<User>('/auth/me'); }

// Users / Technicians
export async function listUsers(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return request<{ items: any[]; total: number }>(`/users${qs}`);
}
export async function listTechnicians() { return request<any[]>('/users/technicians'); }

// Equipment
export async function listEquipment(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return request<{ items: any[]; total: number }>(`/equipment${qs}`);
}
export async function getEquipment(id: number) { return request<any>(`/equipment/${id}`); }
export async function createEquipment(data: any) { return request<any>('/equipment', { method: 'POST', body: JSON.stringify(data) }); }
export async function updateEquipment(id: number, data: any) {
  return request<any>(`/equipment/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}
export async function getEquipmentWorkOrders(id: number) { return request<any[]>(`/equipment/${id}/work-orders`); }
export async function listEquipmentTypes() { return request<any[]>('/equipment-types'); }
export async function listFaultCodes() { return request<any[]>('/fault-codes'); }
export async function listSpareParts() { return request<any[]>('/spare-parts'); }

// Fault Reports
export async function listFaultReports(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return request<{ items: any[]; total: number }>(`/fault-reports${qs}`);
}
export async function getFaultReport(id: number) { return request<any>(`/fault-reports/${id}`); }
export async function createFaultReport(data: any) { return request<any>('/fault-reports', { method: 'POST', body: JSON.stringify(data) }); }
export async function parseFaultText(text: string) { return request<any>('/fault-reports/parse', { method: 'POST', body: JSON.stringify({ text }) }); }
export async function convertFaultReportToWorkOrder(frId: number, data?: ConvertToWorkOrderRequest) {
  return request<ConvertToWorkOrderResponse>(`/fault-reports/${frId}/convert-to-work-order`, {
    method: 'POST', body: JSON.stringify(data || {}),
  });
}

// Work Orders
export async function listWorkOrders(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return request<{ items: any[]; total: number }>(`/work-orders${qs}`);
}
export async function getWorkOrder(id: number) { return request<any>(`/work-orders/${id}`); }
export async function createWorkOrder(data: any) { return request<any>('/work-orders', { method: 'POST', body: JSON.stringify(data) }); }
export async function updateWorkOrder(id: number, data: any) {
  return request<any>(`/work-orders/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}
export async function assignWorkOrder(id: number, data: { assignee_id: number; priority?: string; planned_end_at?: string }) {
  return request<any>(`/work-orders/${id}/assign`, { method: 'POST', body: JSON.stringify(data) });
}
export async function acceptWorkOrder(id: number) { return request<any>(`/work-orders/${id}/accept`, { method: 'POST' }); }
export async function startWorkOrder(id: number) { return request<any>(`/work-orders/${id}/start`, { method: 'POST' }); }
export async function pauseWorkOrder(id: number) { return request<any>(`/work-orders/${id}/pause`, { method: 'POST' }); }
export async function resumeWorkOrder(id: number) { return request<any>(`/work-orders/${id}/resume`, { method: 'POST' }); }
export async function submitWorkOrder(id: number, data: any) {
  return request<any>(`/work-orders/${id}/submit`, { method: 'POST', body: JSON.stringify(data) });
}
export async function approveWorkOrder(id: number) { return request<any>(`/work-orders/${id}/approve`, { method: 'POST' }); }
export async function rejectWorkOrder(id: number, remark: string) {
  return request<any>(`/work-orders/${id}/reject`, { method: 'POST', body: JSON.stringify({ remark }) });
}
export async function cancelWorkOrder(id: number) { return request<any>(`/work-orders/${id}/cancel`, { method: 'POST' }); }
export async function updateChecklistItem(woId: number, itemId: number, data: any) {
  return request<any>(`/work-orders/${woId}/checklist/${itemId}`, { method: 'PUT', body: JSON.stringify(data) });
}
export async function addMaintenanceLog(woId: number, data: any) {
  return request<any>(`/work-orders/${woId}/logs`, { method: 'POST', body: JSON.stringify(data) });
}
export async function addLaborEntry(woId: number, data: any) {
  return request<any>(`/work-orders/${woId}/labor`, { method: 'POST', body: JSON.stringify(data) });
}
export async function addSparePartUsage(woId: number, data: any) {
  return request<any>(`/work-orders/${woId}/spare-parts`, { method: 'POST', body: JSON.stringify(data) });
}

// Copilot
export async function copilotDiagnose(data: { work_order_id?: number; fault_description: string; equipment_id?: number; fault_code?: string }) {
  return request<any>('/copilot/diagnose', { method: 'POST', body: JSON.stringify(data) });
}
export async function copilotRewriteLog(content: string) {
  return request<any>('/copilot/rewrite-maintenance-log', { method: 'POST', body: JSON.stringify({ content }) });
}
export async function copilotGenerateReport(workOrderId: number) {
  return request<any>('/copilot/generate-report', { method: 'POST', body: JSON.stringify({ work_order_id: workOrderId }) });
}
export async function copilotAsk(question: string, equipmentTypeId?: number, faultCode?: string) {
  return request<any>('/copilot/ask', { method: 'POST', body: JSON.stringify({ question, equipment_type_id: equipmentTypeId, fault_code: faultCode }) });
}
export async function copilotEquipmentHistory(equipmentId: number) {
  return request<any>(`/copilot/equipment-history/${equipmentId}`);
}

// Knowledge
export async function listKnowledge(params?: Record<string, string>) {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  return request<{ items: any[]; total: number }>(`/knowledge${qs}`);
}
export async function searchKnowledge(q: string, faultCode?: string, equipmentTypeId?: number) {
  const params = new URLSearchParams({ q });
  if (faultCode) params.set('fault_code', faultCode);
  if (equipmentTypeId) params.set('equipment_type_id', String(equipmentTypeId));
  return request<any[]>(`/knowledge/search?${params.toString()}`);
}

// Dashboard
export async function getSupervisorDashboard() { return request<any>('/dashboard/supervisor'); }
export async function getTechnicianDashboard() { return request<any>('/dashboard/technician'); }
