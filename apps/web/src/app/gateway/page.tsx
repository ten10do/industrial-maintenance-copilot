'use client';

import { useCallback, useEffect, useState } from 'react';
import { Cable, PlugZap, RefreshCcw, RadioTower, ShieldCheck, Rss } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '@/lib/auth';
import {
  getGatewayNodes,
  getGatewayStatus,
  getGatewaySubscriptions,
  reloadGatewayMappings,
  startGatewaySubscriptions,
  stopGatewaySubscriptions,
  syncGateway,
  testGatewayConnection,
} from '@/lib/api';
import type {
  GatewayNode,
  GatewayStatus,
  GatewaySubscriptionStatus,
  GatewaySyncResult,
  GatewayTestConnect,
} from '@/lib/types';

const QUALITY_LABELS: Record<string, { label: string; className: string }> = {
  good: { label: '良好', className: 'bg-green-500/15 text-green-300' },
  uncertain: { label: '不确定', className: 'bg-yellow-500/15 text-yellow-300' },
  bad: { label: '坏质量', className: 'bg-red-500/15 text-red-300' },
};

export default function GatewayPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<GatewayStatus | null>(null);
  const [nodes, setNodes] = useState<GatewayNode[]>([]);
  const [lastTest, setLastTest] = useState<GatewayTestConnect | null>(null);
  const [lastSync, setLastSync] = useState<GatewaySyncResult | null>(null);
  const [subscription, setSubscription] = useState<GatewaySubscriptionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const canControl = user?.role === 'admin' || user?.role === 'supervisor';

  const refresh = useCallback(async () => {
    const [statusData, nodesData, subscriptionData] = await Promise.all([
      getGatewayStatus().catch(() => null),
      getGatewayNodes().catch(() => null),
      getGatewaySubscriptions().catch(() => null),
    ]);
    if (statusData) setStatus(statusData);
    if (nodesData) setNodes(nodesData.nodes);
    if (subscriptionData) setSubscription(subscriptionData);
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const act = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try {
      await action();
      toast.success(success);
      await refresh();
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const runTestConnect = async () => {
    setBusy(true);
    try {
      setLastTest(await testGatewayConnection());
      await refresh();
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const runSync = async () => {
    setBusy(true);
    try {
      setLastSync(await syncGateway());
      toast.success('同步完成');
      await refresh();
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const runtime = status?.runtime;
  const connection = status?.connection;
  const connected = runtime?.connected ?? false;
  const subscriptionActive = subscription?.subscription_status === 'active';

  const runSubscriptionToggle = async () => {
    setBusy(true);
    try {
      if (subscriptionActive) {
        await stopGatewaySubscriptions();
        toast.success('订阅已停止');
      } else {
        await startGatewaySubscriptions();
        toast.success('订阅已启动');
      }
      await refresh();
    } catch (error: any) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6" data-testid="gateway-page">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <div className="text-xs tracking-[0.18em] uppercase text-primary-400 font-semibold mb-1">Industrial Protocol Integration</div>
          <h1 className="text-2xl font-bold">工业协议网关（OPC UA）</h1>
          <p className="text-sm text-muted mt-1">OPC UA-compatible simulated industrial gateway · 只读遥测接入</p>
        </div>
        <div className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs border ${connected ? 'border-green-500/30 bg-green-500/10 text-green-300' : connection?.status === 'error' ? 'border-red-500/30 bg-red-500/10 text-red-300' : 'border-card-border text-muted'}`}>
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : connection?.status === 'error' ? 'bg-red-400' : 'bg-gray-500'}`} />
          {connection?.status === 'error' ? '连接异常' : connected ? '已连接' : '未连接'} · {runtime?.mode || '--'} 模式
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        <section className="card xl:col-span-1 space-y-4">
          <div className="flex items-center gap-2">
            <RadioTower size={16} className="text-primary-400" />
            <h2 className="font-semibold">OPC UA Connection</h2>
          </div>
          <dl className="space-y-2 text-sm">
            <InfoRow label="端点" value={runtime?.endpoint || connection?.endpoint || '--'} mono />
            <InfoRow label="协议" value={(connection?.protocol || 'opcua').toUpperCase()} />
            <InfoRow label="连接状态" value={connection?.status || '--'} />
            <InfoRow label="最近连接" value={formatTime(connection?.last_connected_at)} />
            <InfoRow label="最近同步" value={formatTime(connection?.last_sync_at)} />
            <InfoRow label="轮询周期" value={runtime ? `${runtime.poll_interval_seconds}s` : '--'} />
            <InfoRow label="累计入库快照" value={String(runtime?.totals.snapshots_ingested ?? 0)} />
          </dl>
          {connection?.last_error && (
            <p className="text-xs text-red-300 bg-red-500/10 rounded-lg p-3 break-all">{connection.last_error}</p>
          )}
          {status?.seed_error && (
            <p className="text-xs text-yellow-300 bg-yellow-500/10 rounded-lg p-3 break-all">{status.seed_error}</p>
          )}
          <div className="grid grid-cols-1 gap-2">
            <button disabled={busy} onClick={runTestConnect} className="btn btn-outline btn-block"><PlugZap size={15} />测试连接</button>
            <button disabled={busy || !canControl} onClick={runSync} className="btn btn-primary btn-block"><RefreshCcw size={15} />立即同步</button>
            <button disabled={busy || !canControl} onClick={() => act(() => reloadGatewayMappings(), '映射配置已重载')} className="btn btn-outline btn-block"><Cable size={15} />重载节点映射</button>
          </div>
          {!canControl && <p className="text-xs text-yellow-300 bg-yellow-500/10 rounded-lg p-3">同步与映射重载仅限主管和管理员；当前为只读查看。</p>}
          <p className="text-xs text-muted flex items-start gap-1.5"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-green-400" />网关为 read-only 模式：仅读取设备数据，禁止写 PLC；未来写操作必须经过人工审批。</p>
        </section>

        <section className="xl:col-span-3 space-y-4">
          <div className="card" data-testid="subscription-status">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Rss size={16} className="text-primary-400" />
                <h2 className="font-semibold">Subscription Status</h2>
                <span className="text-[10px] text-muted">DataChange · read-only</span>
              </div>
              <span className={`badge ${subscriptionActive ? 'bg-green-500/15 text-green-300' : subscription?.subscription_status === 'error' ? 'bg-red-500/15 text-red-300' : 'bg-gray-500/15 text-gray-300'}`}>
                {subscriptionActive ? '订阅中' : subscription?.subscription_status === 'error' ? '异常' : '已停止'}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <SyncStat label="活动节点" value={subscription?.active_nodes.length ?? 0} />
              <SyncStat label="采样间隔" value={`${subscription?.sampling_interval_ms ?? '--'} ms`} />
              <SyncStat label="事件总数" value={subscription?.event_totals.received ?? 0} />
              <SyncStat label="入库快照" value={subscription?.event_totals.snapshots_ingested ?? 0} />
            </div>
            <p className="text-xs text-muted mt-3">
              最近事件：{subscription?.last_event ? `${formatTime(subscription.last_event_at)} · ${subscription.last_event}` : '--'}
              {subscription ? ` · 缓冲待发 ${subscription.buffer_pending}` : ''}
            </p>
            {subscription?.error && <p className="text-xs text-red-300 mt-1 break-all">{subscription.error}</p>}
            <button disabled={busy || !canControl} onClick={runSubscriptionToggle} className="btn btn-outline btn-sm mt-3">
              {subscriptionActive ? '停止订阅' : '启动订阅'}
            </button>
            {!canControl && <p className="text-xs text-yellow-300 mt-2">订阅控制仅限主管和管理员；当前为只读查看。</p>}
          </div>

          {lastTest && (
            <div className={`card border ${lastTest.ok ? 'border-green-500/30' : 'border-red-500/30'}`}>
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold">连接测试结果</h2>
                <span className={`badge ${lastTest.ok ? 'bg-green-500/15 text-green-300' : 'bg-red-500/15 text-red-300'}`}>{lastTest.ok ? '成功' : '失败'}</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <InfoRow label="延迟" value={`${lastTest.latency_ms} ms`} />
                <InfoRow label="探测节点" value={lastTest.probe_node || '--'} mono />
                <InfoRow label="采样值" value={String(lastTest.sample_value ?? '--')} mono />
                {lastTest.error && <InfoRow label="错误" value={lastTest.error} />}
              </div>
            </div>
          )}

          {lastSync && (
            <div className="card">
              <h2 className="font-semibold mb-3">最近一次同步（读取 → 质量校验 → 遥测入库）</h2>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                <SyncStat label="读取节点" value={lastSync.reads_total} />
                <SyncStat label="通过质量校验" value={lastSync.accepted} tone={lastSync.accepted > 0 ? 'good' : undefined} />
                <SyncStat label="被拒绝" value={lastSync.rejected} tone={lastSync.rejected > 0 ? 'bad' : undefined} />
                <SyncStat label="入库快照" value={lastSync.snapshots_ingested} tone={lastSync.snapshots_ingested > 0 ? 'good' : undefined} />
                <SyncStat label="触发异常 / 工单" value={`${lastSync.anomalies} / ${lastSync.work_orders_created}`} />
              </div>
              {(Object.keys(lastSync.reject_reasons).length > 0 || lastSync.skipped_details.length > 0) && (
                <div className="mt-3 space-y-1 text-xs text-muted">
                  {Object.entries(lastSync.reject_reasons).map(([reason, count]) => (
                    <p key={reason}>· 质量拒绝 {reason} × {count}</p>
                  ))}
                  {lastSync.skipped_details.map((detail) => (
                    <p key={detail}>· {detail}</p>
                  ))}
                </div>
              )}
              {lastSync.error && <p className="mt-3 text-xs text-red-300">{lastSync.error}</p>}
            </div>
          )}

          <div className="card overflow-x-auto">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">Device Nodes</h2>
              <span className="text-xs text-muted">{nodes.length} 个映射节点</span>
            </div>
            {nodes.length ? (
              <table className="w-full text-sm" data-testid="gateway-nodes-table">
                <thead>
                  <tr className="text-left text-xs text-muted border-b border-card-border">
                    <th className="py-2 pr-3">Node ID</th>
                    <th className="py-2 pr-3">设备</th>
                    <th className="py-2 pr-3">指标</th>
                    <th className="py-2 pr-3">最近值</th>
                    <th className="py-2 pr-3">质量</th>
                    <th className="py-2 pr-3">时间戳</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((node) => {
                    const quality = node.last_quality ? QUALITY_LABELS[node.last_quality] : null;
                    return (
                      <tr key={node.node_id} className="border-b border-card-border/50 last:border-0">
                        <td className="py-2 pr-3 font-mono text-xs">{node.node_id}{!node.enabled && <span className="ml-2 badge bg-gray-500/15 text-gray-300">停用</span>}{node.informational && <span className="ml-2 badge bg-primary-500/15 text-primary-300">展示</span>}</td>
                        <td className="py-2 pr-3">{node.equipment_code || '--'}</td>
                        <td className="py-2 pr-3">{node.metric_name}{node.unit ? ` (${node.unit})` : ''}</td>
                        <td className="py-2 pr-3 font-mono">{node.last_value == null ? '--' : String(node.last_value)}</td>
                        <td className="py-2 pr-3">
                          {node.last_error
                            ? <span className="badge bg-red-500/15 text-red-300" title={node.last_error}>异常</span>
                            : quality
                              ? <span className={`badge ${quality.className}`}>{quality.label}</span>
                              : <span className="text-muted">待采集</span>}
                        </td>
                        <td className="py-2 pr-3 text-xs text-muted">{formatTime(node.last_timestamp)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-muted py-6 text-center">暂无节点映射；请确认 configs/opcua-node-mapping.yaml 与设备编码一致后点击「重载节点映射」。</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted shrink-0">{label}</dt>
      <dd className={`text-right break-all ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
    </div>
  );
}

function SyncStat({ label, value, tone }: { label: string; value: number | string; tone?: 'good' | 'bad' }) {
  return (
    <div className={`rounded-lg border p-3 ${tone === 'good' ? 'border-green-500/30 bg-green-500/10' : tone === 'bad' ? 'border-red-500/30 bg-red-500/10' : 'border-card-border bg-black/10'}`}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-xl font-bold font-mono">{value}</div>
    </div>
  );
}

function formatTime(value: string | null | undefined) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
