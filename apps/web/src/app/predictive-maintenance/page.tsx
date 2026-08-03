'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowRight, BookOpenCheck, BrainCircuit, CalendarClock, PackageCheck, ShieldAlert, Sparkles, UserRoundCheck,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  listAnomalies,
  listDiagnoses,
  listMaintenanceRecommendations,
  listMLModels,
  listMLPredictionRecords,
  listPredictions,
} from '@/lib/api';
import type { MLModelVersion, MLPredictionRecord } from '@/lib/types';

const FAILURE_LABELS: Record<string, string> = {
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

export default function PredictiveMaintenancePage() {
  const router = useRouter();
  const [predictions, setPredictions] = useState<any[]>([]);
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [diagnoses, setDiagnoses] = useState<any[]>([]);
  const [mlModels, setMLModels] = useState<MLModelVersion[]>([]);
  const [mlPredictions, setMLPredictions] = useState<MLPredictionRecord[]>([]);
  const [riskFilter, setRiskFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      listPredictions(),
      listMaintenanceRecommendations(),
      listAnomalies({ status: 'open' }),
      listDiagnoses(),
      listMLModels(),
      listMLPredictionRecords(),
    ])
      .then(([predictionData, recommendationData, anomalyData, diagnosisData, modelData, mlPredictionData]) => {
        setPredictions(predictionData);
        setRecommendations(recommendationData);
        setAnomalies(anomalyData);
        setDiagnoses(diagnosisData);
        setMLModels(modelData);
        setMLPredictions(mlPredictionData);
      })
      .catch((error) => toast.error(error.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () => riskFilter === 'all' ? predictions : predictions.filter((item) => item.risk_level === riskFilter),
    [predictions, riskFilter],
  );

  if (loading) return <div className="text-muted p-6">加载中...</div>;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs tracking-[0.18em] uppercase text-primary-400 font-semibold mb-1"><BrainCircuit size={14} /> Predictive Maintenance</div>
          <h1 className="text-2xl font-bold">预测性维护中心</h1>
          <p className="text-sm text-muted mt-1">风险预测 → 维护窗口 → 策略生成 → 人员与备件调度 → 智能工单</p>
        </div>
        <select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)} className="text-sm">
          <option value="all">全部风险等级</option><option value="critical">紧急</option><option value="high">高风险</option><option value="medium">中风险</option><option value="low">低风险</option>
        </select>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Summary label="开放异常" value={anomalies.length} icon={<ShieldAlert size={18} />} tone="red" />
        <Summary label="风险预测" value={predictions.length} icon={<BrainCircuit size={18} />} tone="purple" />
        <Summary label="维护策略" value={recommendations.length} icon={<Sparkles size={18} />} tone="blue" />
        <Summary label="自动工单" value={recommendations.filter((item) => item.auto_work_order_id).length} icon={<UserRoundCheck size={18} />} tone="green" />
      </div>

      <section className="space-y-3" data-testid="ml-observability">
        <div>
          <h2 className="font-semibold">ML Model Registry &amp; Inference Observability</h2>
          <p className="text-xs text-muted mt-1">
            Operational Health Score and rule estimates remain separate from ML degradation, probability, and RUL outputs.
          </p>
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="card space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Registered model versions</h3>
              <span className="badge bg-purple-500/15 text-purple-200">{mlModels.length}</span>
            </div>
            {mlModels.slice(0, 6).map((model) => (
              <div key={model.id} className="rounded-lg border border-card-border bg-white/[0.02] p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs break-all">{model.version}</span>
                  <span className={`badge ${model.is_production ? 'bg-green-500/15 text-green-200' : 'bg-blue-500/15 text-blue-200'}`}>
                    {model.status}
                  </span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted">
                  <span>{model.task_type}</span>
                  <span>{model.algorithm}</span>
                  <span>Dataset #{model.dataset_version_id}</span>
                  <span>{model.feature_schema_version}</span>
                </div>
              </div>
            ))}
            {!mlModels.length && (
              <p className="text-sm text-muted py-4">No registered ML model. Synthetic rule estimates are not presented as trained model results.</p>
            )}
          </div>

          <div className="card space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Latest deterministic ML predictions</h3>
              <span className="badge bg-blue-500/15 text-blue-200">{mlPredictions.length}</span>
            </div>
            {mlPredictions.slice(0, 6).map((prediction) => (
              <div key={prediction.id} className="rounded-lg border border-card-border bg-white/[0.02] p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{prediction.prediction_type}</span>
                  <span className="font-mono text-xs">Model #{prediction.model_version_id}</span>
                </div>
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <Mini label="Prediction" value={prediction.prediction} />
                  <Mini label="Failure P" value={formatProbability(prediction.probability)} />
                  <Mini label="ML degradation" value={formatDecimal(prediction.degradation_index)} />
                  <Mini label="Estimated RUL" value={prediction.rul_hours == null ? '--' : `${prediction.rul_hours.toFixed(1)}h`} />
                </div>
                <div className="mt-2 text-xs text-muted">
                  {prediction.feature_schema_version} · Window {formatDate(prediction.feature_timestamp_start)}–{formatDate(prediction.feature_timestamp_end)}
                </div>
                {!!prediction.top_contributing_features?.length && (
                  <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Top contributing features">
                    {prediction.top_contributing_features.slice(0, 5).map((feature) => (
                      <span key={feature.name} className="badge bg-yellow-500/10 text-yellow-200">
                        {feature.name}: {feature.contribution.toFixed(3)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {!mlPredictions.length && (
              <p className="text-sm text-muted py-4">No ML PredictionRecord exists. A production/staging model is not fabricated for this demo.</p>
            )}
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <div><h2 className="font-semibold">风险预测队列</h2><p className="text-xs text-muted mt-1">剩余寿命与失效概率为规则模型演示值，不替代 OEM 诊断</p></div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filtered.map((prediction) => {
            const recommendation = recommendations.find((item) => item.prediction_id === prediction.id);
            const diagnosis = diagnoses.find((item) => item.anomaly_event_id === prediction.anomaly_event_id);
            return (
              <article key={prediction.id} className="card overflow-hidden relative">
                <div className={`absolute left-0 top-0 bottom-0 w-1 ${riskColor(prediction.risk_level)}`} />
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-muted font-mono">{prediction.equipment_code}</div>
                    <h3 className="font-semibold mt-1">{prediction.equipment_name}</h3>
                    <p className="text-sm text-primary-300 mt-1">{FAILURE_LABELS[prediction.failure_mode] || prediction.failure_mode}</p>
                  </div>
                  <RiskBadge level={prediction.risk_level} />
                </div>
                <div className="grid grid-cols-3 gap-2 my-4">
                  <Mini label="失效概率" value={`${Math.round(prediction.probability * 100)}%`} />
                  <Mini label="剩余寿命" value={`${prediction.remaining_useful_life_hours ?? '--'}h`} />
                  <Mini label="模型" value={prediction.is_mock ? 'Mock' : 'AI'} />
                </div>
                <div className="rounded-lg bg-black/10 border border-card-border p-3">
                  <div className="flex items-center gap-2 text-xs text-muted mb-2"><CalendarClock size={14} />建议维护窗口</div>
                  <div className="text-sm">{formatDate(prediction.maintenance_window_start)} — {formatDate(prediction.maintenance_window_end)}</div>
                </div>
                {diagnosis && (
                  <div className="mt-4 rounded-lg border border-purple-500/20 bg-purple-500/[0.06] p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-xs text-purple-300"><BookOpenCheck size={14} />结构化诊断与 RAG 证据</div>
                      <span className="text-xs font-mono">{Math.round(diagnosis.confidence * 100)}%</span>
                    </div>
                    <p className="text-sm leading-6">{diagnosis.summary}</p>
                    <p className="text-xs text-muted">可能原因：{(diagnosis.possible_causes || []).join(' · ')}</p>
                    {diagnosis.requires_human_review && <p className="text-xs text-yellow-300">置信度不足，已转人工诊断复核。</p>}
                    <div className="flex flex-wrap gap-2">
                      {(diagnosis.rag_citations || []).map((citation: any) => (
                        <span key={citation.article_id} className="badge bg-purple-500/15 text-purple-200" title={citation.source || ''}>
                          来源：{citation.title} · {Math.round(citation.score * 100)}%
                        </span>
                      ))}
                      {!diagnosis.rag_citations?.length && <span className="text-xs text-yellow-300">知识库未检索到足够证据，需人工补充。</span>}
                    </div>
                  </div>
                )}
                {recommendation && (
                  <div className="mt-4 space-y-3">
                    <div><div className="text-xs text-muted mb-1">Agent 维修策略</div><p className="text-sm leading-6">{recommendation.strategy}</p></div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <div className="rounded-lg bg-blue-500/5 border border-blue-500/15 p-3">
                        <div className="flex items-center gap-2 text-xs text-blue-300 mb-2"><UserRoundCheck size={14} />人员建议</div>
                        <div className="text-sm">{recommendation.dispatch_suggestion?.technicians?.[0]?.name || '待主管分派'}</div>
                        <div className="text-xs text-muted mt-1">{(recommendation.required_skills || []).join(' · ') || '通用维修技能'}</div>
                      </div>
                      <div className="rounded-lg bg-green-500/5 border border-green-500/15 p-3">
                        <div className="flex items-center gap-2 text-xs text-green-300 mb-2"><PackageCheck size={14} />备件建议</div>
                        <div className="text-sm">{(recommendation.required_parts || []).map((part: any) => part.name).join(' · ') || '无需备件'}</div>
                        <div className="text-xs text-muted mt-1">
                          {(recommendation.required_parts || []).every((part: any) => part.reservation_status === 'reserved')
                            ? '已为工单预留'
                            : '部分备件不足，已转人工采购'}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted">优先级 {recommendation.priority} · {recommendation.status}</span>
                      {recommendation.auto_work_order_id ? (
                        <button onClick={() => router.push(`/work-orders/${recommendation.auto_work_order_id}`)} className="btn btn-primary btn-sm">查看智能工单 <ArrowRight size={14} /></button>
                      ) : (
                        <button onClick={() => router.push(`/equipment/${prediction.equipment_id}`)} className="btn btn-outline btn-sm">查看设备 <ArrowRight size={14} /></button>
                      )}
                    </div>
                  </div>
                )}
              </article>
            );
          })}
          {!filtered.length && <div className="card lg:col-span-2 text-center text-muted py-12">当前筛选下暂无风险预测</div>}
        </div>
      </section>
    </div>
  );
}

function Summary({ label, value, icon, tone }: any) {
  const tones: Record<string, string> = { red: 'text-red-300', purple: 'text-purple-300', blue: 'text-blue-300', green: 'text-green-300' };
  return <div className="card"><div className={`flex items-center gap-2 text-xs ${tones[tone]}`}>{icon}{label}</div><div className="text-2xl font-bold mt-2">{value}</div></div>;
}

function Mini({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg bg-white/[0.03] p-2.5"><div className="text-[11px] text-muted">{label}</div><div className="font-mono font-semibold mt-1">{value}</div></div>;
}

function RiskBadge({ level }: { level: string }) {
  const labels: Record<string, string> = { critical: '紧急', high: '高风险', medium: '中风险', low: '低风险' };
  const styles: Record<string, string> = { critical: 'bg-red-500/20 text-red-300', high: 'bg-orange-500/20 text-orange-300', medium: 'bg-yellow-500/20 text-yellow-300', low: 'bg-green-500/20 text-green-300' };
  return <span className={`badge ${styles[level] || styles.medium}`}>{labels[level] || level}</span>;
}

function riskColor(level: string) {
  return { critical: 'bg-red-500', high: 'bg-orange-500', medium: 'bg-yellow-500', low: 'bg-green-500' }[level] || 'bg-gray-500';
}

function formatDate(value?: string) {
  if (!value) return '--';
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function formatProbability(value?: number) {
  return value == null ? '--' : `${(value * 100).toFixed(1)}%`;
}

function formatDecimal(value?: number) {
  return value == null ? '--' : value.toFixed(3);
}
