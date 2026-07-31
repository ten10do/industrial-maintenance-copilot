'use client';

import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, LockKeyhole, ShieldAlert, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { approveOperation, listOperationApprovals, rejectOperation } from '@/lib/api';
import { useAuth } from '@/lib/auth';

const COMMAND_LABELS: Record<string, string> = {
  shutdown: '受控停机',
  emergency_stop: '紧急停机',
  restart: '设备重启',
  start: '设备启动',
  reset_alarm: '复位报警',
  set_speed: '调整转速',
};

export default function ApprovalsPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState('pending');
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const canReview = user?.role === 'admin' || user?.role === 'supervisor';

  const load = useCallback(() => {
    setLoading(true);
    listOperationApprovals(filter === 'all' ? undefined : filter)
      .then(setItems)
      .catch((error) => toast.error(error.message))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const review = async (item: any, action: 'approve' | 'reject') => {
    const note = notes[item.id]?.trim();
    if (!note) {
      toast.error('请先填写审批意见和现场安全确认');
      return;
    }
    setBusyId(item.id);
    try {
      if (action === 'approve') {
        await approveOperation(item.id, note);
        toast.success('审批通过，命令已由设备网关执行');
      } else {
        await rejectOperation(item.id, note);
        toast.success('高风险操作已驳回，未执行设备命令');
      }
      await load();
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs tracking-[0.18em] uppercase text-red-300 font-semibold mb-1"><LockKeyhole size={14} /> Human-in-the-loop</div>
          <h1 className="text-2xl font-bold">高风险操作审批中心</h1>
          <p className="text-sm text-muted mt-1">AI Agent 只能提出操作申请；未经主管人工审批，Equipment Gateway 不执行命令</p>
        </div>
        <select value={filter} onChange={(event) => setFilter(event.target.value)} className="text-sm">
          <option value="pending">待审批</option><option value="approved">已批准</option><option value="rejected">已驳回</option><option value="all">全部</option>
        </select>
      </div>

      <div className="rounded-xl border border-yellow-500/25 bg-yellow-500/[0.07] p-4 flex items-start gap-3 text-sm">
        <ShieldAlert className="text-yellow-300 shrink-0 mt-0.5" size={18} />
        <div><strong className="text-yellow-200">安全边界</strong><p className="text-muted mt-1">批准前必须确认维护窗口、停机影响、现场负责人、能源隔离和 LOTO。批准动作本身会触发 Mock 设备命令，请勿将演示结果视为真实 PLC 状态。</p></div>
      </div>

      {loading ? <div className="text-muted p-6">加载中...</div> : (
        <div className="space-y-4">
          {items.map((item) => (
            <article key={item.id} className="card">
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                <div className="space-y-3 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={item.status} />
                    <span className="badge bg-red-500/15 text-red-300">{item.risk_level}</span>
                    <span className="text-xs text-muted font-mono">审批 #{item.id}</span>
                  </div>
                  <div>
                    <h2 className="font-semibold">{COMMAND_LABELS[item.command_type] || item.command_type} · {item.equipment_name}</h2>
                    <p className="text-xs text-muted mt-1">{item.equipment_code} · 工单 {item.work_order_id ? `#${item.work_order_id}` : '未关联'} · 申请人 {item.requested_by_name}</p>
                  </div>
                  <div className="rounded-lg border border-red-500/15 bg-red-500/5 p-3">
                    <div className="text-xs text-red-300 mb-1">风险说明</div>
                    <p className="text-sm leading-6">{item.risk_reason}</p>
                  </div>
                  {item.command_payload && <div className="text-xs text-muted">命令参数：<code className="font-mono text-slate-300">{JSON.stringify(item.command_payload)}</code></div>}
                  {item.status !== 'pending' && (
                    <div className="text-sm">
                      <div><span className="text-muted">审批人：</span>{item.reviewed_by_name || '-'}</div>
                      <div className="mt-1"><span className="text-muted">审批意见：</span>{item.review_note || '-'}</div>
                      <div className="mt-1"><span className="text-muted">命令执行：</span>{item.command_executed ? '已执行' : '未执行'}</div>
                    </div>
                  )}
                </div>
                {item.status === 'pending' && (
                  <div className="lg:w-80 space-y-3">
                    <label className="block text-xs text-muted">审批意见与安全确认
                      <textarea
                        rows={4}
                        value={notes[item.id] || ''}
                        onChange={(event) => setNotes((current) => ({ ...current, [item.id]: event.target.value }))}
                        placeholder="例：已确认 14:00 维护窗口，张工负责 LOTO，产线主管已知悉"
                        className="w-full mt-1.5 resize-none"
                        disabled={!canReview}
                      />
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <button disabled={!canReview || busyId === item.id} onClick={() => review(item, 'reject')} className="btn btn-outline text-red-300 border-red-500/30"><XCircle size={15} />驳回</button>
                      <button disabled={!canReview || busyId === item.id} onClick={() => review(item, 'approve')} className="btn btn-danger"><CheckCircle2 size={15} />批准并执行</button>
                    </div>
                    {!canReview && <p className="text-xs text-muted">当前角色仅可查看，审批需主管或管理员执行。</p>}
                  </div>
                )}
              </div>
            </article>
          ))}
          {!items.length && <div className="card text-center text-muted py-12">当前没有{filter === 'pending' ? '待审批' : ''}操作</div>}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = { pending: '待审批', approved: '已批准', rejected: '已驳回', execution_failed: '执行失败' };
  const styles: Record<string, string> = { pending: 'bg-yellow-500/15 text-yellow-300', approved: 'bg-green-500/15 text-green-300', rejected: 'bg-gray-500/15 text-gray-300', execution_failed: 'bg-red-500/15 text-red-300' };
  return <span className={`badge ${styles[status] || styles.pending}`}>{labels[status] || status}</span>;
}
