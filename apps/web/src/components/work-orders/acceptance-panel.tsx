'use client';

import { useState } from 'react';
import { approveWorkOrder, rejectWorkOrder } from '@/lib/api';

interface Props {
  workOrderId: number;
  onRefresh: () => void;
}

export default function AcceptancePanel({ workOrderId, onRefresh }: Props) {
  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);

  async function handleApprove() {
    setLoading('approve');
    setError('');
    try {
      await approveWorkOrder(workOrderId);
      onRefresh();
    } catch (e: any) {
      if (e.message?.includes('已完成验收')) {
        setError('该工单已完成验收');
        onRefresh();
      } else {
        setError(e.message || '验收失败');
      }
    } finally {
      setLoading('');
    }
  }

  async function handleReject() {
    if (!rejectReason.trim()) {
      setError('请填写退回原因');
      return;
    }
    setLoading('reject');
    setError('');
    try {
      await rejectWorkOrder(workOrderId, rejectReason.trim());
      onRefresh();
    } catch (e: any) {
      setError(e.message || '退回失败');
    } finally {
      setLoading('');
    }
  }

  return (
    <div className="card p-4 space-y-3" data-testid="acceptance-panel">
      <h3 className="text-lg font-semibold">验收确认</h3>

      {error && <p className="text-red-400 text-xs">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={handleApprove}
          disabled={loading !== ''}
          className="btn btn-primary btn-sm"
          data-testid="approve-work-order-button"
        >
          {loading === 'approve' ? '处理中...' : '验收通过'}
        </button>
        <button
          onClick={() => setShowReject(!showReject)}
          disabled={loading !== ''}
          className="btn btn-sm btn-outline border-red-500/30 text-red-400"
          data-testid="reject-work-order-toggle"
        >
          退回修改
        </button>
      </div>

      {showReject && (
        <div className="space-y-2 pt-2 border-t border-white/5">
          <textarea
            placeholder="请填写退回原因..."
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            className="input w-full h-20 text-sm"
            data-testid="reject-reason-input"
          />
          <div className="flex gap-2">
            <button
              onClick={handleReject}
              disabled={loading !== ''}
              className="btn btn-sm btn-outline border-red-500/30 text-red-400"
              data-testid="confirm-reject-button"
            >
              {loading === 'reject' ? '处理中...' : '确认退回'}
            </button>
            <button
              onClick={() => setShowReject(false)}
              disabled={loading !== ''}
              className="btn btn-sm btn-ghost"
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
