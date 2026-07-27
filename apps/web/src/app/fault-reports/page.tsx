'use client';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { listFaultReports, convertFaultReportToWorkOrder } from '@/lib/api';
import { ApiError, URGENCY_LABELS, FAULT_REPORT_STATUS_LABELS } from '@/lib/types';
import { AlertTriangle, Plus, Wrench, Loader2, ExternalLink } from 'lucide-react';
import toast from 'react-hot-toast';

export default function FaultReportList() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [convertingId, setConvertingId] = useState<number | null>(null);

  const fetchData = useCallback(() => {
    setLoading(true);
    listFaultReports()
      .then(d => setItems(d.items))
      .catch(e => toast.error(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleConvert = async (e: React.MouseEvent, frId: number) => {
    e.stopPropagation();
    const confirmed = window.confirm('确定要为此故障上报创建维修工单吗？');
    if (!confirmed) return;
    setConvertingId(frId);
    try {
      const result = await convertFaultReportToWorkOrder(frId);
      toast.success('工单创建成功');
      router.push(`/work-orders/${result.work_order_id}`);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 409 && err.workOrderId) {
        toast.error('该故障上报已创建工单，正在跳转...');
        router.push(`/work-orders/${err.workOrderId}`);
      } else {
        toast.error(err.message || '创建工单失败');
      }
      setConvertingId(null);
    }
  };

  const handleViewWorkOrder = (e: React.MouseEvent, woId: number) => {
    e.stopPropagation();
    router.push(`/work-orders/${woId}`);
  };

  const urgencyClass: any = { low: 'badge-p4', medium: 'badge-p3', high: 'badge-p2', critical: 'badge-p1' };
  const statusClass: any = { pending: 'bg-yellow-500/20 text-yellow-400', converted: 'bg-blue-500/20 text-blue-400', closed: 'bg-gray-500/20 text-gray-400' };

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">故障上报</h1>
        <button onClick={() => router.push('/fault-reports/new')} className="btn btn-primary">
          <Plus size={16} /> 快速上报
        </button>
      </div>
      <div className="card space-y-1">
        {loading ? (
          <p className="text-muted text-sm py-6 text-center">加载中...</p>
        ) : items.length === 0 ? (
          <div className="py-12 text-center">
            <AlertTriangle size={40} className="mx-auto mb-3 text-muted opacity-40" />
            <p className="text-muted text-sm mb-4">暂无故障上报记录</p>
            <button onClick={() => router.push('/fault-reports/new')} className="btn btn-primary btn-sm">
              <Plus size={14} /> 新建故障上报
            </button>
          </div>
        ) : (
          items.map(fr => (
            <div
              key={fr.id}
              className="p-3 rounded hover:bg-white/5 cursor-pointer transition-colors"
              onClick={() => router.push(`/fault-reports/${fr.id}`)}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span className="font-medium text-sm truncate">{fr.title}</span>
                  <span className={`badge ${urgencyClass[fr.urgency] || ''} shrink-0`}>
                    {URGENCY_LABELS[fr.urgency] || fr.urgency}
                  </span>
                  <span className={`badge text-xs shrink-0 ${statusClass[fr.status] || 'bg-gray-500/20 text-gray-400'}`}>
                    {FAULT_REPORT_STATUS_LABELS[fr.status] || fr.status}
                  </span>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-3">
                  {fr.status === 'pending' && !fr.related_work_order_id && (
                    <button
                      onClick={e => handleConvert(e, fr.id)}
                      disabled={convertingId === fr.id}
                      className="btn btn-primary btn-sm text-xs"
                    >
                      {convertingId === fr.id ? <Loader2 size={12} className="animate-spin" /> : <Wrench size={12} />}
                      创建工单
                    </button>
                  )}
                  {fr.related_work_order_id && (
                    <button
                      onClick={e => handleViewWorkOrder(e, fr.related_work_order_id)}
                      className="btn btn-outline btn-sm text-xs"
                    >
                      <ExternalLink size={12} /> 查看工单
                    </button>
                  )}
                </div>
              </div>
              <div className="text-xs text-muted">
                {fr.equipment_name || '未关联设备'}
                {fr.description && <> - {fr.description.substring(0, 100)}</>}
              </div>
              <div className="flex items-center gap-3 mt-1.5 text-xs">
                <span className="text-muted">{fr.reporter_name || '未知'}</span>
                <span className="text-muted">{fr.occurred_at?.split('T')[0] || ''}</span>
                {fr.is_downtime && <span className="flex items-center gap-0.5 text-red-400 font-medium">● 停机</span>}
                {fr.affects_production && <span className="flex items-center gap-0.5 text-yellow-400 font-medium">● 影响生产</span>}
                {fr.has_safety_risk && <span className="flex items-center gap-0.5 text-red-400 font-medium">▲ 安全风险</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
