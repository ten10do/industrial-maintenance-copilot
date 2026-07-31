'use client';

import { CompletionValidationError } from '@/lib/types';

const MISSING_LABELS: Record<string, string> = {
  root_cause: '根本原因',
  action_taken: '处理措施',
  test_result: '测试结果',
  required_checklist_items: '必做检查项未全部完成',
  maintenance_log: '至少需要一条维修过程记录',
  labor_entry: '至少需要一条工时记录',
  test_step: '至少完成一项测试验证',
  completion_photo: '高风险工单需上传完工或测试照片',
};

export default function CompletionValidationDisplay({ error }: { error: CompletionValidationError }) {
  if (!error.missing_requirements || error.missing_requirements.length === 0) {
    return null;
  }

  return (
    <div className="card p-4 border-red-500/30 bg-red-500/5" data-testid="completion-validation">
      <p className="text-sm font-medium text-red-400 mb-2">{error.message}</p>
      <p className="text-xs text-muted mb-2">以下条件尚未满足：</p>
      <ul className="space-y-1">
        {error.missing_requirements.map((item, i) => (
          <li key={i} className="text-sm text-red-300 flex items-start gap-2">
            <span className="text-red-400 mt-1">&#x2716;</span>
            <span>{MISSING_LABELS[item] || item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
