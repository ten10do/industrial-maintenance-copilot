'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, Gauge, Pause, Play, RefreshCcw, RotateCcw, Thermometer, Zap,
} from 'lucide-react';
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import toast from 'react-hot-toast';
import { useAuth } from '@/lib/auth';
import {
  configureSimulator,
  getEquipmentIntelligence,
  getSimulatorStatus,
  listEquipment,
  pauseSimulator,
  resetSimulator,
  startSimulator,
  tickSimulator,
} from '@/lib/api';

const SCENARIOS = [
  ['normal', '正常运行'],
  ['temperature_rise', '温度缓慢上升'],
  ['vibration_spike', '振动突然升高'],
  ['current_overload', '电流持续过载'],
  ['bearing_wear', '轴承磨损趋势'],
  ['voltage_fluctuation', '电压波动'],
  ['sensor_disconnect', '传感器断连'],
  ['composite_anomaly', '多指标复合异常'],
] as const;

export default function MonitoringPage() {
  const { user } = useAuth();
  const [equipment, setEquipment] = useState<any[]>([]);
  const [selectedEquipmentId, setSelectedEquipmentId] = useState<number | null>(null);
  const [deviceCount, setDeviceCount] = useState(1);
  const [scenario, setScenario] = useState('normal');
  const [intervalSeconds, setIntervalSeconds] = useState(5);
  const [seed, setSeed] = useState(20260731);
  const [simulator, setSimulator] = useState<any>(null);
  const [intelligence, setIntelligence] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const canControl = user?.role === 'admin' || user?.role === 'supervisor';

  const refresh = useCallback(async () => {
    const [status, detail] = await Promise.all([
      getSimulatorStatus().catch(() => null),
      selectedEquipmentId ? getEquipmentIntelligence(selectedEquipmentId, 80).catch(() => null) : Promise.resolve(null),
    ]);
    if (status) setSimulator(status);
    if (detail) setIntelligence(detail);
  }, [selectedEquipmentId]);

  useEffect(() => {
    listEquipment({ page_size: '100' }).then((data) => {
      setEquipment(data.items);
      if (data.items.length) setSelectedEquipmentId((current) => current || data.items[0].id);
    }).catch((error) => toast.error(error.message));
    getSimulatorStatus().then(setSimulator).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const selectedEquipment = equipment.find((item) => item.id === selectedEquipmentId);
  const latest = intelligence?.telemetry?.[intelligence.telemetry.length - 1];
  const chartData = useMemo(() => (intelligence?.telemetry || []).map((item: any) => ({
    ...item,
    time: new Date(item.collected_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  })), [intelligence]);

  const act = async (action: () => Promise<any>, success: string) => {
    setBusy(true);
    try {
      const result = await action();
      if (result?.running !== undefined) setSimulator(result);
      toast.success(success);
      await refresh();
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const configure = () => act(async () => {
    const startIndex = Math.max(0, equipment.findIndex((item) => item.id === selectedEquipmentId));
    const ids = equipment.slice(startIndex, startIndex + deviceCount).map((item) => item.id);
    if (!ids.length) throw new Error('请选择仿真设备');
    return configureSimulator({
      equipment_ids: ids,
      interval_seconds: intervalSeconds,
      scenario,
      seed,
      auto_create_work_orders: true,
    });
  }, '仿真参数已配置');

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <div className="text-xs tracking-[0.18em] uppercase text-primary-400 font-semibold mb-1">Digital Twin Lab</div>
          <h1 className="text-2xl font-bold">实时状态监测与设备仿真</h1>
          <p className="text-sm text-muted mt-1">工业电机与轴承系统 · 纯软件 Mock · 固定随机种子可复现</p>
        </div>
        <div className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs border ${simulator?.running ? 'border-green-500/30 bg-green-500/10 text-green-300' : 'border-card-border text-muted'}`}>
          <span className={`w-2 h-2 rounded-full ${simulator?.running ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
          {simulator?.running ? '仿真运行中' : '仿真已暂停'} · {simulator?.generated_points || 0} 点
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        <section className="card xl:col-span-1 space-y-4">
          <div><h2 className="font-semibold">仿真控制台</h2><p className="text-xs text-muted mt-1">主管配置场景，工程师可查看数据</p></div>
          <label className="block text-xs text-muted">起始设备
            <select value={selectedEquipmentId || ''} onChange={(event) => setSelectedEquipmentId(Number(event.target.value))} className="w-full mt-1.5">
              {equipment.map((item) => <option value={item.id} key={item.id}>{item.code} · {item.name}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs text-muted">设备数量
              <input type="number" min={1} max={Math.min(10, equipment.length || 1)} value={deviceCount} onChange={(event) => setDeviceCount(Number(event.target.value))} className="w-full mt-1.5" />
            </label>
            <label className="block text-xs text-muted">间隔（秒）
              <input type="number" min={0.2} step={0.2} value={intervalSeconds} onChange={(event) => setIntervalSeconds(Number(event.target.value))} className="w-full mt-1.5" />
            </label>
          </div>
          <label className="block text-xs text-muted">故障场景
            <select value={scenario} onChange={(event) => setScenario(event.target.value)} className="w-full mt-1.5">
              {SCENARIOS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="block text-xs text-muted">随机种子
            <input type="number" value={seed} onChange={(event) => setSeed(Number(event.target.value))} className="w-full mt-1.5 font-mono" />
          </label>
          <button disabled={!canControl || busy} onClick={configure} className="btn btn-outline btn-block"><RefreshCcw size={15} />应用配置</button>
          <div className="grid grid-cols-2 gap-2">
            <button disabled={!canControl || busy} onClick={() => act(startSimulator, '仿真已启动')} className="btn btn-primary"><Play size={15} />启动</button>
            <button disabled={!canControl || busy} onClick={() => act(pauseSimulator, '仿真已暂停')} className="btn btn-outline"><Pause size={15} />暂停</button>
            <button disabled={!canControl || busy} onClick={() => act(tickSimulator, '已生成一批遥测')} className="btn btn-outline"><Activity size={15} />单步</button>
            <button disabled={!canControl || busy} onClick={() => act(resetSimulator, '仿真状态已重置')} className="btn btn-outline"><RotateCcw size={15} />重置</button>
          </div>
          {!canControl && <p className="text-xs text-yellow-300 bg-yellow-500/10 rounded-lg p-3">仿真控制仅限主管和管理员；当前为只读监测。</p>}
        </section>

        <section className="xl:col-span-3 space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <MetricCard icon={<Gauge size={17} />} label="振动 RMS" value={format(latest?.vibration_rms)} unit="mm/s" warning={(latest?.vibration_rms || 0) > 4.5} />
            <MetricCard icon={<Thermometer size={17} />} label="轴承温度" value={format(latest?.bearing_temperature)} unit="°C" warning={(latest?.bearing_temperature || 0) > 75} />
            <MetricCard icon={<Zap size={17} />} label="电机电流" value={format(latest?.motor_current)} unit="A" warning={(latest?.motor_current || 0) > 27} />
            <MetricCard icon={<Activity size={17} />} label="负载率" value={format(latest?.load_ratio)} unit="%" warning={(latest?.load_ratio || 0) > 100} />
          </div>
          <div className="card min-h-[390px]">
            <div className="flex items-center justify-between mb-4">
              <div><h2 className="font-semibold">{selectedEquipment?.name || '设备'}关键趋势</h2><p className="text-xs text-muted mt-1">振动、温度、电流与负载归一视图</p></div>
              {intelligence && <HealthPill score={intelligence.health_score} risk={intelligence.risk_level} />}
            </div>
            {chartData.length ? (
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid stroke="#334155" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="time" stroke="#64748b" fontSize={11} tickLine={false} />
                    <YAxis stroke="#64748b" fontSize={11} tickLine={false} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8 }} />
                    <Legend />
                    <Line type="monotone" dataKey="vibration_rms" name="振动 mm/s" stroke="#38bdf8" dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="bearing_temperature" name="温度 °C" stroke="#fb923c" dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="motor_current" name="电流 A" stroke="#a78bfa" dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="load_ratio" name="负载 %" stroke="#34d399" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="h-[300px] flex flex-col items-center justify-center text-muted"><Activity size={36} className="mb-3 opacity-40" /><p>配置设备并启动仿真以生成遥测</p></div>}
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="card">
          <h2 className="font-semibold mb-3">关联传感器</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {intelligence?.sensors?.map((sensor: any) => (
              <div key={sensor.id} className="rounded-lg bg-black/10 border border-card-border p-3 flex items-center justify-between">
                <div><div className="text-sm">{sensor.name}</div><div className="text-[11px] font-mono text-muted">{sensor.code}</div></div>
                <div className="text-right"><div className="font-mono text-sm">{format(sensor.latest_value)} {sensor.unit}</div><div className={`text-[11px] ${sensor.status === 'online' ? 'text-green-400' : 'text-red-400'}`}>{sensor.status === 'online' ? '在线' : '离线'}</div></div>
              </div>
            ))}
            {!intelligence?.sensors?.length && <p className="text-sm text-muted">暂无传感器数据</p>}
          </div>
        </section>
        <section className="card">
          <h2 className="font-semibold mb-3">实时异常</h2>
          <div className="space-y-2">
            {intelligence?.anomalies?.slice(0, 5).map((event: any) => (
              <div key={event.id} className="rounded-lg bg-red-500/5 border border-red-500/20 p-3">
                <div className="flex items-center justify-between"><span className="text-sm font-medium">{event.title}</span><span className="badge bg-red-500/15 text-red-300">{event.severity}</span></div>
                <p className="text-xs text-muted mt-2">{event.diagnosis_summary}</p>
              </div>
            ))}
            {!intelligence?.anomalies?.length && <p className="text-sm text-muted">当前未检测到异常</p>}
          </div>
        </section>
      </div>
    </div>
  );
}

function MetricCard({ icon, label, value, unit, warning }: any) {
  return (
    <div className={`rounded-xl border p-4 ${warning ? 'border-red-500/30 bg-red-500/10' : 'border-card-border bg-card'}`}>
      <div className={`flex items-center gap-2 text-xs ${warning ? 'text-red-300' : 'text-muted'}`}>{icon}{label}</div>
      <div className="mt-2 text-2xl font-bold font-mono">{value}<span className="text-xs text-muted font-normal ml-1">{unit}</span></div>
    </div>
  );
}

function HealthPill({ score, risk }: { score: number; risk: string }) {
  return <div className="rounded-full border border-card-border px-3 py-1 text-xs">健康分 <strong className={score < 70 ? 'text-red-300' : score < 85 ? 'text-yellow-300' : 'text-green-300'}>{score}</strong> · {risk}</div>;
}

function format(value: number | null | undefined) {
  return value == null ? '--' : Number(value).toFixed(1);
}
