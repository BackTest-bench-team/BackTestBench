"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type ExploreLimits = {
  min_date: string;
  max_date: string;
  max_days: number;
  instrument?: string;
  explore_timeframe?: string;
  data_source?: string;
};

export const EXPLORE_TIMEFRAME = "1d";

export type ExploreStability = {
  stability: number | null;
  consistency_score: number | null;
  worst_period: number | null;
  volatility: number | null;
  windows: number;
  positive_windows: number;
  beats_benchmark_windows: number;
  vs_benchmark: number | null;
  note?: string | null;
};

export type ExploreSession = {
  id: string;
  jobId?: string;
  strategyId: string;
  title: string;
  params: Record<string, number>;
  initialCapital: number;
  fromDate: string;
  toDate: string;
  status: "idle" | "queued" | "running" | "completed" | "error";
  error?: string;
  returnPct?: number | null;
  stability?: ExploreStability;
  chartPoints?: Array<{ date: string; strategy_index: number; benchmark_index: number }>;
  periodDays?: number;
};

export const EXPLORE_STORAGE_KEY = "backtestbench.explore.sessions.v1";
export const EXPLORE_DISMISSED_KEY = "backtestbench.explore.dismissed.v1";

const METRIC_HELP = {
  return: "Actual strategy return for the selected period: total P&L ÷ starting capital.",
  stability:
    "Overall score 0–100: how stable the strategy is over time, not just one lucky slice.",
  consistency: "Share of time windows with a positive return. 100% = every window profitable.",
  worstPeriod:
    "Weakest sub-period. Shows the depth of the worst drawdown, not just the average result.",
  volatility: "Spread of returns across windows. Higher = less predictable over time.",
} as const;

type ExploreJob = {
  job_id: string;
  strategy_id: string;
  title?: string;
  params?: Record<string, number>;
  from_date: string;
  to_date: string;
  initial_capital?: number;
  status: string;
  error?: string;
  return_pct?: number;
  period_days?: number;
  chart_points?: ExploreSession["chartPoints"];
  stability?: ExploreStability;
  metrics?: { total_pnl?: number };
};

function toDateOnly(value: string) {
  return value.slice(0, 10);
}

function defaultDateRange(limits: ExploreLimits) {
  const end = limits.max_date;
  const start = new Date(end);
  start.setDate(start.getDate() - Math.min(30, limits.max_days));
  const min = new Date(limits.min_date);
  if (start < min) start.setTime(min.getTime());
  return {
    fromDate: start.toISOString().slice(0, 10),
    toDate: end,
  };
}

function mapJobStatus(status: string): ExploreSession["status"] {
  if (status === "queued" || status === "running" || status === "completed" || status === "error") {
    return status;
  }
  return "idle";
}

export function jobToExploreSession(job: ExploreJob): ExploreSession {
  const returnPct =
    typeof job.return_pct === "number"
      ? job.return_pct
      : job.metrics?.total_pnl != null && job.initial_capital
        ? job.metrics.total_pnl / job.initial_capital
        : null;

  return {
    id: job.job_id,
    jobId: job.job_id,
    strategyId: job.strategy_id,
    title: job.title ?? job.strategy_id,
    params: job.params ?? {},
    initialCapital: job.initial_capital ?? 100_000,
    fromDate: toDateOnly(job.from_date),
    toDate: toDateOnly(job.to_date),
    status: mapJobStatus(job.status),
    error: job.error,
    returnPct,
    stability: job.stability,
    chartPoints: job.chart_points,
    periodDays: job.period_days,
  };
}

export function loadStoredExploreSessions(): ExploreSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(EXPLORE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Array<ExploreSession & { fromAt?: string; toAt?: string }>;
    if (!Array.isArray(parsed)) return [];
    return parsed.map((session) => ({
      ...session,
      fromDate: session.fromDate ?? session.fromAt?.slice(0, 10) ?? "",
      toDate: session.toDate ?? session.toAt?.slice(0, 10) ?? "",
    }));
  } catch {
    return [];
  }
}

