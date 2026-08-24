'use client';

import { useCallback, useEffect, useState } from 'react';
import { BellRing, BrainCircuit, ShieldCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '@/lib/auth';
import {
  acknowledgeAlarm,
  analyzeAlarm,
  correlateAlarms,
  createAlarmWorkOrder,
  listAlarms,
  reviewAlarm,
} from '@/lib/api';
import type { AlarmAnalysis, AlarmCorrelateResult, IndustrialAlarm } from '@/lib/types';

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
  const [analyses, setAnalyses] = useState<Record<number, AlarmAnalysis>>({});
  const [selectedAlarmId, setSelectedAlarmId] = useState<number | null>(null);
  const [correlation, setCorrelation] = useState<AlarmCorrelateResult | null>(null);
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

  const runAnalysis = async (alarm: IndustrialAlarm) => {
    setBusy(true);
    setSelectedAlarmId(alarm.id);
    try {
      const analysis = await analyzeAlarm(alarm.id);
      setAnalyses((current) => ({ ...current, [alarm.id]: analysis }));
      toast.success('分析完成（仅供人工决策参考）');
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const runCorrelation = async () => {
    setBusy(true);
    try {
      setCorrelation(await correlateAlarms());
      toast.success('关联分析完成');
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const review = async (action: 'approve' | 'reject' | 'request_more_evidence') => {
    if (!selectedAlarmId) return;
    setBusy(true);
    try {
      const analysis = await reviewAlarm(selectedAlarmId, action);
      setAnalyses((current) => ({ ...current, [selectedAlarmId]: analysis }));
      toast.success(action === 'approve' ? '分析已批准' : action === 'reject' ? '分析已驳回' : '已要求补充证据');
      await refresh();
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const createWorkOrder = async () => {
    if (!selectedAlarmId) return;
    setBusy(true);
    try {
      const result = await createAlarmWorkOrder(selectedAlarmId);
      setAnalyses((current) => ({
        ...current,
        [selectedAlarmId]: {
          ...current[selectedAlarmId],
          analysis_status: 'WORK_ORDER_CREATED',
          created_work_order_id: result.work_order_id,
        },
      }));
      toast.success(`${result.work_order_code} 已创建`);
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
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{total} 条记录</span>
            <button disabled={busy || !canControl || !alarms.length} onClick={runCorrelation} className="btn btn-outline btn-sm">
              关联分析
            </button>
          </div>
        </div>
        {alarms.length ? (
          <table className="w-full text-sm" data-testid="alarms-table">
            <thead>
              <tr className="text-left text-xs text-muted border-b border-card-border">
                <th className="py-2 pr-3">级别</th>
                <th className="py-2 pr-3">风险</th>
                <th className="py-2 pr-3">设备</th>
                <th className="py-2 pr-3">消息</th>
                <th className="py-2 pr-3">时间</th>
                <th className="py-2 pr-3">状态</th>
                <th className="py-2 pr-3">分析</th>
                <th className="py-2 pr-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {alarms.map((alarm) => (
                <tr key={alarm.id} className="border-b border-card-border/50 last:border-0">
                  <td className="py-2 pr-3">
                    <span className={`badge ${SEVERITY_STYLES[alarm.severity] || 'bg-gray-500/15 text-gray-300'}`}>{alarm.severity}</span>
                  </td>
                  <td className="py-2 pr-3 text-xs">{alarm.risk_level || '待分析'}</td>
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
                  <td className="py-2 pr-3 text-xs">
                    <div>{alarm.analysis_status || 'NEW'}</div>
                    <div className="text-muted">关联 {alarm.correlated_alarm_count || 0} 条</div>
                  </td>
                  <td className="py-2 pr-3 space-x-2 whitespace-nowrap">
                    {!alarm.acknowledged && (
                      <button disabled={busy || !canControl} onClick={() => ack(alarm)} className="btn btn-outline btn-sm">
                        确认
                      </button>
                    )}
                    <button
                      disabled={busy || !canControl}
                      onClick={() => runAnalysis(alarm)}
                      className="btn btn-outline btn-sm"
                      data-testid={`analyze-alarm-${alarm.id}`}
                    >
                      AI 分析
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted py-6 text-center">当前没有工业报警记录。</p>
        )}
      </div>

      {correlation && correlation.groups.length > 0 && (
        <div className="card" data-testid="correlation-panel">
          <h2 className="font-semibold mb-3">关联事件组（{correlation.groups.length} 组 / {correlation.total_alarms} 条报警）</h2>
          <div className="space-y-2 text-sm">
            {correlation.groups.map((group) => (
              <div key={group.group_id} className="rounded-lg border border-card-border p-3 flex items-center justify-between gap-3">
                <div>
                  <span className={`badge ${SEVERITY_STYLES[group.severity] || 'bg-gray-500/15 text-gray-300'}`}>{group.severity}</span>
                  <span className="ml-2 text-xs font-mono text-muted">{group.reason === 'line_cascade' ? '产线级联' : '同设备'}</span>
                </div>
                <div className="text-xs text-muted">
                  报警 {group.alarm_ids.join('、')} · 设备 {group.equipment_ids.map((id) => `#${id}`).join(' ')} · {group.size} 条
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedAlarmId && analyses[selectedAlarmId] && (
        <div className="card" data-testid="analysis-panel">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold flex items-center gap-2"><BrainCircuit size={16} className="text-primary-400" />报警智能分析（AI-assisted，仅供人工决策参考）</h2>
            <span className="text-xs text-muted">风险 {analyses[selectedAlarmId].risk_level} · 置信度 {(analyses[selectedAlarmId].confidence * 100).toFixed(0)}% · {analyses[selectedAlarmId].analysis_status}</span>
          </div>
          <div className="space-y-3 text-sm">
            <AnalysisBlock title="报警理解" body={analyses[selectedAlarmId].summary} />
            <AnalysisBlock title="根因假设" body={analyses[selectedAlarmId].root_cause_hypothesis} />
            <EvidenceDetails evidence={analyses[selectedAlarmId].evidence} />
            {analyses[selectedAlarmId].citations.length > 0 && (
              <div>
                <div className="text-xs text-muted mb-1">知识库引用</div>
                <ul className="list-disc list-inside text-xs text-muted">
                  {analyses[selectedAlarmId].citations.map((citation, index) => (
                    <li key={`${citation.article_id}-${index}`}>
                      {citation.title} · {citation.source || '知识库'}（得分 {citation.score}）
                      {citation.snippet && <span className="block pl-4">{citation.snippet}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <div className="text-xs text-muted mb-1">建议行动（需人工确认后经工单执行）</div>
              <ol className="list-decimal list-inside space-y-1">
                {analyses[selectedAlarmId].recommended_actions.map((action, index) => (
                  <li key={index}>{action}</li>
                ))}
              </ol>
            </div>
            {correlation && (
              <p className="text-xs text-muted">
                关联组：{correlation.groups.find((group) => group.group_id === analyses[selectedAlarmId].correlation_group_id)?.size ?? 1} 条相关报警
              </p>
            )}
            <p className="text-xs text-yellow-300 bg-yellow-500/10 rounded-lg p-3 flex items-start gap-1.5">
              <ShieldCheck size={14} className="mt-0.5 shrink-0" />
              本分析不会自动创建或执行任何设备控制；任何操作必须通过工单与 Human Approval 审批流。
            </p>
            {canControl && analyses[selectedAlarmId].analysis_status === 'WAITING_REVIEW' && (
              <div className="flex flex-wrap gap-2" data-testid="review-actions">
                <button disabled={busy} onClick={() => review('approve')} className="btn btn-primary btn-sm">批准分析</button>
                <button disabled={busy} onClick={() => review('request_more_evidence')} className="btn btn-outline btn-sm">要求补证</button>
                <button disabled={busy} onClick={() => review('reject')} className="btn btn-outline btn-sm">驳回分析</button>
              </div>
            )}
            {canControl && analyses[selectedAlarmId].analysis_status === 'APPROVED' && (
              <button disabled={busy} onClick={createWorkOrder} className="btn btn-primary btn-sm" data-testid="create-alarm-work-order">
                创建受控工单
              </button>
            )}
            {analyses[selectedAlarmId].created_work_order_id && (
              <p className="text-xs text-green-400">已创建工单 #{analyses[selectedAlarmId].created_work_order_id}</p>
            )}
          </div>
        </div>
      )}

      <p className="text-xs text-muted flex items-start gap-1.5">
        <ShieldCheck size={14} className="mt-0.5 shrink-0 text-green-400" />
        报警来源于只读 OPC UA 订阅流水线；确认与分析仅更新平台内记录，不向设备写入任何内容。
      </p>
    </div>
  );
}

function AnalysisBlock({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <div className="text-xs text-muted mb-1">{title}</div>
      <p className="rounded-lg bg-black/10 border border-card-border p-3">{body}</p>
    </div>
  );
}

function EvidenceDetails({ evidence }: { evidence: Record<string, unknown> }) {
  const telemetry = evidence.telemetry_fields as Record<string, unknown> | undefined;
  const prediction = evidence.prediction_context as Record<string, unknown> | undefined;
  const risk = evidence.risk_assessment as { reasons?: string[] } | undefined;
  return (
    <div className="grid md:grid-cols-3 gap-2 text-xs" data-testid="evidence-details">
      <div className="rounded-lg border border-card-border p-3">
        <div className="text-muted mb-1">遥测证据</div>
        <div>{telemetry ? Object.entries(telemetry).map(([key, value]) => `${key}=${value ?? '--'}`).join(' · ') : '无'}</div>
      </div>
      <div className="rounded-lg border border-card-border p-3">
        <div className="text-muted mb-1">故障预测</div>
        <div>{prediction ? `${prediction.failure_mode || '未知'} · probability=${prediction.probability ?? '--'}` : '无预测记录'}</div>
      </div>
      <div className="rounded-lg border border-card-border p-3">
        <div className="text-muted mb-1">风险规则</div>
        <div>{risk?.reasons?.join(' · ') || '无附加升级条件'}</div>
      </div>
    </div>
  );
}

function formatTime(value: string | null | undefined) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
