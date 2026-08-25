'use client';

import { BadgeCheck, CircleAlert, Cpu, Gauge, Wrench } from 'lucide-react';
import type { DemoState } from '@/lib/types';

const SCENARIO_META: Record<
  string,
  { label: string; badge: string; ring: string }
> = {
  normal: {
    label: 'NORMAL',
    badge: 'bg-green-500/15 text-green-300',
    ring: 'stroke-green-400',
  },
  warning: {
    label: 'WARNING',
    badge: 'bg-yellow-500/15 text-yellow-300',
    ring: 'stroke-yellow-400',
  },
  fault: {
    label: 'FAULT',
    badge: 'bg-red-500/15 text-red-300',
    ring: 'stroke-red-500',
  },
};

function Metric({
  label,
  value,
  unit,
  abnormal,
}: {
  label: string;
  value: number | null | undefined;
  unit: string;
  abnormal?: boolean;
}) {
  return (
    <div className="rounded bg-white/5 p-2" data-abnormal={abnormal ? '1' : '0'}>
      <div className="text-muted">{label}</div>
      <div
        className={`mt-0.5 text-sm font-semibold ${abnormal ? 'text-red-300' : ''}`}
      >
        {value ?? '-'}
        <span className="ml-1 text-muted font-normal">{unit}</span>
      </div>
    </div>
  );
}

export function ScenarioControl({
  current,
  busy,
  onSelect,
  canControl,
}: {
  current: string | null;
  busy: boolean;
  onSelect: (scenario: 'normal' | 'warning' | 'fault') => void;
  canControl: boolean;
}) {
  const options: Array<'normal' | 'warning' | 'fault'> = [
    'normal',
    'warning',
    'fault',
  ];
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs text-muted mr-1">运行场景：</span>
      {options.map((scenario) => {
        const meta = SCENARIO_META[scenario];
        const selected = current === scenario;
        return (
          <button
            key={scenario}
            type="button"
            aria-pressed={selected}
            disabled={busy || !canControl}
            onClick={() => onSelect(scenario)}
            className={`btn ${selected ? 'btn-primary' : 'btn-outline'} !py-1 !px-3 text-xs`}
            data-testid={`scenario-${scenario}`}
          >
            {meta.label}
          </button>
        );
      })}
      {!canControl && (
        <span className="text-xs text-muted">（仅 supervisor/admin 可切换）</span>
      )}
    </div>
  );
}

