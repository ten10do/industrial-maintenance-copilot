'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { getKnowledge, updateKnowledge, listEquipmentTypes, listFaultCodes } from '@/lib/api';
import { KNOWLEDGE_CATEGORY_LABELS } from '@/lib/types';
import { ArrowLeft, Save } from 'lucide-react';
import toast from 'react-hot-toast';

export default function KnowledgeEdit() {
  const { id } = useParams();
  const { user } = useAuth();
  const router = useRouter();
  const [types, setTypes] = useState<any[]>([]);
  const [faultCodes, setFaultCodes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    title: '', category: 'experience', content: '', summary: '', tags: '',
    equipment_type_id: '', fault_code_id: '', source: '', status: 'published',
  });

  useEffect(() => {
    listEquipmentTypes().then(setTypes).catch(() => {});
    listFaultCodes().then(setFaultCodes).catch(() => {});
    if (user?.role !== 'admin' && user?.role !== 'supervisor') {
      toast.error('无权限编辑知识条目');
      router.push('/knowledge');
      return;
    }
    getKnowledge(Number(id))
      .then(item => {
        setForm({
          title: item.title || '', category: item.category || 'experience', content: item.content || '',
          summary: item.summary || '', tags: item.tags?.join(', ') || '',
          equipment_type_id: item.equipment_type_id ? String(item.equipment_type_id) : '',
          fault_code_id: item.fault_code_id ? String(item.fault_code_id) : '',
          source: item.source || '', status: item.status || 'published',
        });
      })
      .catch((e: any) => { toast.error(e.message); router.push('/knowledge'); })
      .finally(() => setLoading(false));
  }, [id, user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim() || !form.content.trim()) {
      toast.error('标题和正文不能为空');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        equipment_type_id: form.equipment_type_id ? Number(form.equipment_type_id) : null,
        fault_code_id: form.fault_code_id ? Number(form.fault_code_id) : null,
        tags: form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
      };
      await updateKnowledge(Number(id), payload);
      toast.success('保存成功');
      router.push(`/knowledge/${id}`);
    } catch (e: any) { toast.error(e.message); } finally { setSaving(false); }
  };

  if (loading) return <div className="max-w-2xl mx-auto text-muted p-6">加载中...</div>;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => router.push(`/knowledge/${id}`)} className="btn btn-sm btn-outline">
          <ArrowLeft size={14} /> 返回
        </button>
        <h1 className="text-xl font-bold">编辑知识条目</h1>
      </div>

      <form onSubmit={handleSubmit} className="card space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">标题 <span className="text-red-400">*</span></label>
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className="w-full" />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">内容类型 <span className="text-red-400">*</span></label>
            <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className="w-full">
              {Object.entries(KNOWLEDGE_CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">发布状态</label>
            <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className="w-full">
              <option value="published">已发布</option>
              <option value="draft">草稿</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">摘要</label>
          <textarea value={form.summary} onChange={e => setForm({ ...form, summary: e.target.value })} className="w-full" rows={2} />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">正文 <span className="text-red-400">*</span></label>
          <textarea value={form.content} onChange={e => setForm({ ...form, content: e.target.value })} className="w-full min-h-[200px]" rows={10} />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">设备类型</label>
            <select value={form.equipment_type_id} onChange={e => setForm({ ...form, equipment_type_id: e.target.value })} className="w-full">
              <option value="">无</option>
              {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">故障代码</label>
            <select value={form.fault_code_id} onChange={e => setForm({ ...form, fault_code_id: e.target.value })} className="w-full">
              <option value="">无</option>
              {faultCodes.map(f => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">来源名称</label>
            <input value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} className="w-full" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">标签（逗号分隔）</label>
            <input value={form.tags} onChange={e => setForm({ ...form, tags: e.target.value })} className="w-full" />
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={() => router.back()} className="btn btn-outline">取消</button>
          <button type="submit" disabled={saving} className="btn btn-primary">
            <Save size={14} /> {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </form>
    </div>
  );
}
