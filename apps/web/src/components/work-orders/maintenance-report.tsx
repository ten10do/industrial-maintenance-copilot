'use client';

import { useCallback, useEffect, useState } from 'react';
import { getWorkOrderReport, regenerateWorkOrderReport } from '@/lib/api';
import { WorkOrderReport } from '@/lib/types';

export default function MaintenanceReport({ workOrderId }: { workOrderId: number }) {
  const [report, setReport] = useState<WorkOrderReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState('');

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getWorkOrderReport(workOrderId);
      setReport(data);
    } catch (e: any) {
      setError(e.message || '加载报告失败');
    } finally {
      setLoading(false);
    }
  }, [workOrderId]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  async function handleRegenerate() {
    setRegenerating(true);
    try {
      const data = await regenerateWorkOrderReport(workOrderId);
      setReport(data);
    } catch (e: any) {
      setError(e.message || '重新生成报告失败');
    } finally {
      setRegenerating(false);
    }
  }

  if (loading) {
    return <div className="text-center py-8 text-muted">加载维修报告中...</div>;
  }

  if (error) {
    return (
      <div className="card p-4 border-red-500/30">
        <p className="text-red-400 mb-2">{error}</p>
        <button onClick={loadReport} className="btn btn-sm btn-outline">重试</button>
      </div>
    );
  }

  if (!report) {
    return <div className="text-center py-4 text-muted">暂无维修报告</div>;
  }

  return (
    <div className="card p-4 space-y-4" data-testid="maintenance-report">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">维修报告</h3>
          <p className="text-xs text-muted mt-1">
            生成方式：{report.generation_method === 'ai' ? 'AI 生成' : '模板生成'}
            {' · '}版本 {report.version}
            {report.is_mock && ' · 智能降级'}
          </p>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="btn btn-sm btn-outline"
          data-testid="regenerate-report-button"
        >
          {regenerating ? '生成中...' : '重新生成'}
        </button>
      </div>

      <div className="bg-white/5 rounded-lg p-4">
        <p className="text-sm font-medium text-primary-300 mb-1">摘要</p>
        <p className="text-sm text-muted leading-relaxed">{report.summary}</p>
      </div>

      {report.sections && report.sections.length > 0 && (
        <div className="space-y-3">
          {report.sections.map((section, i) => (
            <div key={i} className="border-t border-white/5 pt-3 first:border-0 first:pt-0">
              <p className="text-sm font-medium mb-1">{section.title}</p>
              <p className="text-sm text-muted leading-relaxed">{section.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