export function EquipmentDigitalView({ state }: { state: DemoState }) {
  const equipmentStatus = state.equipment?.status ?? '-';
  const alarmActive = state.alarm ? !state.alarm.cleared : false;
  const severity = state.alarm?.severity ?? null;
  const scenarioLike =
    severity === 'CRITICAL'
      ? 'fault'
      : severity === 'WARNING' || equipmentStatus === 'warning'
        ? 'warning'
        : 'normal';
  const meta = SCENARIO_META[scenarioLike] ?? SCENARIO_META.normal;
  const telemetry = state.telemetry;

  const vibrationHigh =
    (telemetry?.vibration_rms ?? 0) > 4.5 ||
    (telemetry?.bearing_temperature ?? 0) > 75;

  return (
    <div className="card p-4" data-testid="equipment-digital-view">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Cpu size={18} />
        <h2 className="font-semibold">Motor001 · 数字视图</h2>
        <span
          className={`badge ${meta.badge} ml-auto`}
          data-testid="motor-state-badge"
        >
          {(state.equipment?.status ?? 'unknown').toUpperCase()}
        </span>
        {alarmActive && (
          <span className="badge bg-red-500/15 text-red-300">
            <CircleAlert size={12} className="inline mr-1" />
            ALARM ACTIVE
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 简易工业示意：电机本体 + 轴承/轴/驱动 */}
        <div className="rounded bg-black/20 p-3">
          <svg viewBox="0 0 220 120" className="w-full" role="img"
            aria-label={`Motor001 state ${equipmentStatus}`}>
            {/* 机身 */}
            <rect x="60" y="30" width="100" height="60" rx="8"
              className="fill-white/5 stroke-white/20" strokeWidth="2" />
            {/* 转轴 */}
            <line x1="160" y1="60" x2="205" y2="60"
              className={`${meta.ring} animate-pulse`} strokeWidth="6" strokeLinecap="round" />
            {/* 风扇罩 */}
            <circle cx="85" cy="60" r="18" className="fill-white/10 stroke-white/25" />
            <g className={alarmActive ? '' : 'animate-spin'}
              style={{ transformOrigin: '85px 60px', animationDuration: '3s' }}>
              <line x1="85" y1="46" x2="85" y2="74" className="stroke-white/40" strokeWidth="3" />
              <line x1="71" y1="60" x2="99" y2="60" className="stroke-white/40" strokeWidth="3" />
            </g>
            {/* 接线盒 */}
            <rect x="95" y="18" width="30" height="12" rx="3" className="fill-white/10 stroke-white/25" />
            {/* 底座 */}
            <rect x="55" y="90" width="110" height="8" rx="2" className="fill-white/10" />
            <text x="110" y="112" textAnchor="middle" className="fill-muted" fontSize="9">
              Bearing · Shaft · Drive
            </text>
          </svg>
          <div className="text-center mt-1">
            <span className={`badge ${meta.badge}`} data-testid="digital-state-text">
              {meta.label}
            </span>
          </div>
        </div>

        {/* 实时指标 */}
        <div className="grid grid-cols-2 gap-2 content-start">
          <Metric label="轴承温度" value={telemetry?.bearing_temperature} unit="℃" abnormal={(telemetry?.bearing_temperature ?? 0) > 75} />
          <Metric label="振动 RMS" value={telemetry?.vibration_rms} unit="mm/s" abnormal={(telemetry?.vibration_rms ?? 0) > 4.5} />
          <Metric label="电机电流" value={telemetry?.motor_current_a} unit="A" />
          <Metric label="转速" value={telemetry?.speed_rpm} unit="rpm" />
          <Metric label="电压" value={telemetry?.motor_voltage_v} unit="V" />
          <Metric label="负载率" value={telemetry?.load_ratio_pct} unit="%" />
        </div>
      </div>
      <p className="text-xs text-muted mt-3">
        采样时间：{telemetry?.collected_at ?? '-'} · 数据质量{' '}
        {telemetry?.quality != null ? `${Math.round(telemetry.quality * 100)}%` : '-'}
      </p>
    </div>
  );
}

export function HealthChip({ state }: { state: DemoState }) {
  const health = state.equipment?.health_score;
  return (
    <div className="card p-3 flex items-center gap-2" data-testid="demo-health">
      <Gauge size={16} className="text-blue-300" />
      <span className="text-xs">Health Score</span>
      <span className="font-bold ml-auto">
        {health != null ? `${Math.round(health)} / 100` : '-'}
      </span>
    </div>
  );
}

export function WorkflowChip({ state }: { state: DemoState }) {
  const wo = state.work_order;
  return (
    <div className="card p-3 flex items-center gap-2" data-testid="demo-workorder-chip">
      <Wrench size={16} className="text-green-300" />
      <span className="text-xs">Work Order</span>
      <span className="font-bold ml-auto text-xs">
        {wo ? `${wo.code} · ${wo.status}` : '—'}
      </span>
    </div>
  );
}

export function AnalysisChip({ state }: { state: DemoState }) {
  const waiting =
    state.analysis?.analysis_status === 'WAITING_REVIEW' ||
    state.anomaly != null;
  return (
    <div className="card p-3 flex items-center gap-2" data-testid="demo-analysis-chip">
      <BadgeCheck size={16} className="text-purple-300" />
      <span className="text-xs">AI 分析</span>
      <span className="ml-auto text-xs font-bold">
        {waiting ? '待复核' : '—'}
      </span>
    </div>
  );
}
