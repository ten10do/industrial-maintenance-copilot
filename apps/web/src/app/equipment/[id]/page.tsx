'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { getEquipment, getEquipmentWorkOrders, copilotEquipmentHistory } from '@/lib/api';
import { Bot, QrCode } from 'lucide-react';
import toast from 'react-hot-toast';

export default function EquipmentDetail() {
  const { id } = useParams();
  const router = useRouter();
  const [eq, setEq] = useState<any>(null);
  const [wos, setWos] = useState<any[]>([]);
  const [history, setHistory] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetch = async () => {
    try {
      const [d, w, h] = await Promise.all([getEquipment(Number(id)), getEquipmentWorkOrders(Number(id)), copilotEquipmentHistory(Number(id)).catch(() => null)]);
      setEq(d);
      setWos(w);
      setHistory(h);
    } catch (e: any) { toast.error(e.message); } finally { setLoading(false); }
  };

  useEffect(() => { fetch(); }, [id]);

  if (loading) return <div className="text-muted p-6">加载中...</div>;
  if (!eq) return <div className="text-muted p-6">设备不存在</div>;

  const statusLabel: any = { running: '运行中', fault: '故障', under_repair: '维修中', stopped: '停机', scrapped: '已报废' };
  const riskLabel: any = { low: '低', medium: '中', high: '高', critical: '紧急' };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-xl font-bold">{eq.name}</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="font-semibold mb-3">基本属性</h2>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <Info label="设备编号" value={eq.code} />
            <Info label="设备类型" value={eq.equipment_type_name} />
            <Info label="状态" value={statusLabel[eq.status]} />
            <Info label="风险等级" value={riskLabel[eq.risk_level]} />
            <Info label="厂区" value={eq.plant} />
            <Info label="产线" value={eq.production_line} />
            <Info label="位置" value={eq.location} />
            <Info label="制造商" value={eq.manufacturer} />
            <Info label="型号" value={eq.model} />
            <Info label="序列号" value={eq.serial_number} />
            <Info label="投产日期" value={eq.commissioning_date} />
            <Info label="负责人" value={eq.responsible_person_name} />
            <Info label="最近维修" value={eq.last_maintenance_at} />
          </div>
          {eq.remarks && <div className="mt-2 text-sm text-muted">备注: {eq.remarks}</div>}
        </div>
        <div className="card">
          <h2 className="font-semibold mb-3">设备历史摘要</h2>
          {history ? (
            <div className="space-y-3 text-sm">
              <div><span className="text-muted">总工单数:</span> <span className="font-bold">{history.total_work_orders}</span> {history.avg_repair_hours && <span className="text-muted ml-2">平均修复: {history.avg_repair_hours}h</span>}</div>
              {history.frequent_faults?.length > 0 && <div><div className="text-muted mb-1">高频故障</div>{history.frequent_faults.map((f: any, i: number) => <div key={i} className="flex justify-between text-xs py-0.5"><span>{f.fault?.substring(0, 40)}</span><span className="font-mono text-muted">{f.count}次</span></div>)}</div>}
              {history.repeated_faults?.length > 0 && <div><div className="text-muted mb-1">重复故障</div>{history.repeated_faults.map((f: any, i: number) => <div key={i} className="text-xs">{f.fault?.substring(0, 40)} <span className="font-mono text-muted">({f.count}次)</span></div>)}</div>}
              {history.common_parts?.length > 0 && <div><div className="text-muted mb-1">常见更换部件</div>{history.common_parts.map((p: any, i: number) => <div key={i} className="text-xs">{p.part} <span className="font-mono text-muted">({p.count}次)</span></div>)}</div>}
            </div>
          ) : <p className="text-sm text-muted">暂无历史摘要</p>}
        </div>
      </div>
      <div className="card">
        <h2 className="font-semibold mb-3">历史工单 ({wos.length})</h2>
        {wos.length === 0 ? <p className="text-sm text-muted">暂无工单记录</p> : (
          <div className="space-y-1">
            {wos.map(w => (
              <div key={w.id} className="flex items-center justify-between p-2 rounded hover:bg-white/5 cursor-pointer text-sm" onClick={() => router.push(`/work-orders/${w.id}`)}>
                <div>
                  <span className="font-mono text-xs text-muted mr-2">{w.code}</span>
                  <span>{w.title}</span>
                  {w.root_cause && <span className="text-xs text-muted ml-2">({w.root_cause.substring(0, 30)})</span>}
                </div>
                <span className={`badge ${w.status === 'completed' ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>{w.status === 'completed' ? '已完成' : w.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: any }) {
  return <div><span className="text-muted text-xs">{label}</span><div className="text-sm">{value || '-'}</div></div>;
}
