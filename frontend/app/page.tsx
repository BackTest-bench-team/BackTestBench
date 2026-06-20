"use client";

import { useEffect, useMemo, useState } from "react";

type PipelineStep = {
  name: string;
  status: "pending" | "running" | "done" | "error";
};

type EquityPoint = {
  date: string;
  value: number;
};

type DashboardData = {
  strategy_id: string;
  instrument: string;
  metrics: {
    total_pnl: number;
    sharpe_ratio: number;
    max_drawdown: number;
    win_rate: number;
    deposit_baseline_pnl: number;
  };
  pipeline: PipelineStep[];
  equity_points: EquityPoint[];
  last_updated: string | null;
  error?: string | null;
};

const POLL_MS = 5000;

const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

const percent = new Intl.NumberFormat("ru-RU", {
  style: "percent",
  maximumFractionDigits: 1,
});

const number = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 2,
});

function formatDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
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
  hint?: string;
}) {
  return (
    <div className="card metric-card">
      <div className="metric-title">{title}</div>
      <div className="metric-value">{value}</div>
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </div>
  );
}

function PipelineStatus({ steps }: { steps: PipelineStep[] }) {
  return (
    <div className="card">
      <div className="section-title">Pipeline status</div>
      <div className="pipeline-grid">
        {steps.map((step) => (
          <div key={step.name} className="pipeline-step">
            <div className="pipeline-name">{step.name}</div>
            <div className={`badge badge-${step.status}`}>{step.status}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EquityChart({ points }: { points: EquityPoint[] }) {
  const { pathD, min, max } = useMemo(() => {
    if (!points || points.length < 2) {
      return { pathD: "", min: 0, max: 0 };
    }

    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;

    const width = 100;
    const height = 100;

    const d = points
      .map((p, i) => {
        const x = (i / (points.length - 1)) * width;
        const y = height - ((p.value - min) / range) * height;
        return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");

    return { pathD: d, min, max };
  }, [points]);

  if (!points || points.length < 2) {
    return (
      <div className="card">
        <div className="section-title">Portfolio chart</div>
        <div className="empty-state">Not enough data for chart.</div>
      </div>
    );
  }

  const first = points[0];
  const last = points[points.length - 1];

  return (
    <div className="card">
      <div className="section-title">Portfolio chart</div>
      <div className="chart-meta">
        <span>{first.date}</span>
        <span>
          {money.format(first.value)} → {money.format(last.value)}
        </span>
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
          d={`${pathD} L 100 100 L 0 100 Z`}
          className="chart-area"
          fill="url(#areaFade)"
        />
        <path d={pathD} className="chart-line" />
      </svg>

      <div className="chart-footer">
        <span>Min: {money.format(min)}</span>
        <span>Max: {money.format(max)}</span>
      </div>
    </div>
  );
}

export default function Page() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusText, setStatusText] = useState("Idle");

  const loadDashboard = async () => {
    try {
      const res = await fetch("/api/dashboard", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as DashboardData;
      setData(json);
      setError(json.error ?? null);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
    const id = setInterval(loadDashboard, POLL_MS);
    return () => clearInterval(id);
  }, []);

  const handleRunBacktest = async () => {
    setRunning(true);
    setStatusText("Queued → Data Loader → Strategy Module → Simulation Engine → Analytics Module");

    const pipelineSequence = [
      "Data Loader",
      "Strategy Module",
      "Simulation Engine",
      "Analytics Module",
    ];

    // Локальная визуальная имитация запуска, без реального backend.
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        pipeline: prev.pipeline.map((step, idx) => ({
          ...step,
          status: idx === 0 ? "running" : "pending",
        })),
      };
    });

    for (let i = 0; i < pipelineSequence.length; i++) {
      await new Promise((resolve) => setTimeout(resolve, 450));
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          pipeline: prev.pipeline.map((step, idx) => {
            if (idx < i) return { ...step, status: "done" };
            if (idx === i) return { ...step, status: "running" };
            return { ...step, status: "pending" };
          }),
        };
      });
    }

    await new Promise((resolve) => setTimeout(resolve, 450));
    await loadDashboard();
    setStatusText("Backtest completed");
    setRunning(false);
  };

  const metrics = data?.metrics;

  return (
    <main className="page">
      <div className="shell">
        <header className="header card">
          <div>
            <div className="brand">BackTestBench</div>
            <h1 className="title">MVP 1 Dashboard</h1>
            <div className="subtitle">
              {data?.strategy_id ?? "—"} · {data?.instrument ?? "—"}
            </div>
          </div>

          <div className="header-actions">
            <button className="button" onClick={handleRunBacktest} disabled={running}>
              {running ? "Running..." : "Run backtest"}
            </button>
            <div className="status-line">{statusText}</div>
            <div className="status-line small">
              Last refresh: {formatDate(data?.last_updated ?? null)}
            </div>
          </div>
        </header>

        {loading ? <div className="card">Loading dashboard...</div> : null}

        {error ? (
          <div className="card error-card">
            <strong>Warning:</strong> {error}
          </div>
        ) : null}

        {data ? <PipelineStatus steps={data.pipeline} /> : null}

        {metrics ? (
          <section className="metrics-grid">
            <MetricCard
              title="Total P&L"
              value={money.format(metrics.total_pnl)}
              hint="Realized performance"
            />
            <MetricCard
              title="Sharpe ratio"
              value={number.format(metrics.sharpe_ratio)}
              hint="Risk-adjusted return"
            />
            <MetricCard
              title="Max drawdown"
              value={percent.format(metrics.max_drawdown)}
              hint="Peak-to-trough decline"
            />
            <MetricCard
              title="Win rate"
              value={percent.format(metrics.win_rate)}
              hint="Profitable trades share"
            />
            <MetricCard
              title="Deposit baseline"
              value={money.format(metrics.deposit_baseline_pnl)}
              hint="13% annual baseline"
            />
          </section>
        ) : null}

        {data ? <EquityChart points={data.equity_points} /> : null}
      </div>

      <style jsx>{`
        :global(html, body) {
          margin: 0;
          padding: 0;
          background: #0b1220;
          color: #e5e7eb;
          font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        }

        :global(*) {
          box-sizing: border-box;
        }

        .page {
          min-height: 100vh;
          padding: 24px;
        }

        .shell {
          max-width: 1200px;
          margin: 0 auto;
          display: grid;
          gap: 16px;
        }

        .card {
          background: rgba(17, 24, 39, 0.92);
          border: 1px solid rgba(148, 163, 184, 0.18);
          border-radius: 18px;
          padding: 20px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
        }

        .header {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: flex-start;
          flex-wrap: wrap;
        }

        .brand {
          font-size: 13px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: #93c5fd;
          margin-bottom: 8px;
        }

        .title {
          margin: 0;
          font-size: 28px;
          line-height: 1.1;
        }

        .subtitle {
          margin-top: 8px;
          color: #94a3b8;
        }

        .header-actions {
          display: grid;
          gap: 10px;
          justify-items: end;
        }

        .button {
          border: 0;
          border-radius: 12px;
          padding: 12px 18px;
          font-weight: 700;
          background: #3b82f6;
          color: white;
          cursor: pointer;
        }

        .button:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .status-line {
          color: #cbd5e1;
          font-size: 14px;
          text-align: right;
        }

        .status-line.small {
          font-size: 12px;
          color: #94a3b8;
        }

        .error-card {
          border-color: rgba(248, 113, 113, 0.35);
          color: #fecaca;
        }

        .section-title {
          font-size: 16px;
          font-weight: 700;
          margin-bottom: 14px;
        }

        .pipeline-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 12px;
        }

        .pipeline-step {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 14px;
          border-radius: 14px;
          background: rgba(30, 41, 59, 0.8);
        }

        .pipeline-name {
          font-weight: 600;
        }

        .badge {
          border-radius: 999px;
          padding: 6px 10px;
          font-size: 12px;
          text-transform: capitalize;
        }

        .badge-done {
          background: rgba(34, 197, 94, 0.16);
          color: #86efac;
        }

        .badge-running {
          background: rgba(59, 130, 246, 0.16);
          color: #93c5fd;
        }

        .badge-pending {
          background: rgba(148, 163, 184, 0.16);
          color: #cbd5e1;
        }

        .badge-error {
          background: rgba(239, 68, 68, 0.16);
          color: #fca5a5;
        }

        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 16px;
        }

        .metric-card {
          min-height: 120px;
          display: grid;
          gap: 10px;
        }

        .metric-title {
          font-size: 14px;
          color: #94a3b8;
        }

        .metric-value {
          font-size: 28px;
          font-weight: 800;
          letter-spacing: -0.02em;
        }

        .metric-hint {
          font-size: 13px;
          color: #cbd5e1;
        }

        .chart {
          width: 100%;
          height: 280px;
          display: block;
          margin-top: 10px;
        }

        .chart-grid {
          stroke: rgba(148, 163, 184, 0.12);
          stroke-width: 0.6;
        }

        .chart-line {
          fill: none;
          stroke: #60a5fa;
          stroke-width: 1.8;
        }

        .chart-area {
          stroke: none;
        }

        .chart-meta,
        .chart-footer {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          color: #94a3b8;
          font-size: 13px;
        }

        .empty-state {
          color: #94a3b8;
          padding: 12px 0;
        }

        @media (max-width: 720px) {
          .page {
            padding: 14px;
          }

          .header-actions {
            justify-items: start;
          }

          .status-line {
            text-align: left;
          }
        }
      `}</style>
    </main>
  );
}