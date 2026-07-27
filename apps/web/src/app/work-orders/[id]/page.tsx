'use client';
import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import {
  getWorkOrder, acceptWorkOrder, startWorkOrder, pauseWorkOrder, resumeWorkOrder,
  submitWorkOrder, approveWorkOrder, rejectWorkOrder, updateChecklistItem,
  addMaintenanceLog, addLaborEntry, addSparePartUsage, copilotDiagnose,
  copilotRewriteLog, copilotGenerateReport, cancelWorkOrder
} from '@/lib/api';
import { STATUS_LABELS, PRIORITY_LABELS, LOG_TYPE_LABELS } from '@/lib/types';
import { Wrench, Clock, CheckCircle, AlertTriangle, Play, Pause, Send, XCircle, RefreshCw, Bot } from 'lucide-react';
import toast from 'react-hot-toast';

export default function WorkOrderDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const router = useRouter();
  const [wo, setWo] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [diag, setDiag] = useState<any>(null);
  const [diagLoading, setDiagLoading] = useState(false);
  // 维修记录表单
  const [newLog, setNewLog] = useState({ log_type: 'note', content: '', photos: [] as string[] });
  const [polishedText, setPolishedText] = useState('');
  // 工时
  const [laborForm, setLaborForm] = useState({ started_at: '', ended_at: '', hours: 0, is_downtime: false, remark: '' });
  // 备件
  const [spForm, setSpForm] = useState({ spare_part_name: '', quantity: 1, unit: '个', remark: '' });
  // 完工
  const [submitForm, setSubmitForm] = useState({ root_cause: '', action_taken: '', replaced_parts: '', test_result: '', equipment_status_after: 'running', follow_up_advice: '', needs_observation: false });
  // 退回原因
  const [rejectReason, setRejectReason] = useState('');

  const fetch = useCallback(async () => {
    try { const d = await getWorkOrder(Number(id)); setWo(d); } catch (e: any) { toast.error(e.message); } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { fetch(); }, [fetch]);

  const handleAction = async (action: string, data?: any) => {
    try {
      const actions: any = { accept: acceptWorkOrder, start: startWorkOrder, pause: pauseWorkOrder, resume: resumeWorkOrder, cancel: cancelWorkOrder };
      if (action === 'submit') await submitWorkOrder(Number(id), data || submitForm);
      else if (action === 'approve') await approveWorkOrder(Number(id));
      else if (action === 'reject') await rejectWorkOrder(Number(id), rejectReason || '需要修改');
      else if (actions[action]) await actions[action](Number(id));
      toast.success('操作成功');
      fetch();
    } catch (e: any) { toast.error(e.message); }
  };

  const handleChecklist = async (itemId: number, completed: boolean) => {
    try { await updateChecklistItem(Number(id), itemId, { is_completed: completed }); fetch(); } catch (e: any) { toast.error(e.message); }
  };

  const addLog = async () => {
    if (!newLog.content) return toast.error('请输入内容');
    try { await addMaintenanceLog(Number(id), { ...newLog, logged_at: new Date().toISOString() }); setNewLog({ log_type: 'note', content: '', photos: [] }); setPolishedText(''); fetch(); toast.success('记录已添加'); } catch (e: any) { toast.error(e.message); }
  };

  const addLabor = async () => {
    if (!laborForm.hours) return toast.error('请输入工时');
    try { await addLaborEntry(Number(id), laborForm); setLaborForm({ started_at: '', ended_at: '', hours: 0, is_downtime: false, remark: '' }); fetch(); toast.success('工时已记录'); } catch (e: any) { toast.error(e.message); }
  };

  const addSpare = async () => {
    if (!spForm.spare_part_name) return toast.error('请输入备件名称');
    try { await addSparePartUsage(Number(id), spForm); setSpForm({ spare_part_name: '', quantity: 1, unit: '个', remark: '' }); fetch(); toast.success('备件已记录'); } catch (e: any) { toast.error(e.message); }
  };

  const runDiagnosis = async () => {
    setDiagLoading(true);
    try {
      const result = await copilotDiagnose({ work_order_id: Number(id), fault_description: wo.fault_description || wo.title, equipment_id: wo.equipment_id, fault_code: wo.fault_code });
      setDiag(result);
    } catch (e: any) { toast.error(e.message); } finally { setDiagLoading(false); }
  };

  const runRewrite = async () => {
    if (!newLog.content) return;
    try { const r = await copilotRewriteLog(newLog.content); setPolishedText(r.polished); } catch {}
  };

  const doSubmit = () => {
    if (!submitForm.root_cause || !submitForm.action_taken || !submitForm.test_result) { toast.error('请填写根本原因、处理措施和测试结果'); return; }
    if (!wo.logs?.length) { toast.error('至少需要一条维修过程记录'); return; }
    handleAction('submit', submitForm);
  };

  const getStatusClass = (s: string) => {
    const m: any = { pending_dispatch: 'text-gray-400', assigned: 'text-blue-400', accepted: 'text-purple-400', in_progress: 'text-yellow-400', pending_acceptance: 'text-green-400', completed: 'text-green-500', returned: 'text-red-400', paused: 'text-gray-400' };
    return m[s] || '';
  };

  if (loading) return <div className="text-muted p-6">加载中...</div>;
  if (!wo) return <div className="text-muted p-6">工单不存在</div>;

  const isTech = user?.role === 'technician';
  const isSupervisor = user?.role === 'supervisor' || user?.role === 'admin';
  const isAssignee = wo.assignee_id === user?.id;
  const canEdit = isAssignee && ['accepted', 'in_progress', 'paused', 'returned'].includes(wo.status);
  const canSubmit = isAssignee && wo.status === 'in_progress';
  const canApprove = isSupervisor && wo.status === 'pending_acceptance';

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-lg font-bold">{wo.title}</h1>
          <p className="text-sm text-muted">{wo.code} - {wo.equipment_name || '未知设备'}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`badge ${getStatusClass(wo.status)}`}>{STATUS_LABELS[wo.status]}</span>
          <PriorityBadge priority={wo.priority} />
        </div>
      </div>

      {/* Action Buttons */}
      {(canEdit || canSubmit || canApprove || (isSupervisor && ['pending_dispatch'].includes(wo.status))) && (
        <div className="card flex flex-wrap gap-2">
          {isAssignee && wo.status === 'assigned' && <button onClick={() => handleAction('accept')} className="btn btn-primary"><Play size={16} /> 接受工单</button>}
          {isAssignee && wo.status === 'accepted' && <button onClick={() => handleAction('start')} className="btn btn-success"><Play size={16} /> 开始维修</button>}
          {isAssignee && wo.status === 'in_progress' && <button onClick={() => handleAction('pause')} className="btn btn-outline"><Pause size={16} /> 暂停</button>}
          {isAssignee && wo.status === 'paused' && <button onClick={() => handleAction('resume')} className="btn btn-success"><Play size={16} /> 继续</button>}
          {isAssignee && wo.status === 'returned' && <button onClick={() => handleAction('start')} className="btn btn-primary"><RefreshCw size={16} /> 重新处理</button>}
          {canSubmit && <button onClick={doSubmit} className="btn btn-primary"><Send size={16} /> 提交完工</button>}
          {canApprove && <><button onClick={() => handleAction('approve')} className="btn btn-success"><CheckCircle size={16} /> 验收通过</button></>}
          {isSupervisor && ['pending_dispatch', 'assigned'].includes(wo.status) && <button onClick={() => handleAction('cancel')} className="btn btn-outline"><XCircle size={16} /> 取消工单</button>}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Basic Info */}
          <div className="card">
            <h2 className="font-semibold mb-3">基本信息</h2>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Info label="设备" value={wo.equipment_name} />
              <Info label="优先级" value={<PriorityBadge priority={wo.priority} />} />
              <Info label="类型" value={wo.order_type === 'fault_repair' ? '故障维修' : wo.order_type} />
              <Info label="负责人" value={wo.assignee_name || '未分派'} />
              <Info label="故障代码" value={wo.fault_code || '-'} />
              <Info label="计划完成" value={wo.planned_end_at?.split('T')[0] || '-'} />
            </div>
            {wo.fault_description && <div className="mt-3 text-sm"><div className="text-muted mb-1">故障描述</div><div className="p-2 rounded bg-white/5">{wo.fault_description}</div></div>}
            {wo.safety_risk && <div className="mt-3 p-3 rounded border border-red-500/30 bg-red-500/10 text-sm"><AlertTriangle size={14} className="inline mr-1" />安全风险: {wo.safety_risk}</div>}
          </div>

          {/* AI Diagnosis */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold flex items-center gap-2"><Bot size={16} /> AI 诊断建议</h2>
              <button onClick={runDiagnosis} disabled={diagLoading} className="btn btn-sm btn-outline">{diagLoading ? '分析中...' : diag ? '重新分析' : '获取建议'}</button>
            </div>
            {diag ? (
              <div className="space-y-3 text-sm">
                {diag.possible_causes?.length > 0 && <div><div className="text-muted mb-1">可能原因</div>{diag.possible_causes.map((c: any, i: number) => <div key={i} className="flex items-center gap-2 p-1.5"><span className={`badge ${c.confidence > 0.6 ? 'badge-p1' : 'badge-p3'}`}>{Math.round(c.confidence * 100)}%</span> {c.cause}</div>)}</div>}
                {diag.inspection_order?.length > 0 && <div><div className="text-muted mb-1">建议排查顺序</div><ol className="list-decimal pl-5 space-y-0.5">{diag.inspection_order.map((s: string, i: number) => <li key={i}>{s}</li>)}</ol></div>}
                {diag.safety_notes?.length > 0 && <div className="p-2 rounded bg-red-500/10 border border-red-500/20"><div className="text-muted mb-1">安全注意事项</div>{diag.safety_notes.map((s: string, i: number) => <div key={i} className="flex items-start gap-1"><AlertTriangle size={12} className="mt-1 text-red-400 flex-shrink-0" /> {s}</div>)}</div>}
                {diag.similar_cases?.length > 0 && <div><div className="text-muted mb-1">相似案例</div>{diag.similar_cases.map((c: any) => <div key={c.work_order_id} className="flex items-center gap-2 p-1.5"><span className="badge badge-p3">{Math.round(c.similarity * 100)}%</span> {c.code} - {c.root_cause || c.title}</div>)}</div>}
                <div className="text-xs text-muted border-t border-card-border pt-2">{diag.disclaimer}</div>
              </div>
            ) : <p className="text-sm text-muted">点击"获取建议"让 AI 辅助诊断故障原因</p>}
          </div>

          {/* Checklist */}
          <div className="card">
            <h2 className="font-semibold mb-3">维修检查清单</h2>
            <div className="space-y-1">
              {wo.checklist_items?.map((item: any) => (
                <label key={item.id} className={`flex items-start gap-3 p-2 rounded cursor-pointer ${item.is_completed ? 'bg-green-500/10' : 'hover:bg-white/5'}`}>
                  <input type="checkbox" checked={item.is_completed} onChange={e => handleChecklist(item.id, e.target.checked)} disabled={!canEdit && wo.status !== 'in_progress'} className="mt-0.5 w-4 h-4" />
                  <div className="flex-1 text-sm">
                    <span className={item.is_completed ? 'line-through text-muted' : ''}>{item.content}</span>
                    {item.is_required && <span className="text-red-400 text-xs ml-1">*必填</span>}
                    {item.remark && <div className="text-xs text-muted mt-0.5">{item.remark}</div>}
                  </div>
                </label>
              )) || <p className="text-sm text-muted">无检查项</p>}
            </div>
          </div>

          {/* Maintenance Logs */}
          <div className="card">
            <h2 className="font-semibold mb-3">维修过程记录</h2>
            <div className="space-y-3 mb-4 max-h-80 overflow-y-auto">
              {wo.logs?.map((log: any) => (
                <div key={log.id} className="p-2 rounded bg-white/5 text-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="badge badge-p3">{LOG_TYPE_LABELS[log.log_type] || log.log_type}</span>
                    <span className="text-xs text-muted">{log.operator_name} - {log.logged_at?.split('T')[0]} {log.logged_at?.split('T')[1]?.split('.')[0]}</span>
                  </div>
                  <div>{log.content}</div>
                  {log.ai_polished && <div className="mt-1 p-1.5 rounded bg-primary/10 text-xs"><span className="text-primary-300 font-medium">AI 润色:</span> {log.ai_polished}</div>}
                </div>
              )) || <p className="text-sm text-muted">暂无记录</p>}
            </div>
            {canEdit && (
              <div className="space-y-2 border-t border-card-border pt-3">
                <div className="flex gap-2">
                  <select value={newLog.log_type} onChange={e => setNewLog({ ...newLog, log_type: e.target.value })} className="text-sm">
                    {Object.entries(LOG_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <button onClick={runRewrite} className="btn btn-sm btn-outline" title="AI润色"><Bot size={14} /></button>
                </div>
                <textarea value={newLog.content} onChange={e => setNewLog({ ...newLog, content: e.target.value })} rows={3} className="w-full text-sm" placeholder="记录维修过程..." />
                {polishedText && (
                  <div className="p-2 rounded bg-primary/10 text-xs text-primary-300">
                    建议版本: {polishedText}
                    <button onClick={() => setNewLog({ ...newLog, content: polishedText })} className="ml-2 underline">使用</button>
                  </div>
                )}
                <button onClick={addLog} className="btn btn-primary btn-sm">添加记录</button>
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Labor */}
          <div className="card">
            <h3 className="font-semibold text-sm mb-2">工时记录</h3>
            {wo.labor_entries?.map((e: any) => (
              <div key={e.id} className="text-xs py-1 flex justify-between"><span>{e.hours}h</span><span className="text-muted">{e.operator_name}</span></div>
            )) || <p className="text-xs text-muted">无</p>}
            {canEdit && (
              <div className="space-y-1.5 mt-2 pt-2 border-t border-card-border">
                <input type="number" value={laborForm.hours || ''} onChange={e => setLaborForm({ ...laborForm, hours: Number(e.target.value) })} placeholder="工时(小时)" className="w-full text-sm" />
                <div className="flex gap-2">
                  <label className="flex items-center gap-1 text-xs cursor-pointer">
                    <input type="checkbox" checked={laborForm.is_downtime} onChange={e => setLaborForm({ ...laborForm, is_downtime: e.target.checked })} /> 停机工时
                  </label>
                </div>
                <input value={laborForm.remark} onChange={e => setLaborForm({ ...laborForm, remark: e.target.value })} placeholder="备注" className="w-full text-sm" />
                <button onClick={addLabor} className="btn btn-primary btn-sm btn-block">记录工时</button>
              </div>
            )}
          </div>

          {/* Spare Parts */}
          <div className="card">
            <h3 className="font-semibold text-sm mb-2">备件使用</h3>
            {wo.spare_parts?.map((s: any) => (
              <div key={s.id} className="text-xs py-1 flex justify-between"><span>{s.spare_part_name} x{s.quantity}{s.unit}</span></div>
            )) || <p className="text-xs text-muted">无</p>}
            {canEdit && (
              <div className="space-y-1.5 mt-2 pt-2 border-t border-card-border">
                <input value={spForm.spare_part_name} onChange={e => setSpForm({ ...spForm, spare_part_name: e.target.value })} placeholder="备件名称" className="w-full text-sm" />
                <div className="flex gap-2">
                  <input type="number" value={spForm.quantity} onChange={e => setSpForm({ ...spForm, quantity: Number(e.target.value) })} placeholder="数量" className="w-20 text-sm" />
                  <input value={spForm.unit} onChange={e => setSpForm({ ...spForm, unit: e.target.value })} placeholder="单位" className="w-16 text-sm" />
                </div>
                <button onClick={addSpare} className="btn btn-primary btn-sm btn-block">添加备件</button>
              </div>
            )}
          </div>

          {/* Status History */}
          <div className="card">
            <h3 className="font-semibold text-sm mb-2">状态历史</h3>
            <div className="space-y-1 text-xs">
              {wo.status_history?.map((h: any, i: number) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-muted w-20">{h.changed_at?.split('T')[0]}</span>
                  <span className="font-mono">{h.from_status || '-'} → {h.to_status}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Submit Section (when in_progress) */}
      {canSubmit && (
        <div className="card">
          <h2 className="font-semibold mb-3">完工信息</h2>
          <div className="space-y-3">
            <div><label className="block text-sm mb-1">根本原因 *</label><textarea value={submitForm.root_cause} onChange={e => setSubmitForm({ ...submitForm, root_cause: e.target.value })} rows={2} className="w-full" placeholder="故障的根本原因" /></div>
            <div><label className="block text-sm mb-1">处理措施 *</label><textarea value={submitForm.action_taken} onChange={e => setSubmitForm({ ...submitForm, action_taken: e.target.value })} rows={2} className="w-full" placeholder="采取的处理措施" /></div>
            <div><label className="block text-sm mb-1">更换部件</label><input value={submitForm.replaced_parts} onChange={e => setSubmitForm({ ...submitForm, replaced_parts: e.target.value })} className="w-full" placeholder="更换的部件(多个用逗号分隔)" /></div>
            <div><label className="block text-sm mb-1">测试结果 *</label><textarea value={submitForm.test_result} onChange={e => setSubmitForm({ ...submitForm, test_result: e.target.value })} rows={2} className="w-full" placeholder="测试结果" /></div>
            <div><label className="block text-sm mb-1">后续建议</label><textarea value={submitForm.follow_up_advice} onChange={e => setSubmitForm({ ...submitForm, follow_up_advice: e.target.value })} rows={2} className="w-full" placeholder="后续维护建议" /></div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={submitForm.needs_observation} onChange={e => setSubmitForm({ ...submitForm, needs_observation: e.target.checked })} />
              需要继续观察
            </label>
          </div>
        </div>
      )}

      {/* Approval Section (supervisor) */}
      {canApprove && (
        <div className="card space-y-4">
          <h2 className="font-semibold">验收</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><div className="text-muted">根本原因</div><div>{wo.root_cause}</div></div>
            <div><div className="text-muted">处理措施</div><div>{wo.action_taken}</div></div>
            <div><div className="text-muted">测试结果</div><div>{wo.test_result}</div></div>
            <div><div className="text-muted">更换部件</div><div>{wo.replaced_parts || '无'}</div></div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => handleAction('approve')} className="btn btn-success flex-1"><CheckCircle size={16} /> 验收通过</button>
            <details className="flex-1">
              <summary className="btn btn-danger w-full"><XCircle size={16} /> 退回修改</summary>
              <div className="mt-2 space-y-2">
                <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} rows={2} className="w-full" placeholder="退回原因" />
                <button onClick={() => handleAction('reject')} className="btn btn-danger btn-sm btn-block">确认退回</button>
              </div>
            </details>
          </div>
        </div>
      )}

      {/* Completed Info */}
      {wo.status === 'completed' && (
        <div className="card space-y-3">
          <h2 className="font-semibold flex items-center gap-2"><CheckCircle size={16} className="text-green-500" /> 维修报告</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><div className="text-muted">根本原因</div><div>{wo.root_cause}</div></div>
            <div><div className="text-muted">处理措施</div><div>{wo.action_taken}</div></div>
            <div><div className="text-muted">测试结果</div><div>{wo.test_result}</div></div>
            <div><div className="text-muted">后续建议</div><div>{wo.follow_up_advice || '无'}</div></div>
          </div>
          {wo.needs_observation && <div className="badge badge-p2">需要继续观察</div>}
        </div>
      )}
    </div>
  );
}

function Info({ label, value }: { label: string; value: any }) {
  return <div><span className="text-muted text-xs">{label}</span><div className="text-sm">{value}</div></div>;
}

function PriorityBadge({ priority }: { priority: string }) {
  const cls: any = { P1: 'badge-p1', P2: 'badge-p2', P3: 'badge-p3', P4: 'badge-p4' };
  return <span className={`badge ${cls[priority] || ''}`}>{PRIORITY_LABELS[priority] || priority}</span>;
}
