'use client';

import { useState } from 'react';
import {
  acceptWorkOrder, startWorkOrder, pauseWorkOrder, resumeWorkOrder,
  cancelWorkOrder,
} from '@/lib/api';
import { WorkOrderDetail } from '@/lib/types';

interface Props {
  workOrder: WorkOrderDetail;
  currentUserId: number;
  userRole: string;
  onRefresh: () => void;
}

export default function WorkOrderActions({ workOrder, currentUserId, userRole, onRefresh }: Props) {
  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');

  const isAssignee = workOrder.assignee_id === currentUserId;
  const isSupervisor = userRole === 'admin' || userRole === 'supervisor';
  const canEdit = isAssignee && ['accepted', 'in_progress', 'paused', 'returned'].includes(workOrder.status);
  const canSubmit = isAssignee && workOrder.status === 'in_progress';
  const canApprove = isSupervisor && workOrder.status === 'pending_acceptance';

  async function handleAction(action: string, fn: () => Promise<any>) {
    setLoading(action);
    setError('');
    try {
      await fn();
      onRefresh();
    } catch (e: any) {
      setError(e.message || '操作失败');
    } finally {
      setLoading('');
    }
  }

  const actions: { label: string; action: string; show: boolean; fn: () => Promise<any>; variant: string }[] = [
    {
      label: '接受工单',
      action: 'accept',
      show: workOrder.status === 'assigned' && isAssignee,
      fn: () => acceptWorkOrder(workOrder.id),
      variant: 'btn-primary',
    },
    {
      label: '开始维修',
      action: 'start',
      show: workOrder.status === 'accepted' && isAssignee,
      fn: () => startWorkOrder(workOrder.id),
      variant: 'btn-primary',
    },
    {
      label: '暂停',
      action: 'pause',
      show: workOrder.status === 'in_progress' && isAssignee,
      fn: () => pauseWorkOrder(workOrder.id),
      variant: 'btn-outline',
    },
    {
      label: '继续',
      action: 'resume',
      show: workOrder.status === 'paused' && isAssignee,
      fn: () => resumeWorkOrder(workOrder.id),
      variant: 'btn-primary',
    },
    {
      label: '重新处理',
      action: 'resume',
      show: workOrder.status === 'returned' && isAssignee,
      fn: () => resumeWorkOrder(workOrder.id),
      variant: 'btn-primary',
    },
    {
      label: '取消工单',
      action: 'cancel',
      show: (workOrder.status === 'pending_dispatch' || workOrder.status === 'assigned') && isSupervisor,
      fn: () => cancelWorkOrder(workOrder.id),
      variant: 'btn-outline border-red-500/30 text-red-400',
    },
  ];

  return (
    <div className="flex flex-wrap gap-2" data-testid="work-order-actions">
      {actions.filter(a => a.show).map(a => (
        <button
          key={a.action}
          onClick={() => handleAction(a.action, a.fn)}
          disabled={loading !== ''}
          className={`btn btn-sm ${a.variant}`}
          data-testid={`${a.action}-work-order-button`}
        >
          {loading === a.action ? '处理中...' : a.label}
        </button>
      ))}
      {error && <p className="text-red-400 text-xs w-full mt-1">{error}</p>}
    </div>
  );
}
