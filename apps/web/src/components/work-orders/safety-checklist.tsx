'use client';

import { useEffect, useState } from 'react';
import { updateChecklistItem } from '@/lib/api';
import { ChecklistItem, CHECKLIST_CATEGORY_LABELS } from '@/lib/types';

interface Props {
  workOrderId: number;
  items: ChecklistItem[];
  canEdit: boolean;
  onRefresh: () => void | Promise<void>;
}

const CATEGORY_ORDER = ['safety', 'diagnosis', 'repair', 'testing'];
const CATEGORY_COLORS: Record<string, string> = {
  safety: 'text-yellow-400 border-yellow-400/30',
  diagnosis: 'text-blue-400 border-blue-400/30',
  repair: 'text-purple-400 border-purple-400/30',
  testing: 'text-green-400 border-green-400/30',
};

export default function SafetyChecklist({ workOrderId, items, canEdit, onRefresh }: Props) {
  const [loadingId, setLoadingId] = useState<number | null>(null);
  const [completedById, setCompletedById] = useState<Record<number, boolean>>({});

  useEffect(() => {
    setCompletedById(Object.fromEntries(items.map(item => [item.id, item.is_completed])));
  }, [items]);

  // Group items by category
  const grouped: Record<string, ChecklistItem[]> = {};
  for (const item of items) {
    const cat = item.category || 'repair';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(item);
  }

  async function handleToggle(item: ChecklistItem) {
    if (!canEdit || loadingId !== null) return;
    const previous = completedById[item.id] ?? item.is_completed;
    const next = !previous;
    setCompletedById(current => ({ ...current, [item.id]: next }));
    setLoadingId(item.id);
    try {
      await updateChecklistItem(workOrderId, item.id, {
        is_completed: next,
      });
      await onRefresh();
    } catch {
      setCompletedById(current => ({ ...current, [item.id]: previous }));
    } finally {
      setLoadingId(null);
    }
  }

  const isCompleted = (item: ChecklistItem) => completedById[item.id] ?? item.is_completed;
  const completed = items.filter(isCompleted).length;
  const required = items.filter(i => i.is_required).length;
  const progress = required > 0 ? Math.round((completed / required) * 100) : 0;

  return (
    <div className="space-y-4" data-testid="safety-checklist">
      {/* Progress bar */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted">整体进度</span>
        <div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-xs text-muted">{completed}/{items.length}</span>
      </div>

      {/* Grouped by category */}
      {CATEGORY_ORDER.map(cat => {
        const catItems = grouped[cat];
        if (!catItems || catItems.length === 0) return null;
        const catCompleted = catItems.filter(isCompleted).length;
        const catRequired = catItems.filter(i => i.is_required).length;
        const isSafety = cat === 'safety';

        return (
          <div key={cat} data-testid={`checklist-group-${cat}`}>
            <div className="flex items-center gap-2 mb-2">
              <h4 className={`text-sm font-semibold ${CATEGORY_COLORS[cat]?.split(' ')[0] || 'text-muted'}`}>
                {CHECKLIST_CATEGORY_LABELS[cat] || cat}
                {isSafety && <span className="text-red-400 ml-1">（必做）</span>}
              </h4>
              <span className="text-xs text-muted">
                {catCompleted}/{catItems.length}
              </span>
            </div>

            {/* Safety prohibition warning for safety category */}
            {isSafety && (
              <div className="mb-2 p-2 rounded bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                严禁带电操作、短接保护装置、绕过安全联锁。所有安全项必须逐一确认。
              </div>
            )}

            <div className="space-y-1">
              {catItems.map(item => {
                const itemCompleted = isCompleted(item);
                return (
                <label
                  key={item.id}
                  className={`flex items-start gap-2 p-2 rounded cursor-pointer transition-colors ${
                    itemCompleted ? 'bg-green-500/10' : 'bg-white/5 hover:bg-white/10'
                  } ${!canEdit ? 'opacity-60 cursor-default' : ''}`}
                  data-testid={`checklist-item-${item.id}`}
                >
                  <input
                    type="checkbox"
                    checked={itemCompleted}
                    onChange={() => handleToggle(item)}
                    disabled={!canEdit || loadingId === item.id}
                    className="mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1">
                      {item.is_required && <span className="text-red-400 text-xs">*</span>}
                      <span className={`text-sm ${itemCompleted ? 'line-through text-muted' : ''}`}>
                        {item.content}
                      </span>
                    </div>
                    {item.remark && <p className="text-xs text-muted mt-0.5">{item.remark}</p>}
                    {item.completed_at && (
                      <p className="text-xs text-green-400 mt-0.5">
                        已完成 · {new Date(item.completed_at).toLocaleString('zh-CN')}
                      </p>
                    )}
                  </div>
                  {loadingId === item.id && <span className="text-xs text-muted animate-pulse">...</span>}
                </label>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
