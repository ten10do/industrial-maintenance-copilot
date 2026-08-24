'use client';

import { useCallback, useEffect, useState } from 'react';
import { BellRing, ShieldCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '@/lib/auth';
import { acknowledgeAlarm, listAlarms } from '@/lib/api';
import type { IndustrialAlarm } from '@/lib/types';

const SEVERITY_STYLES: Record<string, string> = {
  CRITICAL: 'bg-red-500/15 text-red-300',
  WARNING: 'bg-yellow-500/15 text-yellow-300',
};

export default function AlarmsPage() {
  const { user } = useAuth();
  const [alarms, setAlarms] = useState<IndustrialAlarm[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState('active');
  const [busy, setBusy] = useState(false);
  const canControl = user?.role === 'admin' || user?.role === 'supervisor';

  const refresh = useCallback(async () => {
    const data = await listAlarms(statusFilter ? { status: statusFilter } : undefined).catch(() => null);
    if (data) {
      setAlarms(data.items);
      setTotal(data.total);
    }
  }, [statusFilter]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const ack = async (alarm: IndustrialAlarm) => {
    setBusy(true);
    try {
      await acknowledgeAlarm(alarm.id);
      toast.success('报警已确认');
      await refresh();
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6" data-testid="alarms-page">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <div className="text-xs tracking-[0.18em] uppercase text-primary-400 font-semibold mb-1">Industrial Alarm Center</div>
          <h1 className="text-2xl font-bold">工业报警中心</h1>
          <p className="text-sm text-muted mt-1">
            OPC UA Alarm 语义（simulated subscription workflow）· 报警由只读事件流水线派生
          </p>
        </div>
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          className="text-sm"
          aria-label="报警筛选"
        >
          <option value="">全部</option>
          <option value="active">活动</option>
          <option value="acknowledged">已确认</option>
          <option value="cleared">已解除</option>
        </select>
      </div>

      <div className="card overflow-x-auto">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold flex items-center gap-2"><BellRing size={16} className="text-yellow-300" />报警列表</h2>
          <span className="text-xs text-muted">{total} 条记录</span>
        </div>
        {alarms.length ? (
          <table className="w-full text-sm" data-testid="alarms-table">
            <thead>
              <tr className="text-left text-xs text-muted border-b border-card-border">
                <th className="py-2 pr-3">级别</th>
                <th className="py-2 pr-3">设备</th>
                <th className="py-2 pr-3">消息</th>
                <th className="py-2 pr-3">时间</th>
                <th className="py-2 pr-3">状态</th>
                <th className="py-2 pr-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {alarms.map((alarm) => (
                <tr key={alarm.id} className="border-b border-card-border/50 last:border-0">
                  <td className="py-2 pr-3">
                    <span className={`badge ${SEVERITY_STYLES[alarm.severity] || 'bg-gray-500/15 text-gray-300'}`}>{alarm.severity}</span>
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">#{alarm.equipment_id}</td>
                  <td className="py-2 pr-3">{alarm.message}</td>
                  <td className="py-2 pr-3 text-xs text-muted">{formatTime(alarm.created_at)}</td>
                  <td className="py-2 pr-3 text-xs">
                    {alarm.cleared_at ? (
                      <span className="text-green-400">已解除 {formatTime(alarm.cleared_at)}</span>
                    ) : (
                      <span className="text-red-400">活动中</span>
                    )}
                    {alarm.acknowledged && <span className="ml-2 badge bg-primary-500/15 text-primary-300">已确认</span>}
                  </td>
                  <td className="py-2 pr-3">
                    {!alarm.acknowledged && (
                      <button disabled={busy || !canControl} onClick={() => ack(alarm)} className="btn btn-outline btn-sm">
                        确认
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted py-6 text-center">当前没有工业报警记录。</p>
        )}
      </div>

      <p className="text-xs text-muted flex items-start gap-1.5">
        <ShieldCheck size={14} className="mt-0.5 shrink-0 text-green-400" />
        报警来源于只读 OPC UA 订阅流水线；确认操作仅更新平台内记录，不向设备写入任何内容。
      </p>
    </div>
  );
}

function formatTime(value: string | null | undefined) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
