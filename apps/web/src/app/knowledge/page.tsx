'use client';
import { BookOpen, Construction } from 'lucide-react';

export default function KnowledgePage() {
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-xl font-bold mb-4">知识库</h1>
      <div className="card text-center py-16">
        <Construction size={48} className="mx-auto mb-4 text-yellow-400" />
        <h2 className="text-lg font-medium mb-2">功能建设中</h2>
        <p className="text-sm text-muted max-w-md mx-auto">
          知识库管理功能正在开发中。完成后您可以在这里浏览维修手册、操作规程、故障案例和经验分享。
        </p>
        <div className="mt-6 flex items-center justify-center gap-4 text-xs text-muted">
          <div className="flex items-center gap-1"><BookOpen size={14} /> 维修手册</div>
          <div className="flex items-center gap-1"><BookOpen size={14} /> 操作规程</div>
          <div className="flex items-center gap-1"><BookOpen size={14} /> 故障案例</div>
        </div>
      </div>
    </div>
  );
}
