'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { getKnowledge, deleteKnowledge } from '@/lib/api';
import { KNOWLEDGE_CATEGORY_LABELS } from '@/lib/types';
import { ArrowLeft, Edit, Trash2, Copy, MessageSquare } from 'lucide-react';
import toast from 'react-hot-toast';

export default function KnowledgeDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const router = useRouter();
  const [item, setItem] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getKnowledge(Number(id))
      .then(setItem)
      .catch((e: any) => setError(e.status === 403 ? '权限不足，无法查看此条目' : e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="max-w-3xl mx-auto text-muted p-6">加载中...</div>;
  if (error) return <div className="max-w-3xl mx-auto"><div className="card text-center py-12"><p className="text-red-400 mb-3">{error}</p><button onClick={() => router.push('/knowledge')} className="btn btn-outline">返回知识库</button></div></div>;
  if (!item) return <div className="max-w-3xl mx-auto"><div className="card text-center py-12"><p className="text-muted mb-3">知识条目不存在</p><button onClick={() => router.push('/knowledge')} className="btn btn-outline">返回知识库</button></div></div>;

  const catLabel = (c: string) => KNOWLEDGE_CATEGORY_LABELS[c] || c;
  const canEdit = user?.role === 'admin' || user?.role === 'supervisor';

  const handleDelete = async () => {
    if (!confirm('确定删除此知识条目？此操作不可撤销。')) return;
    try {
      await deleteKnowledge(item.id);
      toast.success('已删除');
      router.push('/knowledge');
    } catch (e: any) { toast.error(e.message); }
  };

  const copyRef = () => {
    const ref = `[${item.title}](${window.location.origin}/knowledge/${item.id})`;
    navigator.clipboard.writeText(ref).then(() => toast.success('引用已复制'));
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => router.push('/knowledge')} className="btn btn-sm btn-outline">
          <ArrowLeft size={14} /> 返回
        </button>
        <div className="flex-1" />
        {canEdit && (
          <>
            <button onClick={() => router.push(`/knowledge/${item.id}/edit`)} className="btn btn-sm btn-outline">
              <Edit size={14} /> 编辑
            </button>
            <button onClick={handleDelete} className="btn btn-sm btn-outline text-red-400">
              <Trash2 size={14} /> 删除
            </button>
          </>
        )}
        <button onClick={copyRef} className="btn btn-sm btn-outline">
          <Copy size={14} /> 复制引用
        </button>
        <button onClick={() => router.push(`/copilot?from_knowledge=${item.id}`)} className="btn btn-sm btn-primary">
          <MessageSquare size={14} /> 提问
        </button>
      </div>

      <div className="card space-y-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <h1 className="text-xl font-bold">{item.title}</h1>
            <span className={`badge ${item.status === 'published' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
              {item.status === 'published' ? '已发布' : '草稿'}
            </span>
          </div>
          <div className="flex flex-wrap gap-2 text-sm text-muted">
            <span className="badge bg-blue-500/20 text-blue-400">{catLabel(item.category)}</span>
            {item.tags?.map((t: string) => <span key={t} className="badge bg-white/10">{t}</span>)}
          </div>
        </div>

        {item.summary && <p className="text-muted text-sm border-l-2 border-primary/30 pl-3">{item.summary}</p>}

        <div className="prose prose-invert max-w-none whitespace-pre-wrap text-sm leading-relaxed">{item.content}</div>

        <hr className="border-card-border" />

        <div className="grid grid-cols-2 gap-3 text-sm">
          {item.source && <Info label="来源名称" value={item.source} />}
          <Info label="内容类型" value={catLabel(item.category)} />
          <Info label="浏览次数" value={String(item.view_count || 0)} />
          <Info label="更新时间" value={item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN') : '-'} />
          <Info label="创建时间" value={item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'} />
        </div>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><span className="text-xs text-muted">{label}</span><div className="text-sm">{value || '-'}</div></div>;
}
