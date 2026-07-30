'use client';
import { Citation, AskResult } from '@/lib/types';
import { KNOWLEDGE_CATEGORY_LABELS } from '@/lib/types';
import { Link, AlertTriangle, ChevronRight, Zap } from 'lucide-react';

interface SourceType {
  source_type: string;
  source_id: number;
  title: string;
  excerpt?: string;
  relevance_score: number;
  url?: string;
}

export default function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      <div className="text-xs text-muted font-medium mb-1">引用来源 ({citations.length})</div>
      {citations.map((c, i) => (
        <CitationCard key={`${c.source_type}-${c.source_id}`} citation={c} index={i + 1} />
      ))}
    </div>
  );
}

function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  const scoreColor = citation.relevance_score > 0.7 ? 'text-green-400' : citation.relevance_score > 0.3 ? 'text-yellow-400' : 'text-gray-400';

  return (
    <a
      href={citation.url || '#'}
      target="_self"
      className="flex items-start gap-3 p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors group no-underline text-inherit"
    >
      <span className="shrink-0 w-5 h-5 rounded-full bg-primary/20 text-primary text-xs flex items-center justify-center mt-0.5">
        {index}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{citation.title}</span>
          <span className={`text-xs ${scoreColor} font-mono shrink-0`}>{Math.round(citation.relevance_score * 100)}%</span>
        </div>
        {citation.excerpt && (
          <p className="text-xs text-muted mt-0.5 line-clamp-2">{citation.excerpt}</p>
        )}
      </div>
      <ChevronRight size={14} className="shrink-0 mt-1 text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
    </a>
  );
}

export function AnswerPanel({ result, loading }: { result: AskResult | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="card">
        <div className="flex items-center gap-3 text-muted">
          <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          <span>正在检索知识库并生成回答...</span>
        </div>
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="space-y-4">
      {/* Safety disclaimer - always visible */}
      <div className="flex items-start gap-2 text-xs text-yellow-400 bg-yellow-500/10 rounded-lg p-3">
        <AlertTriangle size={14} className="shrink-0 mt-0.5" />
        <span>{result.disclaimer}</span>
      </div>

      {/* Answer */}
      <div className="card space-y-4">
        {/* Confidence & mock indicator */}
        <div className="flex items-center gap-3 text-xs">
          {result.is_mock && (
            <span className="badge bg-yellow-500/20 text-yellow-400">Mock AI 模式</span>
          )}
          <span className="text-muted">
            置信度: <span className={result.confidence > 0.7 ? 'text-green-400' : result.confidence > 0.3 ? 'text-yellow-400' : 'text-gray-400 font-medium'}>
              {Math.round(result.confidence * 100)}%
            </span>
          </span>
          {result.confidence < 0.3 && (
            <span className="text-yellow-400">当前知识库证据不足，请结合设备手册和现场检查确认。</span>
          )}
        </div>

        {/* Answer text */}
        <div className="prose prose-invert max-w-none text-sm whitespace-pre-wrap leading-relaxed">
          {result.answer}
        </div>

        {/* Warnings */}
        {result.warnings && result.warnings.length > 0 && (
          <div className="space-y-1">
            {result.warnings.map((w, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 rounded p-2">
                <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                <span>{w}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Citations */}
      {result.citations && result.citations.length > 0 && (
        <div className="card">
          <CitationList citations={result.citations} />
        </div>
      )}

      {/* No sources warning */}
      {(!result.citations || result.citations.length === 0) && (
        <div className="card">
          <div className="flex items-start gap-2 text-sm text-yellow-400">
            <Zap size={14} className="shrink-0 mt-0.5" />
            <span>当前知识库证据不足，请结合设备手册和现场检查确认。</span>
          </div>
        </div>
      )}
    </div>
  );
}
