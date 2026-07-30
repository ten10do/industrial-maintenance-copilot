'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { listKnowledge, listEquipmentTypes, listFaultCodes } from '@/lib/api';
import { KNOWLEDGE_CATEGORY_LABELS } from '@/lib/types';
import { Search, Plus, BookOpen } from 'lucide-react';
import toast from 'react-hot-toast';

export default function KnowledgeList() {
  const { user } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [equipmentTypeFilter, setEquipmentTypeFilter] = useState('');
  const [faultCodeFilter, setFaultCodeFilter] = useState('');
  const [types, setTypes] = useState<any[]>([]);
  const [faultCodes, setFaultCodes] = useState<any[]>([]);

  useEffect(() => { listEquipmentTypes().then(setTypes).catch(() => {}); listFaultCodes().then(setFaultCodes).catch(() => {}); }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    const params: any = { page: String(page), page_size: '20' };
    if (keyword) params.keyword = keyword;
    if (categoryFilter) params.category = categoryFilter;
    try {
      const d = await listKnowledge(params);
      setItems(d.items);
      setTotal(d.total);
    } catch (e: any) { toast.error(e.message); } finally { setLoading(false); }
  }, [page, keyword, categoryFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const catLabel = (c: string) => KNOWLEDGE_CATEGORY_LABELS[c] || c;

  // Client-side filter for equipment type and fault code (backend doesn't support these in list)
  const filtered = items.filter(item => {
    if (equipmentTypeFilter && item.equipment_type_id !== Number(equipmentTypeFilter)) return false;
    if (faultCodeFilter && item.fault_code_id !== Number(faultCodeFilter)) return false;
    return true;
  });

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">知识库</h1>
        {(user?.role === 'admin' || user?.role === 'supervisor') && (
          <button onClick={() => router.push('/knowledge/new')} className="btn btn-primary">
            <Plus size={16} /> 新建条目
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <input value={keyword} onChange={e => setKeyword(e.target.value)} placeholder="搜索标题或内容..." className="pl-8 w-full" onKeyDown={e => { if (e.key === 'Enter') { setPage(1); fetchData(); } }} />
          <Search size={14} className="absolute left-2.5 top-2.5 text-muted" />
        </div>
        <select value={categoryFilter} onChange={e => { setCategoryFilter(e.target.value); setPage(1); }} className="text-sm">
          <option value="">全部类型</option>
          {Object.entries(KNOWLEDGE_CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={equipmentTypeFilter} onChange={e => { setEquipmentTypeFilter(e.target.value); setPage(1); }} className="text-sm">
          <option value="">全部设备类型</option>
          {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <select value={faultCodeFilter} onChange={e => { setFaultCodeFilter(e.target.value); setPage(1); }} className="text-sm">
          <option value="">全部故障代码</option>
          {faultCodes.map(f => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
        </select>
      </div>

      {loading ? <div className="text-muted p-6">加载中...</div> : filtered.length === 0 ? (
        <div className="card text-center py-12 text-muted">
          <BookOpen size={40} className="mx-auto mb-3 opacity-30" />
          <p>{keyword || categoryFilter ? '未找到匹配的知识条目' : '知识库中暂无内容'}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(item => (
            <div key={item.id} className="card cursor-pointer hover:bg-white/5 transition-colors" onClick={() => router.push(`/knowledge/${item.id}`)}>
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="font-semibold text-sm">{item.title}</div>
                  {item.summary && <div className="text-xs text-muted mt-0.5 line-clamp-2">{item.summary}</div>}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`badge text-xs ${item.status === 'published' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                    {item.status === 'published' ? '已发布' : '草稿'}
                  </span>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                <span className="badge bg-blue-500/20 text-blue-400">{catLabel(item.category)}</span>
                {item.tags?.map((t: string) => <span key={t} className="badge bg-white/10">{t}</span>)}
                {item.source && <span>来源: {item.source}</span>}
                <span className="ml-auto">{item.updated_at ? new Date(item.updated_at).toLocaleDateString('zh-CN') : ''}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {total > 20 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="btn btn-sm btn-outline">上一页</button>
          <span className="text-sm text-muted self-center">第 {page} 页 / 共 {Math.ceil(total / 20)} 页</span>
          <button onClick={() => setPage(p => p + 1)} disabled={page >= Math.ceil(total / 20)} className="btn btn-sm btn-outline">下一页</button>
        </div>
      )}
    </div>
  );
}
