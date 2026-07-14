"use client";

import { WorkflowMarketPicker } from "@/components/WorkflowMarketPicker";
import { botSessionFingerprint, dedupeByFingerprint } from "@/lib/session-fingerprint";
import {
  botRollingWindowMaxDays,
  loadWorkflowMarketDefaults,
  pollSecondsForTimeframe,
  sourceDisplayName,
  type WorkflowConfigSchema,
  type WorkflowMarketSelection,
} from "@/lib/workflow-config";
import { useCallback, useEffect, useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type BotValidation = {
  validation_run_id?: string;
  source_backtest_run_id?: string;
  total_pnl?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  win_rate?: number;
  deposit_baseline_pnl?: number;
  return_pct?: number;
};

export type BotChartPoint = {
  date: string;
  strategy_index: number;
  benchmark_index: number;
  equity?: number;
  close?: number;
};

export type BotSession = {
  id: string;
  jobId?: string;
  strategyId: string;
  title: string;
  params: Record<string, number>;
  instrument: string;
  timeframe: string;
  dataSource: string;
  brokerSource: string;
  daysToFetch: number;
  useSandbox: boolean;
  initialCapital: number;
  status: "idle" | "queued" | "running" | "stopped" | "completed" | "error";
  error?: string;
  validation?: BotValidation;
  tradeCount?: number;
  candleCount?: number;
  candleSource?: string;
  periodStart?: string;
  periodEnd?: string;
  paperEvents?: string[];
  lastTrade?: {
    entry_price?: number;
    exit_price?: number | null;
    quantity?: number;
    pnl?: number;
  };
  chartPoints?: BotChartPoint[];
  tradeLog?: Array<{ timestamp: string; action: string; price: number }>;
  tick?: number;
  lastTickAt?: string;
  pollSeconds?: number;
};

export const BOT_STORAGE_KEY = "backtestbench.bot.sessions.v1";
export const BOT_DISMISSED_KEY = "backtestbench.bot.dismissed.v1";

const METRIC_HELP = {
  return: "Live return on the rolling window: total P&L ÷ starting capital.",
  pnl: "Realized profit/loss on the current live slice.",
  sharpe: "Annualized Sharpe ratio on the live equity curve.",
  drawdown: "Largest peak-to-trough decline on the live slice.",
  winRate: "Share of profitable closed trades in the live run.",
  trades: "Closed trades on the current rolling window.",
} as const;

type BotJob = {
  job_id: string;
  strategy_id: string;
  title?: string;
  params?: Record<string, number>;
  instrument?: string;
  timeframe?: string;
  broker_source?: string;
  days_to_fetch?: number;
  use_sandbox?: boolean;
  initial_capital?: number;
  status: string;
  error?: string;
  validation?: BotValidation;
  trade_count?: number;
  candle_count?: number;
  candle_source?: string;
  period_start?: string;
  period_end?: string;
  paper_events?: string[];
  last_trade?: BotSession["lastTrade"];
  chart_points?: BotChartPoint[];
  trade_log?: BotSession["tradeLog"];
  tick?: number;
  last_tick_at?: string;
  poll_seconds?: number;
};

function mapJobStatus(status: string): BotSession["status"] {
  if (status === "queued" || status === "running" || status === "completed" || status === "error") {
    return status;
  }
  if (status === "stopped" || status === "stopping") {
    return "stopped";
  }
  return "idle";
}

export function jobToBotSession(job: BotJob): BotSession {
  const brokerSource = job.broker_source ?? "tbank";
  const timeframe = job.timeframe ?? "1h";
  return {
    id: job.job_id,
    jobId: job.job_id,
    strategyId: job.strategy_id,
    title: job.title ?? job.strategy_id,
    params: job.params ?? {},
    instrument: job.instrument ?? "SBER",
    timeframe,
    dataSource: sourceDisplayName(brokerSource),
    brokerSource,
    daysToFetch: job.days_to_fetch ?? 7,
    useSandbox: job.use_sandbox ?? brokerSource === "tbank",
    initialCapital: job.initial_capital ?? 100_000,
    status: mapJobStatus(job.status),
    error: job.error,
    validation: job.validation,
    tradeCount: job.trade_count,
    candleCount: job.candle_count,
    candleSource: job.candle_source,
    periodStart: job.period_start,
    periodEnd: job.period_end,
    paperEvents: job.paper_events,
    lastTrade: job.last_trade,
    chartPoints: job.chart_points,
    tradeLog: job.trade_log,
    tick: job.tick,
    lastTickAt: job.last_tick_at,
    pollSeconds: job.poll_seconds ?? pollSecondsForTimeframe(timeframe),
  };
}

export function loadStoredBotSessions(): BotSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(BOT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as BotSession[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function loadDismissedBotIds(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(BOT_DISMISSED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as string[];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

export function dismissBotSession(session: Pick<BotSession, "id" | "jobId">) {
  if (typeof window === "undefined") return;
  const dismissed = loadDismissedBotIds();
  dismissed.add(session.id);
  if (session.jobId) dismissed.add(session.jobId);
  try {
    window.localStorage.setItem(BOT_DISMISSED_KEY, JSON.stringify(Array.from(dismissed)));
  } catch {
    // ignore quota errors
  }
}

export async function stopBotJob(jobId: string) {
  await fetch("/api/bot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "stop", job_id: jobId }),
  });
}

export async function deleteBotJob(jobId: string) {
  await fetch(`/api/bot?job_id=${encodeURIComponent(jobId)}`, { method: "DELETE" });
}

export function saveBotSessions(sessions: BotSession[]) {
  if (typeof window === "undefined") return;
  const dismissed = loadDismissedBotIds();
  const filtered = sessions.filter(
    (session) =>
      !dismissed.has(session.id) && !(session.jobId && dismissed.has(session.jobId))
  );
  const deduped = dedupeByFingerprint(filtered, botSessionFingerprint);
  try {
    window.localStorage.setItem(BOT_STORAGE_KEY, JSON.stringify(deduped));
  } catch {
    // ignore quota errors
  }
}

export function mergeBotSessions(
  stored: BotSession[],
  jobs: BotJob[],
  dismissed: Set<string> = loadDismissedBotIds()
): BotSession[] {
  const merged = new Map<string, BotSession>();

  for (const job of jobs) {
    if (dismissed.has(job.job_id)) continue;
    merged.set(job.job_id, jobToBotSession(job));
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

  return dedupeByFingerprint(
    Array.from(merged.values()).sort((a, b) => {
      const aKey = a.jobId ?? a.id;
      const bKey = b.jobId ?? b.id;
      return bKey.localeCompare(aKey);
    }),
    botSessionFingerprint
  );
}

export function findBotSessionByFingerprint(
  sessions: BotSession[],
  next: Pick<
    BotSession,
    "strategyId" | "params" | "instrument" | "timeframe" | "daysToFetch" | "brokerSource"
  >
) {
  const key = botSessionFingerprint(next);
  return sessions.find((session) => botSessionFingerprint(session) === key) ?? null;
}

function formatPct(fraction: number | null | undefined) {
  if (fraction == null) return "—";
  const sign = fraction >= 0 ? "+" : "−";
  return `${sign}${new Intl.NumberFormat("ru-RU", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Math.abs(fraction))}`;
}

function formatMoney(value: number | null | undefined) {
  if (value == null) return "—";
  const sign = value >= 0 ? "+" : "−";
  return `${sign}${new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(Math.abs(value))}`;
}

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value == null) return "—";
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

function formatTickTime(value: string | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 19);
  return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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

function statusLabel(status: BotSession["status"]) {
  if (status === "running") return "Live";
  if (status === "queued") return "Starting";
  if (status === "stopped") return "Stopped";
  if (status === "completed") return "Done";
  if (status === "error") return "Error";
  return "Ready";
}

function BotLiveChart({
  points,
  live,
}: {
  points: BotChartPoint[];
  live?: boolean;
}) {
  const visible = useMemo(() => points.slice(-120), [points]);

  if (!visible.length) {
    return (
      <div className="explore-dock-chart-empty bot-live-chart-empty">
        {live ? "Fetching live candles… chart updates on each tick." : "Start the trading bot to see the live chart."}
      </div>
    );
  }

  return (
    <div className="explore-dock-chart bot-live-chart">
      {live && <span className="bot-live-pill">Live</span>}
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={visible} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#c8d3e4" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10 }}
            minTickGap={28}
            tickFormatter={(value: string) => value.slice(5, 16).replace("T", " ")}
          />
          <YAxis width={40} tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
          <Tooltip
            labelFormatter={(value) => String(value).slice(0, 19).replace("T", " ")}
            formatter={(value, name) => [
              `${Number(value ?? 0).toFixed(2)}`,
              name === "strategy_index" ? "Strategy" : "Benchmark",
            ]}
          />
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
            stroke="#0f7a58"
            strokeWidth={2}
            dot={false}
            isAnimationActive={live}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BotDockPanel({
  sessions,
  activeId,
  schema,
  onPatch,
  onRun,
  onStop,
}: {
  sessions: BotSession[];
  activeId: string | null;
  schema: WorkflowConfigSchema;
  onPatch: (id: string, patch: Partial<BotSession>) => void;
  onRun: (id: string) => Promise<void>;
  onStop: (id: string) => Promise<void>;
}) {
  const active = sessions.find((s) => s.id === activeId) ?? sessions[0];
  if (!active) return null;

  const isLive = active.status === "running" || active.status === "queued";
  const runningCount = sessions.filter((s) => s.status === "running" || s.status === "queued").length;
  const maxDays = useMemo(
    () => botRollingWindowMaxDays(schema, active.brokerSource, active.timeframe),
    [schema, active.brokerSource, active.timeframe]
  );
  const pollSeconds = active.pollSeconds ?? pollSecondsForTimeframe(active.timeframe);

  const handleMarketChange = (selection: WorkflowMarketSelection) => {
    const nextMaxDays = botRollingWindowMaxDays(schema, selection.brokerSource, active.timeframe);
    onPatch(active.id, {
      brokerSource: selection.brokerSource,
      instrument: selection.instrument,
      dataSource: selection.dataSource,
      daysToFetch: Math.min(active.daysToFetch, nextMaxDays),
      useSandbox: selection.brokerSource === "tbank" ? active.useSandbox : false,
      jobId: undefined,
      status: "idle",
      error: undefined,
      validation: undefined,
      tradeCount: undefined,
      candleCount: undefined,
      candleSource: undefined,
      periodStart: undefined,
      periodEnd: undefined,
      paperEvents: undefined,
      lastTrade: undefined,
      chartPoints: undefined,
      tradeLog: undefined,
      tick: undefined,
      lastTickAt: undefined,
    });
  };

  return (
    <div className="explore-dock-body bot-dock-body bot-dock-body-live">
      <div className="explore-dock-controls">
        <p className="explore-dock-meta">
          <span className="workflow-kind-badge is-bot">Trading Bot</span>
          {active.strategyId} · {active.dataSource} · {active.instrument} · {active.timeframe}
        </p>
        <p className="bot-dock-subtitle">
          Runs your strategy continuously on the freshest broker candles. The chart shifts as new
          data arrives every {pollSeconds}s. Orders are simulated.
        </p>
        {runningCount >= 2 && (
          <p className="bot-dock-concurrency-note">
            {runningCount} bots are running and share the local candle cache.
          </p>
        )}
        <WorkflowMarketPicker
          schema={schema}
          brokerSource={active.brokerSource}
          instrument={active.instrument}
          disabled={isLive}
          onChange={handleMarketChange}
        />
        <div className="explore-dock-params">
          {Object.entries(active.params)
            .filter(([k]) => k !== "order_size")
            .map(([k, v]) => (
              <span key={k} className="explore-dock-param">
                {k}={v}
              </span>
            ))}
        </div>
        <div className="explore-dock-dates bot-dock-settings">
          <label>
            Rolling window (days)
            <input
              type="number"
              min={1}
              max={maxDays}
              value={active.daysToFetch}
              disabled={isLive}
              onChange={(e) =>
                onPatch(active.id, { daysToFetch: Math.max(1, Number(e.target.value) || 1) })
              }
            />
          </label>
          {active.brokerSource === "tbank" && (
            <label
              className="bot-dock-sandbox"
              title="Use T-Bank sandbox API host for candle fetches (paper environment, not production trading)."
            >
              <input
                type="checkbox"
                checked={active.useSandbox}
                disabled={isLive}
                onChange={(e) => onPatch(active.id, { useSandbox: e.target.checked })}
              />
              Sandbox API
            </label>
          )}
        </div>
        <p className="explore-dock-hint">
          Polls {active.dataSource} API every {pollSeconds}s · window {active.daysToFetch}d
          {active.brokerSource === "tbank" && active.useSandbox ? " · T-Bank sandbox host" : ""}
        </p>
        <div className="explore-dock-actions">
          {isLive ? (
            <button className="control-btn bot-stop-btn" type="button" onClick={() => onStop(active.id)}>
              Stop bot
            </button>
          ) : (
            <button
              className="control-btn control-btn-run bot-run-btn"
              type="button"
              disabled={active.status === "queued"}
              onClick={() => onRun(active.id)}
            >
              Start trading bot
            </button>
          )}
          <span className={`explore-dock-status is-${active.status}`}>{statusLabel(active.status)}</span>
          {active.tick != null && active.tick > 0 && (
            <span className="explore-dock-results-note">Tick {active.tick}</span>
          )}
          {active.lastTickAt && (
            <span className="explore-dock-results-note">Updated {formatTickTime(active.lastTickAt)}</span>
          )}
        </div>
        {active.error && <p className="explore-dock-error">{active.error}</p>}
        {active.validation && (
          <div className="explore-dock-results">
            {active.validation.return_pct != null && (
              <MetricChip
                label="Return"
                value={formatPct(active.validation.return_pct)}
                help={METRIC_HELP.return}
              />
            )}
            {active.validation.total_pnl != null && (
              <MetricChip label="P&L" value={formatMoney(active.validation.total_pnl)} help={METRIC_HELP.pnl} />
            )}
            {active.validation.sharpe_ratio != null && (
              <MetricChip
                label="Sharpe"
                value={formatNumber(active.validation.sharpe_ratio)}
                help={METRIC_HELP.sharpe}
              />
            )}
            {active.validation.max_drawdown != null && (
              <MetricChip
                label="Max DD"
                value={formatPct(active.validation.max_drawdown)}
                help={METRIC_HELP.drawdown}
              />
            )}
            {active.validation.win_rate != null && (
              <MetricChip
                label="Win rate"
                value={formatPct(active.validation.win_rate)}
                help={METRIC_HELP.winRate}
              />
            )}
            {active.tradeCount != null && (
              <MetricChip label="Trades" value={String(active.tradeCount)} help={METRIC_HELP.trades} />
            )}
            {active.candleCount ? (
              <span className="explore-dock-results-note">
                {active.candleCount} candles from {active.candleSource ?? active.dataSource}
              </span>
            ) : null}
          </div>
        )}
        {active.paperEvents && active.paperEvents.length > 0 && (
          <div className="bot-paper-log">
            <p className="bot-paper-log-title">Latest activity</p>
            <ul>
              {active.paperEvents.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <BotLiveChart points={active.chartPoints ?? []} live={active.status === "running"} />
    </div>
  );
}

export function createBotSession(
  strategyId: string,
  title: string,
  params: Record<string, number>,
  initialCapital: number,
  schema: WorkflowConfigSchema
): BotSession {
  const market = loadWorkflowMarketDefaults(schema);
  const timeframe = String(schema.defaults.timeframe ?? "1h");
  const maxDays = botRollingWindowMaxDays(schema, market.brokerSource, timeframe);
  return {
    id: crypto.randomUUID(),
    strategyId,
    title,
    params,
    instrument: market.instrument,
    timeframe,
    dataSource: market.dataSource,
    brokerSource: market.brokerSource,
    daysToFetch: Math.min(7, maxDays),
    useSandbox: market.brokerSource === "tbank",
    initialCapital,
    pollSeconds: pollSecondsForTimeframe(timeframe),
    status: "idle",
  };
}

export function useBotRestore(onRestore: (sessions: BotSession[]) => void) {
  const handleRestore = useCallback(async () => {
    try {
      const [listRes, stored] = await Promise.all([
        fetch("/api/bot?list=1", { cache: "no-store" }),
        Promise.resolve(loadStoredBotSessions()),
      ]);
      const listJson = (await listRes.json()) as { ok?: boolean; jobs?: BotJob[] };
      const jobs = listJson.ok && Array.isArray(listJson.jobs) ? listJson.jobs : [];
      const merged = mergeBotSessions(stored, jobs);
      if (merged.length) onRestore(merged);
    } catch {
      const stored = loadStoredBotSessions();
      if (stored.length) onRestore(stored);
    }
  }, [onRestore]);

  useEffect(() => {
    void handleRestore();
  }, [handleRestore]);
}

export function useBotJobPolling(
  sessions: BotSession[],
  onJobUpdate: (sessionId: string, job: Record<string, unknown>) => void
) {
  useEffect(() => {
    const active = sessions.filter((s) => s.jobId && s.status === "running");
    if (!active.length) return;

    let cancelled = false;
    const poll = async () => {
      for (const session of active) {
        if (!session.jobId) continue;
        try {
          const res = await fetch(`/api/bot?job_id=${encodeURIComponent(session.jobId)}`, {
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
    const timer = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [sessions, onJobUpdate]);
}

export function applyBotJobUpdate(
  session: BotSession,
  job: Record<string, unknown>
): BotSession {
  const mapped = jobToBotSession(job as BotJob);
  return {
    ...session,
    ...mapped,
    id: session.id,
    jobId: mapped.jobId ?? session.jobId,
  };
}
