"use client";

import { useEffect, useMemo, useState } from "react";

type PipelineStep = {
  name: string;
  status: "pending" | "running" | "done" | "skipped" | "error";
};

type EquityPoint = {
  date: string;
  value: number;
};

type DashboardData = {
  run_id: string;
  strategy_id: string;
  strategy_version: string;
  instrument: string;
  timeframe: string;
  data_source: string;
  status: string;
  current_stage: string;
  pipeline: PipelineStep[];
  metrics: {
    total_pnl: number | null;
    sharpe_ratio: number | null;
    max_drawdown: number | null;
    win_rate: number | null;
    deposit_baseline_pnl: number | null;
  };
  equity_points: EquityPoint[];
  trade_count: number;
  final_portfolio: {
    cash: number | null;
    position_size: number | null;
    equity: number | null;
  };
  message: string;
  error: string | null;
  last_updated: string | null;
};

const POLL_MS = 3000;

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("ru-RU");
}

function MetricCard({
  title,
  value,
  hint,
}: {
  title: string;
  value: string;
  hint: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-title">{title}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-hint">{hint}</div>
    </article>
  );
}

function PipelineStatus({
  currentStage,
  message,
  steps,
}: {
  currentStage: string;
  message: string;
  steps: PipelineStep[];
}) {
  const safeSteps = Array.isArray(steps) ? steps : [];

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2 className="section-title">Pipeline status</h2>
          <div className="panel-subtitle">Current stage: {currentStage}</div>
        </div>
        <div className="panel-note">{message}</div>
      </div>

      {safeSteps.length === 0 ? (
        <div className="chart-empty">Pipeline has not started yet.</div>
      ) : (
        <div className="pipeline-list">
          {safeSteps.map((step) => (
            <div key={step.name} className="pipeline-row">
              <div className="pipeline-name">{step.name}</div>
              <div className={`badge badge-${step.status}`}>{step.status}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function EquityChart({ points }: { points: EquityPoint[] }) {
  const chart = useMemo(() => {
    if (!points || points.length < 2) {
      return { pathD: "", min: 0, max: 0 };
    }

    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;

    const width = 100;
    const height = 100;

    const pathD = points
      .map((p, i) => {
        const x = (i / (points.length - 1)) * width;
        const y = height - ((p.value - min) / range) * height;
        return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");

    return { pathD, min, max };
  }, [points]);

  if (!points || points.length < 2) {
    return (
      <section className="panel">
        <h2 className="section-title">Portfolio chart</h2>
        <div className="chart-empty">No equity data yet.</div>
      </section>
    );
  }

  const first = points[0];
  const last = points[points.length - 1];

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2 className="section-title">Portfolio chart</h2>
          <div className="panel-subtitle">
            {first.date} → {last.date}
          </div>
        </div>
        <div className="panel-note">
          Min: {formatMoney(chart.min)} · Max: {formatMoney(chart.max)}
        </div>
      </div>

      <svg viewBox="0 0 100 100" className="chart" preserveAspectRatio="none">
        <defs>
          <linearGradient id="areaFade" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopOpacity="0.25" />
            <stop offset="100%" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {[0, 25, 50, 75, 100].map((y) => (
          <line key={y} x1="0" y1={y} x2="100" y2={y} className="chart-grid" />
        ))}

        <path
          d={`${chart.pathD} L 100 100 L 0 100 Z`}
          fill="url(#areaFade)"
          className="chart-area"
        />
        <path d={chart.pathD} className="chart-line" />
      </svg>
    </section>
  );
}

export default function Page() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = async () => {
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const json = (await response.json()) as DashboardData;
      setData(json);
      setError(json.error ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
    const timer = setInterval(loadDashboard, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  const runBacktest = async () => {
    setStarting(true);
    setError(null);

    try {
      const res = await fetch("/api/run", { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start pipeline");
    } finally {
      setStarting(false);
    }
  };

  const metrics = data?.metrics;

  return (
    <main className="app-shell">
      <header className="panel topbar">
        <div>
          <div className="brand">BackTestBench</div>
          <h1 className="title">MVP 1 Dashboard</h1>

          <div className="subtitle">
            Strategy: {data?.strategy_id || "—"} · Version: {data?.strategy_version || "—"}
          </div>
          <div className="subtitle">
            Instrument: {data?.instrument || "—"} · Timeframe: {data?.timeframe || "—"}
          </div>
          <div className="subtitle">
            Data source: {data?.data_source || "—"} · Run: {data?.run_id || "—"}
          </div>
          <div className="subtitle">
            Current stage: {data?.current_stage || "—"}
          </div>
        </div>

        <div className="actions">
          <button className="button" onClick={runBacktest} disabled={starting}>
            {starting ? "Starting..." : "Run backtest"}
          </button>

          <div className="status-line">
            {data?.status === "error"
              ? `Error: ${data.error || data.message}`
              : data?.message || "Idle"}
          </div>
          <div className="status-line small">
            Trades: {data?.trade_count ?? 0}
          </div>
          <div className="status-line small">
            Last refresh: {formatDate(data?.last_updated)}
          </div>
        </div>
      </header>

      {loading ? <section className="panel">Loading dashboard...</section> : null}

      {error ? (
        <section className="panel error-card">
          Warning: {error}
        </section>
      ) : null}

      {data ? (
        <PipelineStatus
          currentStage={data.current_stage}
          message={data.message}
          steps={data.pipeline}
        />
      ) : null}

      <section className="metrics-grid">
        <MetricCard
          title="Total P&L"
          value={formatMoney(metrics?.total_pnl)}
          hint="Realized performance"
        />
        <MetricCard
          title="Sharpe ratio"
          value={formatNumber(metrics?.sharpe_ratio)}
          hint="Risk-adjusted return"
        />
        <MetricCard
          title="Max drawdown"
          value={formatPercent(metrics?.max_drawdown)}
          hint="Peak-to-trough decline"
        />
        <MetricCard
          title="Win rate"
          value={formatPercent(metrics?.win_rate)}
          hint="Profitable trades share"
        />
        <MetricCard
          title="Deposit baseline"
          value={formatMoney(metrics?.deposit_baseline_pnl)}
          hint="13% annual baseline"
        />
      </section>

      <EquityChart points={data?.equity_points ?? []} />
    </main>
  );
}