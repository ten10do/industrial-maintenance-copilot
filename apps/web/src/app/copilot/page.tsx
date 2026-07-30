'use client';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { copilotAsk, listEquipmentTypes, listFaultCodes } from '@/lib/api';
import { AskResult } from '@/lib/types';
import { AnswerPanel } from '@/components/copilot/citation-card';
import { Send, Trash2, AlertTriangle, Zap } from 'lucide-react';
import toast from 'react-hot-toast';

const EXAMPLE_QUESTIONS = [
  'E102 故障一般是什么原因？',
  '包装机接近开关频繁松动如何处理？',
  '更换伺服驱动器前需要完成哪些安全检查？',
  '这台设备最近是否发生过类似故障？',
];

export default function CopilotPage() {
  const { user } = useAuth();
  const sp = useSearchParams();
  const [question, setQuestion] = useState('');
  const [equipmentTypeId, setEquipmentTypeId] = useState<number | undefined>(undefined);
  const [faultCode, setFaultCode] = useState<string | undefined>(undefined);
  const [types, setTypes] = useState<any[]>([]);
  const [faultCodes, setFaultCodes] = useState<any[]>([]);
  const [result, setResult] = useState<AskResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listEquipmentTypes().then(setTypes).catch(() => {});
    listFaultCodes().then(setFaultCodes).catch(() => {});
  }, []);

  const handleAsk = async (q?: string) => {
    const query = q || question.trim();
    if (!query) return;
    setLoading(true);
    try {
      const res = await copilotAsk(query, equipmentTypeId, faultCode);
      setResult(res);
    } catch (e: any) {
      toast.error(e.message);
      setResult(null);
    } finally { setLoading(false); }
  };

  const handleClear = () => {
    setQuestion('');
    setResult(null);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-xl font-bold">AI 维修助手</h1>

      {/* Safety notice - always visible */}
      <div className="flex items-start gap-2 text-sm text-yellow-400 bg-yellow-500/10 rounded-lg p-4">
        <AlertTriangle size={16} className="shrink-0 mt-0.5" />
        <span>AI 建议仅供辅助。维修人员应依据现场情况、设备手册和安全规范进行判断。</span>
      </div>

      {/* Input area */}
      <div className="card space-y-4">
        <div className="flex gap-2">
          <input
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAsk(); } }}
            placeholder="输入维修问题，AI 将从知识库中检索并提供建议..."
            className="flex-1"
            data-testid="copilot-question-input"
          />
          <button onClick={() => handleAsk()} disabled={loading || !question.trim()} className="btn btn-primary" data-testid="copilot-submit-button">
            <Send size={16} /> {loading ? '检索中...' : '提问'}
          </button>
          {result && (
            <button onClick={handleClear} className="btn btn-outline">
              <Trash2 size={16} />
            </button>
          )}
        </div>

        {/* Filters */}
        <div className="flex gap-2 flex-wrap">
          <select value={equipmentTypeId || ''} onChange={e => setEquipmentTypeId(e.target.value ? Number(e.target.value) : undefined)} className="text-sm">
            <option value="">全部设备类型</option>
            {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select value={faultCode || ''} onChange={e => setFaultCode(e.target.value || undefined)} className="text-sm">
            <option value="">全部故障代码</option>
            {faultCodes.map(f => <option key={f.code} value={f.code}>{f.code} - {f.name}</option>)}
          </select>
        </div>

        {/* Example questions */}
        {!result && (
          <div className="space-y-1">
            <div className="text-xs text-muted mb-2">快捷示例</div>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_QUESTIONS.map((q, i) => (
                <button key={i} onClick={() => handleAsk(q)} className="btn btn-sm btn-outline text-xs">{q}</button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Answer panel */}
      <AnswerPanel result={result} loading={loading} />
    </div>
  );
}
