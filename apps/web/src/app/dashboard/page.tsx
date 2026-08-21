'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { getSupervisorDashboard, getTechnicianDashboard, getIntelligenceOverview } from '@/lib/api';
import { Wrench, Clock, CheckCircle, AlertTriangle, TrendingUp, ArrowRight, Activity, HeartPulse, ShieldAlert, Sparkles } from 'lucide-react';
import { STATUS_LABELS, PRIORITY_LABELS } from '@/lib/types';

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  const [intelligence, setIntelligence] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    if (user.role === 'technician') {
      getTechnicianDashboard().then(setData).catch(console.error).finally(() => setLoading(false));
      return;
    }
    const intelligenceRequest = typeof getIntelligenceOverview === 'function'
      ? getIntelligenceOverview().catch(() => null)
      : Promise.resolve(null);
    Promise.all([getSupervisorDashboard(), intelligenceRequest])
      .then(([dashboardData, intelligenceData]) => {
        setData(dashboardData);
        setIntelligence(intelligenceData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
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
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-primary-400 text-xs font-semibold tracking-[0.18em] uppercase mb-1">
            <Sparkles size={13} /> AI-Powered Maintenance
          </div>
          <h1 className="text-2xl font-bold">智能运维驾驶舱</h1>
          <p className="text-sm text-muted mt-1">运维管理仪表盘</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          Mock 设备网关在线 · AI 建议需人工复核
        </div>
      </div>
      {intelligence && (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <PlatformMetric icon={<CpuIcon />} label="设备资产" value={intelligence.total_equipment} suffix="台" tone="blue" onClick={() => router.push('/equipment')} />
          <PlatformMetric icon={<HeartPulse size={18} />} label="平均健康分" value={intelligence.average_health_score} suffix="/100" tone="green" />
          <PlatformMetric icon={<Activity size={18} />} label="实时异常" value={intelligence.active_anomalies} suffix="项" tone="orange" onClick={() => router.push('/monitoring')} />
          <PlatformMetric icon={<ShieldAlert size={18} />} label="高风险设备" value={intelligence.high_risk_equipment} suffix="台" tone="red" onClick={() => router.push('/predictive-maintenance')} />
          <PlatformMetric icon={<Clock size={18} />} label="待处理操作" value={intelligence.pending_approvals} suffix="项" tone="yellow" onClick={() => router.push('/approvals')} />
          <PlatformMetric icon={<TrendingUp size={18} />} label="已生成遥测" value={intelligence.simulator?.generated_points || 0} suffix="点" tone="purple" />
        </div>
      )}
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
      {intelligence && (
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
          <div className="card xl:col-span-3">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-semibold">设备实时状态</h2>
                <p className="text-xs text-muted mt-1">电机及轴承关键指标最新快照</p>
              </div>
              <button className="text-sm text-primary-400 flex items-center gap-1" onClick={() => router.push('/monitoring')}>进入监测 <ArrowRight size={14} /></button>
            </div>
            {intelligence.latest_telemetry?.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted border-b border-card-border">
                    <tr><th className="text-left py-2">设备</th><th className="text-right">振动</th><th className="text-right">温度</th><th className="text-right">电流</th><th className="text-right">负载</th><th className="text-right">状态</th></tr>
                  </thead>
                  <tbody>
                    {intelligence.latest_telemetry.slice(0, 6).map((item: any) => (
                      <tr key={item.id} className="border-b border-card-border/50 hover:bg-white/[0.03]">
                        <td className="py-3"><div className="font-medium">{item.equipment_name}</div><div className="text-xs text-muted font-mono">{item.equipment_code}</div></td>
                        <td className="text-right font-mono">{formatMetric(item.vibration_rms, 'mm/s')}</td>
                        <td className="text-right font-mono">{formatMetric(item.bearing_temperature, '°C')}</td>
                        <td className="text-right font-mono">{formatMetric(item.motor_current, 'A')}</td>
                        <td className="text-right font-mono">{formatMetric(item.load_ratio, '%')}</td>
                        <td className="text-right"><span className={`badge ${item.is_anomaly ? 'bg-red-500/20 text-red-300' : 'bg-green-500/20 text-green-300'}`}>{item.is_anomaly ? '异常' : '正常'}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-sm text-muted py-8 text-center">启动设备仿真后将在此显示实时遥测</p>}
          </div>
          <div className="card xl:col-span-2">
            <div className="flex items-center justify-between mb-4">
              <div><h2 className="font-semibold">风险预测</h2><p className="text-xs text-muted mt-1">确定性规则模型 · Mock</p></div>
              <button className="text-sm text-primary-400" onClick={() => router.push('/predictive-maintenance')}>查看全部</button>
            </div>
            <div className="space-y-3">
              {intelligence.risk_predictions?.slice(0, 4).map((prediction: any) => (
                <div key={prediction.id} className="rounded-lg border border-card-border bg-black/10 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div><div className="text-sm font-medium">{prediction.equipment_name}</div><div className="text-xs text-muted mt-1">{failureModeLabel(prediction.failure_mode)}</div></div>
                    <RiskBadge level={prediction.risk_level} />
                  </div>
                  <div className="mt-3 flex items-center justify-between text-xs">
                    <span className="text-muted">失效概率</span><span className="font-mono">{Math.round(prediction.probability * 100)}%</span>
                    <span className="text-muted">剩余寿命</span><span className="font-mono">{prediction.remaining_useful_life_hours}h</span>
                  </div>
                </div>
              ))}
              {!intelligence.risk_predictions?.length && <p className="text-sm text-muted py-6 text-center">暂无风险预测</p>}
            </div>
          </div>
        </div>
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

function CpuIcon() {
  return <Wrench size={18} />;
}

function PlatformMetric({ icon, label, value, suffix, tone, onClick }: any) {
  const tones: Record<string, string> = {
    blue: 'text-blue-300 bg-blue-500/10 border-blue-500/20',
    green: 'text-green-300 bg-green-500/10 border-green-500/20',
    orange: 'text-orange-300 bg-orange-500/10 border-orange-500/20',
    red: 'text-red-300 bg-red-500/10 border-red-500/20',
    yellow: 'text-yellow-300 bg-yellow-500/10 border-yellow-500/20',
    purple: 'text-purple-300 bg-purple-500/10 border-purple-500/20',
  };
  return (
    <button type="button" onClick={onClick} className={`text-left rounded-xl border p-3 transition-transform hover:-translate-y-0.5 ${tones[tone] || tones.blue}`}>
      <div className="flex items-center gap-2 text-xs opacity-80">{icon}{label}</div>
      <div className="mt-2 text-xl font-bold text-white">{value}<span className="text-xs font-normal text-muted ml-1">{suffix}</span></div>
    </button>
  );
}

function RiskBadge({ level }: { level: string }) {
  const styles: Record<string, string> = {
    low: 'bg-green-500/15 text-green-300',
    medium: 'bg-yellow-500/15 text-yellow-300',
    high: 'bg-orange-500/15 text-orange-300',
    critical: 'bg-red-500/15 text-red-300',
  };
  const labels: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险', critical: '紧急' };
  return <span className={`badge ${styles[level] || styles.medium}`}>{labels[level] || level}</span>;
}

function failureModeLabel(mode: string) {
  const labels: Record<string, string> = {
    bearing_wear: '轴承磨损',
    bearing_overheat: '轴承过热',
    motor_overload: '电机过载',
    rotor_unbalance: '转子不平衡',
    shaft_misalignment: '轴系不对中',
    insufficient_lubrication: '润滑不足',
    voltage_abnormal: '电压异常',
    sensor_abnormal: '传感器异常',
    unknown_anomaly: '未知复合异常',
  };
  return labels[mode] || mode;
}

function formatMetric(value: number | null | undefined, unit: string) {
  return value == null ? '--' : `${value} ${unit}`;
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
  return <span className={`badge ${cls[priority] || ''}`}>{PRIORITY_LABELS[priority] || priority}</span>;
}