export function loadDismissedExploreIds(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(EXPLORE_DISMISSED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as string[];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

export function dismissExploreSession(session: Pick<ExploreSession, "id" | "jobId">) {
  if (typeof window === "undefined") return;
  const dismissed = loadDismissedExploreIds();
  dismissed.add(session.id);
  if (session.jobId) dismissed.add(session.jobId);
  try {
    window.localStorage.setItem(EXPLORE_DISMISSED_KEY, JSON.stringify(Array.from(dismissed)));
  } catch {
    // ignore quota errors
  }
}

export async function deleteExploreJob(jobId: string) {
  await fetch(`/api/explore?job_id=${encodeURIComponent(jobId)}`, { method: "DELETE" });
}

export function saveExploreSessions(sessions: ExploreSession[]) {
  if (typeof window === "undefined") return;
  const dismissed = loadDismissedExploreIds();
  const filtered = sessions.filter(
    (session) =>
      !dismissed.has(session.id) && !(session.jobId && dismissed.has(session.jobId))
  );
  try {
    window.localStorage.setItem(EXPLORE_STORAGE_KEY, JSON.stringify(filtered));
  } catch {
    // ignore quota errors
  }
}

export function mergeExploreSessions(
  stored: ExploreSession[],
  jobs: ExploreJob[],
  dismissed: Set<string> = loadDismissedExploreIds()
): ExploreSession[] {
  const merged = new Map<string, ExploreSession>();

  for (const job of jobs) {
    if (dismissed.has(job.job_id)) continue;
    merged.set(job.job_id, jobToExploreSession(job));
  }

  for (const session of stored) {
    if (dismissed.has(session.id) || (session.jobId && dismissed.has(session.jobId))) {
      continue;
    }
    if (session.jobId) {
      if (!merged.has(session.jobId)) {
        merged.set(session.id, session);
      }
      continue;
    }
    if (session.status === "idle") {
      merged.set(session.id, session);
    }
  }

  return Array.from(merged.values()).sort((a, b) => {
    const aKey = a.jobId ?? a.id;
    const bKey = b.jobId ?? b.id;
    return bKey.localeCompare(aKey);
  });
}

function formatPct(fraction: number | null | undefined) {
  if (fraction == null) return "—";
  const sign = fraction >= 0 ? "+" : "−";
  return `${sign}${new Intl.NumberFormat("ru-RU", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Math.abs(fraction))}`;
}

function formatScore(value: number | null | undefined) {
  if (value == null) return "—";
  return `${value}/100`;
}

function MetricChip({
  label,
  value,
  help,
}: {
  label: string;
  value: React.ReactNode;
  help: string;
}) {
  return (
    <span className="explore-metric-chip" title={help}>
      <span className="explore-metric-label">{label}</span>
      <strong>{value}</strong>
    </span>
  );
}

function statusLabel(status: ExploreSession["status"]) {
  if (status === "running" || status === "queued") return "Running";
  if (status === "completed") return "Done";
  if (status === "error") return "Error";
  return "Ready";
}

function ExploreChart({
  points,
}: {
  points: Array<{ date: string; strategy_index: number; benchmark_index: number }>;
}) {
  if (!points.length) {
    return <div className="explore-dock-chart-empty">Chart appears when the run completes.</div>;
  }
  return (
    <div className="explore-dock-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#c8d3e4" />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={24} />
          <YAxis width={36} tick={{ fontSize: 10 }} />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="benchmark_index"
            stroke="#6b7c93"
            strokeDasharray="4 3"
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="strategy_index"
            stroke="#475ee6"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ExploreDock({
  sessions,
  activeId,
  limits,
  collapsed,
  onToggleCollapse,
  onSelect,
  onClose,
  onPatch,
  onRun,
}: {
  sessions: ExploreSession[];
  activeId: string | null;
  limits: ExploreLimits | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onPatch: (id: string, patch: Partial<ExploreSession>) => void;
  onRun: (id: string) => Promise<void>;
}) {
  const active = sessions.find((s) => s.id === activeId) ?? sessions[0];
  const runningCount = sessions.filter((s) => s.status === "running" || s.status === "queued").length;

  if (!sessions.length) return null;

  return (
    <section className={`explore-dock${collapsed ? " is-collapsed" : ""}`} aria-label="Explore sessions">
      <header className="explore-dock-bar">
        <div className="explore-dock-bar-title">
          <span className="explore-dock-label">Explore</span>
          {runningCount > 0 && <span className="explore-dock-badge">{runningCount} active</span>}
        </div>
        <div className="explore-dock-tabs" role="tablist">
          {sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              role="tab"
              aria-selected={session.id === active?.id}
              className={`explore-dock-tab${session.id === active?.id ? " is-active" : ""}`}
              onClick={() => onSelect(session.id)}
            >
              <span className={`explore-dock-tab-dot is-${session.status}`} />
              <span className="explore-dock-tab-text">{session.title}</span>
              <span
                className="explore-dock-tab-close"
                onClick={(e) => {
                  e.stopPropagation();
                  onClose(session.id);
                }}
              >
                ×
              </span>
            </button>
          ))}
        </div>
        <button className="explore-dock-toggle" type="button" onClick={onToggleCollapse}>
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </header>

      {!collapsed && active && limits && (
        <div className="explore-dock-body">
          <div className="explore-dock-controls">
            <p className="explore-dock-meta">
              {active.strategyId} · {limits.data_source} · {limits.instrument}
            </p>
            <div className="explore-dock-params">
              {Object.entries(active.params)
                .filter(([k]) => k !== "order_size")
                .map(([k, v]) => (
                  <span key={k} className="explore-dock-param">
                    {k}={v}
                  </span>
                ))}
            </div>
            <div className="explore-dock-dates">
              <label>
                From
                <input
                  type="date"
                  min={limits.min_date}
                  max={limits.max_date}
                  value={active.fromDate}
                  disabled={active.status === "running" || active.status === "queued"}
                  onChange={(e) => onPatch(active.id, { fromDate: e.target.value })}
                />
              </label>
              <label>
                To
                <input
                  type="date"
                  min={limits.min_date}
                  max={limits.max_date}
                  value={active.toDate}
                  disabled={active.status === "running" || active.status === "queued"}
                  onChange={(e) => onPatch(active.id, { toDate: e.target.value })}
                />
              </label>
            </div>
            <p className="explore-dock-hint">Max {limits.max_days} days</p>
            <p className="explore-dock-timeframe-note">Daily candles (1d)</p>
            <div className="explore-dock-actions">
              <button
                className="control-btn control-btn-run"
                type="button"
                disabled={active.status === "running" || active.status === "queued"}
                onClick={() => onRun(active.id)}
              >
                {active.status === "running" || active.status === "queued" ? "Running…" : "Run explore"}
              </button>
              <span className={`explore-dock-status is-${active.status}`}>{statusLabel(active.status)}</span>
            </div>
            {active.error && <p className="explore-dock-error">{active.error}</p>}
            {(active.returnPct != null || active.stability) && (
              <div className="explore-dock-results">
                {active.returnPct != null && (
                  <MetricChip label="Return" value={formatPct(active.returnPct)} help={METRIC_HELP.return} />
                )}
                {active.stability?.stability != null && (
                  <MetricChip
                    label="Stability"
                    value={formatScore(active.stability.stability)}
                    help={METRIC_HELP.stability}
                  />
                )}
                {active.stability?.consistency_score != null && (
                  <MetricChip
                    label="Consistency"
                    value={formatScore(active.stability.consistency_score)}
                    help={METRIC_HELP.consistency}
                  />
                )}
                {active.stability?.worst_period != null && (
                  <MetricChip
                    label="Worst period"
                    value={formatPct(active.stability.worst_period)}
                    help={METRIC_HELP.worstPeriod}
                  />
                )}
                {active.stability?.volatility != null && (
                  <MetricChip
                    label="Volatility"
                    value={formatPct(active.stability.volatility)}
                    help={METRIC_HELP.volatility}
                  />
                )}
                {active.periodDays ? (
                  <span className="explore-dock-results-note">{active.periodDays} calendar days</span>
                ) : null}
                {active.stability?.note && (
                  <span className="explore-dock-results-note">{active.stability.note}</span>
                )}
              </div>
            )}
            <p className="explore-dock-foot">
              The period is split into equal windows; Stability combines consistency, worst period,
              and volatility. Hover a metric for details.
            </p>
          </div>
          <ExploreChart points={active.chartPoints ?? []} />
        </div>
      )}
    </section>
  );
}

export function createExploreSession(
  strategyId: string,
  title: string,
  params: Record<string, number>,
  initialCapital: number,
  limits: ExploreLimits
): ExploreSession {
  const range = defaultDateRange(limits);
  return {
    id: crypto.randomUUID(),
    strategyId,
    title,
    params,
    initialCapital,
    status: "idle",
    ...range,
  };
}

export function useExploreLimits() {
  const [limits, setLimits] = useState<ExploreLimits | null>(null);
  useEffect(() => {
    fetch("/api/explore", { cache: "no-store" })
      .then((res) => res.json())
      .then((json: ExploreLimits & { ok?: boolean }) => setLimits(json))
      .catch(() => setLimits(null));
  }, []);
  return limits;
}

export function useExploreRestore(onRestore: (sessions: ExploreSession[]) => void) {
  const handleRestore = useCallback(async () => {
    try {
      const [listRes, stored] = await Promise.all([
        fetch("/api/explore?list=1", { cache: "no-store" }),
        Promise.resolve(loadStoredExploreSessions()),
      ]);
      const listJson = (await listRes.json()) as { ok?: boolean; jobs?: ExploreJob[] };
      const jobs = listJson.ok && Array.isArray(listJson.jobs) ? listJson.jobs : [];
      const merged = mergeExploreSessions(stored, jobs);
      if (merged.length) onRestore(merged);
    } catch {
      const stored = loadStoredExploreSessions();
      if (stored.length) onRestore(stored);
    }
  }, [onRestore]);

  useEffect(() => {
    void handleRestore();
  }, [handleRestore]);
}

export function useExploreJobPolling(
  sessions: ExploreSession[],
  onJobUpdate: (sessionId: string, job: Record<string, unknown>) => void
) {
  useEffect(() => {
    const active = sessions.filter(
      (s) => s.jobId && (s.status === "running" || s.status === "queued")
    );
    if (!active.length) return;

    let cancelled = false;
    const poll = async () => {
      for (const session of active) {
        if (!session.jobId) continue;
        try {
          const res = await fetch(`/api/explore?job_id=${encodeURIComponent(session.jobId)}`, {
            cache: "no-store",
          });
          const json = (await res.json()) as { ok?: boolean; job?: Record<string, unknown> };
          if (!cancelled && json.ok && json.job) {
            onJobUpdate(session.id, json.job);
          }
        } catch {
          // keep polling
        }
      }
    };

    poll();
    const timer = setInterval(poll, 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [sessions, onJobUpdate]);
}

export function applyExploreJobUpdate(
  session: ExploreSession,
  job: Record<string, unknown>
): ExploreSession {
  const mapped = jobToExploreSession(job as ExploreJob);
  return {
    ...session,
    ...mapped,
    id: session.id,
    jobId: mapped.jobId ?? session.jobId,
  };
}
