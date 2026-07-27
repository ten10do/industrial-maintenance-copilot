'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { getSupervisorDashboard, getTechnicianDashboard } from '@/lib/api';
import { Wrench, Clock, CheckCircle, AlertTriangle, TrendingUp, ArrowRight } from 'lucide-react';

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    const fetcher = user.role === 'technician' ? getTechnicianDashboard : getSupervisorDashboard;
    fetcher().then(setData).catch(console.error).finally(() => setLoading(false));
  }, [user]);

  if (loading) return <div className="text-muted p-6">加载中...</div>;
  if (!data) return <div className="text-muted p-6">暂无数据</div>;

  if (user?.role === 'technician') {
    const d = data;
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-xl font-bold">维修工作台</h1>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={<Wrench />} label="分配给我" value={d.assigned_to_me} color="blue" />
          <StatCard icon={<Clock />} label="今日待处理" value={d.today_todo} color="yellow" />
          <StatCard icon={<AlertTriangle />} label="高优先级" value={d.high_priority} color="red" />
          <StatCard icon={<TrendingUp />} label="已超时" value={d.overdue} color="red" />
        </div>
        <div className="flex gap-3">
          <button onClick={() => router.push('/fault-reports/new')} className="btn btn-primary btn-lg flex-1">快速故障上报</button>
          <button onClick={() => router.push('/work-orders?mine=true')} className="btn btn-outline btn-lg flex-1">我的工单</button>
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">待处理工单</h2>
            <button onClick={() => router.push('/work-orders?mine=true')} className="text-sm text-primary-400 flex items-center gap-1">全部 <ArrowRight size={14} /></button>
          </div>
          {d.my_work_orders?.length ? (
            <div className="space-y-2">
              {d.my_work_orders.slice(0, 5).map((wo: any) => (
                <div key={wo.id} className="flex items-center justify-between p-3 rounded-lg bg-white/5 cursor-pointer hover:bg-white/10" onClick={() => router.push(`/work-orders/${wo.id}`)}>
                  <div>
                    <div className="text-sm font-medium">{wo.title}</div>
                    <div className="text-xs text-muted">{wo.code} - {wo.equipment_name}</div>
                  </div>
                  <StatusBadge status={wo.status} />
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-muted">暂无待处理工单</p>}
        </div>
      </div>
    );
  }

  // Supervisor / Admin Dashboard
  const d = data;
  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <h1 className="text-xl font-bold">运维管理仪表盘</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <StatCard icon={<Clock />} label="待分派" value={d.pending_dispatch} color="yellow" onClick={() => router.push('/work-orders?status=pending_dispatch')} />
        <StatCard icon={<Wrench />} label="处理中" value={d.in_progress} color="blue" onClick={() => router.push('/work-orders?status=in_progress')} />
        <StatCard icon={<CheckCircle />} label="待验收" value={d.pending_acceptance} color="green" onClick={() => router.push('/work-orders?status=pending_acceptance')} />
        <StatCard icon={<AlertTriangle />} label="已超时" value={d.overdue} color="red" onClick={() => router.push('/work-orders?status=overdue')} />
        <StatCard icon={<AlertTriangle />} label="今日新增" value={d.today_new_faults} color="orange" />
        <StatCard icon={<CheckCircle />} label="今日完成" value={d.today_completed} color="green" />
      </div>
      {d.avg_repair_hours != null && (
        <p className="text-sm text-muted">平均修复时长: {d.avg_repair_hours} 小时</p>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="font-semibold mb-3">按优先级分布</h2>
          <div className="space-y-2">
            {d.by_priority?.map((p: any) => (
              <div key={p.priority} className="flex items-center justify-between">
                <span><PriorityBadge priority={p.priority} /></span>
                <div className="flex items-center gap-2">
                  <div className="w-32 h-2 rounded-full bg-white/10">
                    <div className={`h-full rounded-full ${p.priority === 'P1' ? 'bg-red-500' : p.priority === 'P2' ? 'bg-yellow-500' : p.priority === 'P3' ? 'bg-blue-500' : 'bg-gray-500'}`} style={{ width: `${Math.min((p.count / Math.max(...d.by_priority.map((x: any) => x.count || 1))) * 100, 100)}%` }} />
                  </div>
                  <span className="text-sm font-mono">{p.count}</span>
                </div>
              </div>
            )) || <p className="text-sm text-muted">无数据</p>}
          </div>
        </div>
        <div className="card">
          <h2 className="font-semibold mb-3">按设备类型</h2>
          <div className="space-y-2">
            {d.by_equipment_type?.map((t: any) => (
              <div key={t.equipment_type} className="flex items-center justify-between text-sm">
                <span>{t.equipment_type}</span>
                <span className="font-mono">{t.count}</span>
              </div>
            )) || <p className="text-sm text-muted">无数据</p>}
          </div>
        </div>
      </div>
      <div className="card">
        <h2 className="font-semibold mb-3">最近工单</h2>
        <div className="space-y-1">
          {d.recent_work_orders?.map((wo: any) => (
            <div key={wo.id} className="flex items-center justify-between p-2 rounded hover:bg-white/5 cursor-pointer text-sm" onClick={() => router.push(`/work-orders/${wo.id}`)}>
              <span className="text-muted w-20">{wo.code}</span>
              <span className="flex-1 truncate">{wo.title}</span>
              <StatusBadge status={wo.status} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, color, onClick }: any) {
  const colors: any = { blue: 'border-primary/30', yellow: 'border-warning/30', red: 'border-red-500/30', green: 'border-green-500/30', orange: 'border-orange-500/30' };
  return (
    <div className={`card cursor-pointer hover:bg-white/5 transition-colors border-l-4 ${colors[color] || 'border-card-border'}`} onClick={onClick}>
      <div className="text-sm text-muted mb-1">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: any = {
    pending_dispatch: 'bg-gray-500/20 text-gray-400',
    assigned: 'bg-blue-500/20 text-blue-400',
    accepted: 'bg-purple-500/20 text-purple-400',
    in_progress: 'bg-yellow-500/20 text-yellow-400',
    pending_acceptance: 'bg-green-500/20 text-green-400',
    completed: 'bg-green-600/20 text-green-500',
    cancelled: 'bg-gray-500/20 text-gray-500',
    returned: 'bg-red-500/20 text-red-400',
    paused: 'bg-gray-500/20 text-gray-400',
  };
  const labels: any = {
    pending_dispatch: '待分派', assigned: '已分派', accepted: '已接受', in_progress: '处理中',
    pending_acceptance: '待验收', completed: '已完成', cancelled: '已取消', returned: '已退回', paused: '暂停',
  };
  return <span className={`badge ${colors[status] || ''}`}>{labels[status] || status}</span>;
}

function PriorityBadge({ priority }: { priority: string }) {
  const cls: any = { P1: 'badge-p1', P2: 'badge-p2', P3: 'badge-p3', P4: 'badge-p4' };
  return <span className={`badge ${cls[priority] || ''}`}>{priority}</span>;
}
