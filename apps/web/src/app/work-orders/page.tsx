'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { listWorkOrders, listTechnicians, assignWorkOrder, cancelWorkOrder } from '@/lib/api';
import { STATUS_LABELS, PRIORITY_LABELS } from '@/lib/types';
import { Search, Plus } from 'lucide-react';
import toast from 'react-hot-toast';

export default function WorkOrderList() {
  const { user } = useAuth();
  const router = useRouter();
  const sp = useSearchParams();
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState(sp.get('status') || '');
  const [keyword, setKeyword] = useState('');
  const [mine, setMine] = useState(sp.get('mine') === 'true');
  const [assigning, setAssigning] = useState<number | null>(null);
  const [techs, setTechs] = useState<any[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    const params: any = { page: String(page), page_size: '20' };
    if (statusFilter) params.status_filter = statusFilter;
    if (keyword) params.keyword = keyword;
    if (mine) params.mine = 'true';
    try {
      const d = await listWorkOrders(params);
      setItems(d.items);
      setTotal(d.total);
    } catch (e: any) {
      toast.error(e.message);
    } finally { setLoading(false); }
  }, [page, statusFilter, keyword, mine]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openAssign = async (woId: number) => {
    setAssigning(woId);
    try { setTechs(await listTechnicians()); } catch {}
  };

  const doAssign = async (woId: number, techId: number) => {
    try {
      await assignWorkOrder(woId, { assignee_id: techId });
      toast.success('分派成功');
      setAssigning(null);
      fetchData();
    } catch (e: any) { toast.error(e.message); }
  };

  const getStatusClass = (s: string) => {
    const m: any = { pending_dispatch: 'text-gray-400', assigned: 'text-blue-400', accepted: 'text-purple-400', in_progress: 'text-yellow-400', pending_acceptance: 'text-green-400', completed: 'text-green-500', returned: 'text-red-400', paused: 'text-gray-400' };
    return m[s] || '';
  };

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">工单管理</h1>
        <button onClick={() => router.push('/fault-reports/new')} className="btn btn-primary">
          <Plus size={16} /> 新建工单
        </button>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex gap-2 flex-wrap">
          {['', 'pending_dispatch', 'assigned', 'in_progress', 'pending_acceptance', 'completed'].map(s => (
            <button key={s} onClick={() => { setStatusFilter(s); setPage(1); }} className={`btn btn-sm ${statusFilter === s ? 'btn-primary' : 'btn-outline'}`}>
              {s ? STATUS_LABELS[s] : '全部'}
            </button>
          ))}
        </div>
        {user?.role === 'technician' && (
          <button onClick={() => { setMine(!mine); setPage(1); }} className={`btn btn-sm ${mine ? 'btn-primary' : 'btn-outline'}`}>仅看我的</button>
        )}
        <div className="flex-1 min-w-0" />
        <div className="relative">
          <input value={keyword} onChange={e => setKeyword(e.target.value)} placeholder="搜索工单..." className="pl-8 pr-3 py-1.5 text-sm" onKeyDown={e => { if (e.key === 'Enter') { setPage(1); fetchData(); } }} />
          <Search size={14} className="absolute left-2.5 top-2 text-muted" />
        </div>
      </div>
      <div className="card space-y-1 overflow-x-auto">
        {loading ? <p className="text-muted text-sm p-4">加载中...</p> : items.length === 0 ? <p className="text-muted text-sm p-4">暂无工单</p> : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted text-xs">
                <th className="p-2">编号</th><th className="p-2">标题</th><th className="p-2">设备</th><th className="p-2">优先级</th><th className="p-2">状态</th><th className="p-2">负责人</th><th className="p-2">创建时间</th><th className="p-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map(wo => (
                <tr key={wo.id} className="border-t border-card-border hover:bg-white/5 cursor-pointer" onClick={() => router.push(`/work-orders/${wo.id}`)}>
                  <td className="p-2 font-mono text-xs text-muted">{wo.code}</td>
                  <td className="p-2">{wo.title}</td>
                  <td className="p-2 text-muted">{wo.equipment_name || '-'}</td>
                  <td className="p-2"><PriorityBadge priority={wo.priority} /></td>
                  <td className="p-2"><span className={getStatusClass(wo.status)}>{STATUS_LABELS[wo.status] || wo.status}</span></td>
                  <td className="p-2 text-muted">{wo.assignee_name || '-'}</td>
                  <td className="p-2 text-muted text-xs">{wo.created_at?.split('T')[0]}</td>
                  <td className="p-2" onClick={e => e.stopPropagation()}>
                    {(user?.role === 'admin' || user?.role === 'supervisor') && wo.status === 'pending_dispatch' && (
                      <button onClick={() => openAssign(wo.id)} className="btn btn-primary btn-sm text-xs">分派</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {assigning && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setAssigning(null)}>
          <div className="card max-w-sm w-full mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold mb-3">分派给维修工程师</h3>
            <div className="space-y-2">
              {techs.map(t => (
                <div key={t.user_id} className="flex items-center justify-between p-3 rounded bg-white/5 hover:bg-white/10 cursor-pointer" onClick={() => doAssign(assigning, t.user_id)}>
                  <div>
                    <div className="font-medium text-sm">{t.full_name}</div>
                    <div className="text-xs text-muted">在修: {t.active_work_orders} - {t.skills?.map((s: any) => s.name).join(', ')}</div>
                  </div>
                  <span className={`badge ${t.availability === 'available' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                    {t.availability === 'available' ? '可用' : '忙碌'}
                  </span>
                </div>
              ))}
            </div>
            <button onClick={() => setAssigning(null)} className="btn btn-outline btn-block mt-3">取消</button>
          </div>
        </div>
      )}
    </div>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const cls: any = { P1: 'badge-p1', P2: 'badge-p2', P3: 'badge-p3', P4: 'badge-p4' };
  return <span className={`badge ${cls[priority] || ''}`}>{PRIORITY_LABELS[priority] || priority}</span>;
}
