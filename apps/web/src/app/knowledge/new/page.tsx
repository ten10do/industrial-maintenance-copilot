'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { createKnowledge, listEquipmentTypes, listFaultCodes } from '@/lib/api';
import { KNOWLEDGE_CATEGORY_LABELS } from '@/lib/types';
import { ArrowLeft, Save } from 'lucide-react';
import toast from 'react-hot-toast';

export default function KnowledgeNew() {
  const { user } = useAuth();
  const router = useRouter();
  const [types, setTypes] = useState<any[]>([]);
  const [faultCodes, setFaultCodes] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    title: '', category: 'experience', content: '', summary: '', tags: '',
    equipment_type_id: '', fault_code_id: '', source: '', status: 'published',
  });

  useEffect(() => {
    listEquipmentTypes().then(setTypes).catch(() => {});
    listFaultCodes().then(setFaultCodes).catch(() => {});
    if (user?.role !== 'admin' && user?.role !== 'supervisor') {
      toast.error('无权限创建知识条目');
      router.push('/knowledge');
    }
  }, [user, router]);

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
      const result = await createKnowledge(payload);
      toast.success('创建成功');
      router.push(`/knowledge/${result.id}`);
    } catch (e: any) { toast.error(e.message); } finally { setSaving(false); }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => router.push('/knowledge')} className="btn btn-sm btn-outline">
          <ArrowLeft size={14} /> 返回
        </button>
        <h1 className="text-xl font-bold">新建知识条目</h1>
      </div>

      <form onSubmit={handleSubmit} className="card space-y-4">
        <FormField label="标题" required>
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="知识条目标题" className="w-full" />
        </FormField>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="内容类型" required>
            <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className="w-full">
              {Object.entries(KNOWLEDGE_CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </FormField>
          <FormField label="发布状态">
            <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className="w-full">
              <option value="published">已发布</option>
              <option value="draft">草稿</option>
            </select>
          </FormField>
        </div>

        <FormField label="摘要">
          <textarea value={form.summary} onChange={e => setForm({ ...form, summary: e.target.value })} placeholder="简要描述知识条目内容" className="w-full" rows={2} />
        </FormField>

        <FormField label="正文" required>
          <textarea value={form.content} onChange={e => setForm({ ...form, content: e.target.value })} placeholder="知识条目正文内容（支持 Markdown 格式）" className="w-full min-h-[200px]" rows={10} />
        </FormField>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="设备类型">
            <select value={form.equipment_type_id} onChange={e => setForm({ ...form, equipment_type_id: e.target.value })} className="w-full">
              <option value="">无</option>
              {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </FormField>
          <FormField label="故障代码">
            <select value={form.fault_code_id} onChange={e => setForm({ ...form, fault_code_id: e.target.value })} className="w-full">
              <option value="">无</option>
              {faultCodes.map(f => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
            </select>
          </FormField>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="来源名称">
            <input value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} placeholder="例如：设备维修手册 V3.2" className="w-full" />
          </FormField>
          <FormField label="标签（逗号分隔）">
            <input value={form.tags} onChange={e => setForm({ ...form, tags: e.target.value })} placeholder="例如：接近开关, 包装机, E104" className="w-full" />
          </FormField>
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

function FormField({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}{required && <span className="text-red-400 ml-0.5">*</span>}</label>
      {children}
    </div>
  );
}
