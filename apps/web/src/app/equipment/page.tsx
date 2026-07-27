'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { listEquipment, listEquipmentTypes, getEquipmentWorkOrders, copilotEquipmentHistory } from '@/lib/api';
import { Search, QrCode } from 'lucide-react';
import toast from 'react-hot-toast';

export default function EquipmentList() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [types, setTypes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const fetch = async () => {
    setLoading(true);
    const params: any = { page: String(page), page_size: '20' };
    if (keyword) params.keyword = keyword;
    if (typeFilter) params.equipment_type_id = typeFilter;
    if (statusFilter) params.status = statusFilter;
    try { const d = await listEquipment(params); setItems(d.items); setTotal(d.total); } catch (e: any) { toast.error(e.message); } finally { setLoading(false); }
  };

  useEffect(() => { fetch(); }, [page, typeFilter, statusFilter]);
  useEffect(() => { listEquipmentTypes().then(setTypes).catch(() => {}); }, []);

  const statusLabel: any = { running: '运行中', fault: '故障', under_repair: '维修中', stopped: '停机', scrapped: '已报废' };
  const statusClass: any = { running: 'text-green-400', fault: 'text-red-400', under_repair: 'text-yellow-400', stopped: 'text-gray-400', scrapped: 'text-gray-500' };

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <h1 className="text-xl font-bold">设备台账</h1>
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <input value={keyword} onChange={e => setKeyword(e.target.value)} placeholder="搜索设备编号或名称..." className="pl-8 w-full" onKeyDown={e => { if (e.key === 'Enter') { setPage(1); fetch(); } }} />
          <Search size={14} className="absolute left-2.5 top-2.5 text-muted" />
        </div>
        <select value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1); }} className="text-sm">
          <option value="">全部类型</option>
          {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }} className="text-sm">
          <option value="">全部状态</option>
          <option value="running">运行中</option>
          <option value="fault">故障</option>
          <option value="under_repair">维修中</option>
          <option value="stopped">停机</option>
        </select>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {loading ? <div className="col-span-full text-muted">加载中...</div> : items.length === 0 ? <div className="col-span-full text-muted">无设备</div> : items.map(eq => (
          <div key={eq.id} className="card cursor-pointer hover:bg-white/5 transition-colors" onClick={() => router.push(`/equipment/${eq.id}`)}>
            <div className="flex items-start justify-between mb-2">
              <div>
                <div className="font-semibold text-sm">{eq.name}</div>
                <div className="text-xs text-muted font-mono">{eq.code}</div>
              </div>
              <span className={`badge ${statusClass[eq.status] || ''}`}>{statusLabel[eq.status] || eq.status}</span>
            </div>
            <div className="text-xs text-muted space-y-0.5">
              {eq.equipment_type_name && <div>类型: {eq.equipment_type_name}</div>}
              {eq.location && <div>位置: {eq.location}</div>}
              {eq.manufacturer && <div>制造商: {eq.manufacturer} {eq.model}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
