"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BacktestControlPanel,
  type RuntimeSettings,
} from "@/components/BacktestControlPanel";
import { AddStrategyPanel } from "@/components/AddStrategyPanel";
import { sourceDisplayName } from "@/lib/workflow-config";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type ParamSpec = {
  name: string;
  type: string;
  default: number | string | boolean;
  minimum?: number;
  maximum?: number;
  description?: string;
};

type ChartPoint = {
  date: string;
  strategy_index: number;
  benchmark_index: number;
  equity: number;
  close: number;
};

type TradePoint = {
  timestamp: string;
  action: "BUY" | "SELL";
  price: number;
};

type ChartRow = ChartPoint & {
  action: "BUY" | "SELL" | null;
  alpha: number;
  in_position: boolean;
  strategy_solid: number | null;
  strategy_flat: number | null;
  trade_marker: number | null;
};

type OptimizationSummary = {
  target_metric: string;
  mode: string;
  grid_size: number;
  iterations_requested: number;
  iterations_run: number;
  exhaustive: boolean;
  seed: number;
  top_iterations: Array<{
    params: Record<string, number>;
    total_pnl: number;
    sharpe_ratio: number;
    score: number;
  }>;
};

type StrategyResult = {
  strategy_id: string;
  strategy_version: string;
  title?: string;
  status: "idle" | "running" | "completed" | "error";
  params: Record<string, number | boolean>;
  parameter_specs?: ParamSpec[];
  initial_capital: number;
  optimization?: OptimizationSummary;
  metrics: {
    total_pnl: number | null;
    sharpe_ratio: number | null;
    max_drawdown: number | null;
    win_rate: number | null;
    deposit_baseline_pnl: number | null;
    deposit_baseline_final?: number | null;
    profit_factor: number | null;
    calmar_ratio: number | null;
    consistency_pct: number | null;
    total_return_pct: number | null;
    vs_buy_hold_pct: number | null;
    positive_months: number | null;
    total_months: number | null;
  };
  live_active?: boolean;
  verdict?: {
    grade: "PASS" | "CAUTION" | "FAIL";
    flags: string[];
    vs_buy_hold_pct: number;
    vs_deposit_pct: number;
    profit_factor: number;
    consistency_pct: number;
    total_return_pct: number;
  } | null;
  chart_points?: ChartPoint[];
  trade_log?: TradePoint[];
  final_portfolio: {
    cash: number | null;
    position_size: number | null;
    equity: number | null;
  };
  error?: string | null;
};

type RankingEntry = {
  rank: number;
  strategy_id: string;
  instrument: string;
  run_id?: string;
  total_pnl: number;
  computed_at?: string;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  deposit_baseline_pnl: number;
  previous_rank?: number;
  rank_delta?: number;
};

type DashboardRanking = {
  computed_at: string | null;
  entries: RankingEntry[];
};

type DashboardData = {
  instrument: string;
  timeframe: string;
  data_source: string;
  initial_capital: number;
  strategies: StrategyResult[];
  ranking?: DashboardRanking;
  last_updated: string | null;
};

const POLL_IDLE_MS = 8000;
const POLL_RUNNING_MS = 1500;
const BASELINE = 100;

function livePollMs(timeframe: string) {
  const intervals: Record<string, number> = {
    "1m": 15_000,
    "5m": 30_000,
    "15m": 60_000,
    "30m": 90_000,
    "1h": 120_000,
    "1d": 300_000,
    "1w": 600_000,
    "1M": 900_000,
  };
  return intervals[timeframe] ?? 60_000;
}

const CHART = {
  strategy: "#475ee6",
  benchmark: "#6b7c93",
  brush: "#475ee6",
  buy: "#2f9e44",
  sell: "#c92a2a",
  grid: "#c8d3e4",
  axis: "#5c6b82",
};

function formatMoney(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(v);
}

function formatSignedPercent(fraction: number | null | undefined) {
  if (fraction === null || fraction === undefined) return null;
  const sign = fraction >= 0 ? "+" : "−";
  const pct = new Intl.NumberFormat("ru-RU", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Math.abs(fraction));
  return `${sign}${pct}`;
}

function formatSignedReturnPct(fraction: number | null | undefined) {
  if (fraction === null || fraction === undefined) return "—";
  return formatSignedPercent(fraction) ?? "—";
}

function formatReturnPct(
  amountRub: number | null | undefined,
  baseCapital: number | null | undefined
) {
  if (amountRub === null || amountRub === undefined) return "—";
  if (!baseCapital) return "—";
  return formatSignedReturnPct(amountRub / baseCapital);
}

function formatPercent(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(v);
}

function formatNumber(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(v);
}

function formatChartDate(value: string) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("ru-RU");
}

function formatIndex(value: number) {
  const delta = value - BASELINE;
  const sign = delta >= 0 ? "+" : "";
  return `${value.toFixed(1)} (${sign}${delta.toFixed(1)}%)`;
}

function formatAxisDate(value: string) {
  const d = new Date(String(value));
  return Number.isNaN(d.getTime())
    ? String(value)
    : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}


function buildInPositionByDate(points: ChartPoint[], trades: TradePoint[]) {
  const sortedTrades = [...trades].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const inPositionByDate = new Map<string, boolean>();
  let tradeIdx = 0;
  let inPosition = false;

  for (const point of points) {
    while (tradeIdx < sortedTrades.length && sortedTrades[tradeIdx].timestamp <= point.date) {
      inPosition = sortedTrades[tradeIdx].action === "BUY";
      tradeIdx += 1;
    }
    inPositionByDate.set(point.date, inPosition);
  }

  return inPositionByDate;
}

function buildChartRows(points: ChartPoint[], trades: TradePoint[]): ChartRow[] {
  const actionByDate = new Map(trades.map((t) => [t.timestamp, t.action]));
  const inPositionByDate = buildInPositionByDate(points, trades);

  const baseRows = points.map((point) => {
    const inPosition = inPositionByDate.get(point.date) ?? false;
    return {
      ...point,
      action: actionByDate.get(point.date) ?? null,
      alpha: point.strategy_index - point.benchmark_index,
      in_position: inPosition,
      strategy_solid: null as number | null,
      strategy_flat: null as number | null,
    };
  });

  return baseRows.map((row, index) => {
    const next = baseRows[index + 1];
    const prev = baseRows[index - 1];
    const bridgeToFlat = row.in_position && next && !next.in_position;
    const entering = row.in_position && (!prev || !prev.in_position);

    let action = row.action;
    if (!action && bridgeToFlat) action = "SELL";
    if (!action && entering) action = "BUY";

    return {
      ...row,
      action,
      strategy_solid: row.in_position || (next && !row.in_position && next.in_position) ? row.strategy_index : null,
      strategy_flat: !row.in_position || bridgeToFlat ? row.strategy_index : null,
      trade_marker: action ? row.strategy_index : null,
    };
  });
}


function needsRankingRefresh(strategies: StrategyResult[], ranking?: DashboardRanking) {
  if (!strategies.length) return false;
  const hasCompleted = strategies.some((s) => s.status === "completed");
  const hasRanking = (ranking?.entries?.length ?? 0) > 0;
  return hasCompleted && !hasRanking;
}

function strategyCardId(strategyId: string) {
  return `strategy-${strategyId}`;
}

function matchStrategyQuery(strategy: StrategyResult, query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return false;
  const title = strategy.title?.toLowerCase() ?? "";
  const id = strategy.strategy_id.toLowerCase();
  return title.includes(normalized) || id.includes(normalized);
}

function findStrategyByQuery(strategies: StrategyResult[], query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return null;
  return (
    strategies.find((strategy) => strategy.title?.toLowerCase() === normalized) ??
    strategies.find((strategy) => strategy.strategy_id.toLowerCase() === normalized) ??
    strategies.find((strategy) => matchStrategyQuery(strategy, normalized)) ??
    null
  );
}

function filterStrategySuggestions(strategies: StrategyResult[], query: string, limit = 6) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  return strategies.filter((strategy) => matchStrategyQuery(strategy, normalized)).slice(0, limit);
}

function StrategySearch({
  strategies,
  onNavigate,
}: {
  strategies: StrategyResult[];
  onNavigate: (strategyId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const suggestions = useMemo(
    () => filterStrategySuggestions(strategies, query),
    [strategies, query]
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function navigateTo(strategyId: string) {
    setError(null);
    setOpen(false);
    onNavigate(strategyId);
  }

  function submitSearch() {
    const match = findStrategyByQuery(strategies, query);
    if (!match) {
      setError("Strategy not found");
      return;
    }
    setQuery(match.title ?? match.strategy_id);
    navigateTo(match.strategy_id);
  }

  return (
    <div className="strategy-search" ref={containerRef}>
      <span className="strategy-search-label">Find strategy</span>
      <form
        className="strategy-search-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (open && suggestions[activeIndex]) {
            const picked = suggestions[activeIndex];
            setQuery(picked.title ?? picked.strategy_id);
            navigateTo(picked.strategy_id);
            return;
          }
          submitSearch();
        }}
      >
        <input
          className="strategy-search-input"
          type="text"
          role="searchbox"
          autoComplete="off"
          spellCheck={false}
          value={query}
          placeholder="Name or ID, e.g. MA Crossover"
          aria-label="Find strategy"
          aria-autocomplete="list"
          aria-expanded={open && suggestions.length > 0}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setError(null);
            setOpen(true);
          }}
          onKeyDown={(event) => {
            if (!open || !suggestions.length) return;
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActiveIndex((index) => (index + 1) % suggestions.length);
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setActiveIndex((index) => (index - 1 + suggestions.length) % suggestions.length);
            }
            if (event.key === "Escape") {
              setOpen(false);
            }
          }}
        />
        <button className="strategy-search-btn" type="submit" disabled={!query.trim()}>
          Go to
        </button>
      </form>
      {error && <span className="strategy-search-hint is-error">{error}</span>}
      {!error && !open && (
        <span className="strategy-search-hint">Enter a name or ID and press Enter</span>
      )}
      {open && suggestions.length > 0 && (
        <ul className="strategy-search-suggestions" role="listbox">
          {suggestions.map((strategy, index) => (
            <li key={strategy.strategy_id} role="option" aria-selected={index === activeIndex}>
              <button
                type="button"
                className={`strategy-search-suggestion${index === activeIndex ? " is-active" : ""}`}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  setQuery(strategy.title ?? strategy.strategy_id);
                  navigateTo(strategy.strategy_id);
                }}
              >
                <span className="suggestion-title">{strategy.title ?? strategy.strategy_id}</span>
                <span className="suggestion-id">{strategy.strategy_id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function rankByStrategyId(ranking?: DashboardRanking): Map<string, RankingEntry> {
  const map = new Map<string, RankingEntry>();
  for (const entry of ranking?.entries ?? []) {
    map.set(entry.strategy_id, entry);
  }
  return map;
}

function isRankingReady(strategies: StrategyResult[], ranking?: DashboardRanking) {
  const completed = strategies.filter((s) => s.status === "completed");
  if (completed.length === 0) return false;
  const rankedIds = new Set((ranking?.entries ?? []).map((entry) => entry.strategy_id));
  return completed.every((strategy) => rankedIds.has(strategy.strategy_id));
}

function sortStrategiesByRank(
  strategies: StrategyResult[],
  ranking?: DashboardRanking
): StrategyResult[] {
  const ranks = rankByStrategyId(ranking);
  return [...strategies].sort((a, b) => {
    const rankA = ranks.get(a.strategy_id)?.rank;
    const rankB = ranks.get(b.strategy_id)?.rank;
    if (rankA == null && rankB == null) return 0;
    if (rankA == null) return 1;
    if (rankB == null) return -1;
    return rankA - rankB;
  });
}

function RankBadge({ entry }: { entry?: RankingEntry }) {
  if (!entry) return null;

  const movedUp = (entry.rank_delta ?? 0) > 0;
  const movedDown = (entry.rank_delta ?? 0) < 0;
  const delta = Math.abs(entry.rank_delta ?? 0);

  return (
    <div className="rank-badge" aria-label={`Rank ${entry.rank}`}>
      <span className="rank-number">#{entry.rank}</span>
      {movedUp && (
        <span className="rank-move rank-up" title={`Up ${delta} place${delta === 1 ? "" : "s"}`}>
          ↑{delta > 1 ? delta : ""}
        </span>
      )}
      {movedDown && (
        <span className="rank-move rank-down" title={`Down ${delta} place${delta === 1 ? "" : "s"}`}>
          ↓{delta > 1 ? delta : ""}
        </span>
      )}
    </div>
  );
}

function StrategyLoading() {
  const [step, setStep] = useState(0);
  const stages = [
    "Syncing candle history",
    "Simulating order flow",
    "Computing risk metrics",
    "Rendering chart series",
  ];

  useEffect(() => {
    const timer = setInterval(() => setStep((s) => (s + 1) % stages.length), 1400);
    return () => clearInterval(timer);
  }, [stages.length]);

  return (
    <div className="strategy-loading" aria-live="polite">
      <div className="loading-visual">
        <div className="orbit">
          <span />
          <span />
          <span />
        </div>
        <div className="loading-wave" />
      </div>
      <p className="loading-caption">{stages[step]}</p>
      <div className="skeleton-metrics">
        {Array.from({ length: 6 }).map((_, i) => (
          <div className="skeleton-block" key={i} style={{ animationDelay: `${i * 0.08}s` }} />
        ))}
      </div>
      <div className="skeleton-chart" />
    </div>
  );
}

function formatParamLabel(name: string) {
  return name.replace(/_/g, " ");
}

function numericStrategyParams(params: Record<string, number | boolean>) {
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(params)) {
    if (key === "enabled") continue;
    if (typeof value === "number") out[key] = value;
  }
  return out;
}

function ParamSummary({ params }: { params: Record<string, number | boolean> }) {
  const numeric = numericStrategyParams(params);
  return (
    <div className="params-summary" aria-label="Strategy parameters">
      {Object.entries(numeric).map(([name, value]) => (
        <div className="param-chip" key={name}>
          <span className="param-chip-label">{formatParamLabel(name)}</span>
          <span className="param-chip-value">{value}</span>
        </div>
      ))}
    </div>
  );
}

function OptimizationPanel({
  summary,
  initialCapital,
}: {
  summary: OptimizationSummary;
  initialCapital: number;
}) {
  const scopeLabel =
    summary.mode === "grid" || summary.exhaustive
      ? `Full grid search: ${summary.iterations_run} valid combinations evaluated (best by ${summary.target_metric})`
      : `Random sample: ${summary.iterations_run} of ${summary.grid_size} combinations (seed ${summary.seed})`;

  return (
    <div className="optimization-panel">
      <div className="optimization-header">
        <span className="optimization-title">Parameter search</span>
        <span className="optimization-scope">{scopeLabel}</span>
      </div>
      {summary.top_iterations.length > 0 && (
        <div className="optimization-table-wrap">
          <table className="optimization-table">
            <thead>
              <tr>
                <th>#</th>
                <th>P&amp;L</th>
                <th>Return %</th>
                <th>Sharpe</th>
                <th>Params</th>
              </tr>
            </thead>
            <tbody>
              {summary.top_iterations.map((row, index) => (
                <tr key={index} className={index === 0 ? "is-best" : undefined}>
                  <td>{index + 1}</td>
                  <td>{formatMoney(row.total_pnl)}</td>
                  <td>{formatReturnPct(row.total_pnl, initialCapital)}</td>
                  <td>{formatNumber(row.sharpe_ratio)}</td>
                  <td>
                    {Object.entries(row.params)
                      .filter(([key]) => key !== "order_size")
                      .map(([key, value]) => `${formatParamLabel(key)}=${value}`)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function clampViewRange(start: number, end: number, maxIndex: number, minWindow: number) {
  const size = Math.max(minWindow, Math.min(maxIndex + 1, end - start + 1));
  let nextStart = Math.max(0, Math.min(start, maxIndex));
  let nextEnd = Math.min(maxIndex, nextStart + size - 1);
  if (nextEnd - nextStart + 1 < minWindow) {
    nextStart = Math.max(0, nextEnd - minWindow + 1);
  }
  return { start: nextStart, end: nextEnd };
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: ChartRow }[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const alphaSign = row.alpha >= 0 ? "+" : "";

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{formatChartDate(row.date)}</div>
      <div className="tooltip-strategy">Strategy: {formatIndex(row.strategy_index)}</div>
      <div className="tooltip-muted">{formatMoney(row.equity)}</div>
      <div className="tooltip-benchmark">Buy &amp; hold: {formatIndex(row.benchmark_index)}</div>
      <div className="tooltip-muted">Close: {formatNumber(row.close)} ₽</div>
      <div className="tooltip-alpha">
        Alpha: {alphaSign}
        {row.alpha.toFixed(1)} pp
      </div>
      {row.action && (
        <div className={row.action === "BUY" ? "tooltip-buy" : "tooltip-sell"}>{row.action}</div>
      )}
    </div>
  );
}

function TradeMarker(props: { cx?: number; cy?: number; payload?: ChartRow }) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null || !payload?.action) return null;
  const fill = payload.action === "BUY" ? CHART.buy : CHART.sell;
  return <circle cx={cx} cy={cy} r={3.5} fill={fill} stroke="#ffffff" strokeWidth={1.5} />;
}

function PerformanceChartInner({ points, trades = [] }: { points: ChartPoint[]; trades: TradePoint[] }) {
  const data = useMemo(() => buildChartRows(points, trades), [points, trades]);
  const chartBoxRef = useRef<HTMLDivElement>(null);

  const dataSignature = useMemo(
    () => `${data.length}:${data[0]?.date ?? ""}:${data[data.length - 1]?.date ?? ""}`,
    [data]
  );

  const [viewRange, setViewRange] = useState<{ start: number; end: number } | null>(null);

  useEffect(() => {
    setViewRange(null);
  }, [dataSignature]);

  const maxIndex = Math.max(data.length - 1, 0);
  const minWindow = Math.min(12, Math.max(data.length, 1));
  const start = viewRange?.start ?? 0;
  const end = viewRange?.end ?? maxIndex;
  const isZoomed = start > 0 || end < maxIndex;

  useEffect(() => {
    const element = chartBoxRef.current;
    if (!element || !data.length) return;

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      setViewRange((current) => {
        const currentStart = current?.start ?? 0;
        const currentEnd = current?.end ?? maxIndex;
        const windowSize = currentEnd - currentStart + 1;
        const zoomIn = event.deltaY < 0;
        const factor = zoomIn ? 0.82 : 1.22;
        let nextSize = Math.round(windowSize * factor);
        nextSize = Math.max(minWindow, Math.min(data.length, nextSize));

        if (nextSize >= data.length) {
          return null;
        }

        const center = (currentStart + currentEnd) / 2;
        let nextStart = Math.round(center - (nextSize - 1) / 2);
        let nextEnd = nextStart + nextSize - 1;

        if (nextEnd > maxIndex) {
          nextEnd = maxIndex;
          nextStart = Math.max(0, nextEnd - nextSize + 1);
        }
        if (nextStart < 0) {
          nextStart = 0;
          nextEnd = Math.min(maxIndex, nextSize - 1);
        }

        return clampViewRange(nextStart, nextEnd, maxIndex, minWindow);
      });
    };

    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [data.length, maxIndex, minWindow]);

  const xDomain = useMemo(() => {
    if (!data.length || !isZoomed) return ["dataMin", "dataMax"] as const;
    return [data[start].date, data[end].date] as [string, string];
  }, [data, end, isZoomed, start]);

  const summary = useMemo(() => {
    if (!data.length) return null;
    const last = data[data.length - 1];
    return {
      strategy: last.strategy_index,
      benchmark: last.benchmark_index,
      alpha: last.strategy_index - last.benchmark_index,
    };
  }, [data]);

  if (!data.length) return null;

  return (
    <div className="chart-panel-inner">
      {summary && (
        <div className="chart-summary">
          <span className="summary-strategy">{formatIndex(summary.strategy)}</span>
          <span className="summary-vs">vs</span>
          <span className="summary-benchmark">{formatIndex(summary.benchmark)}</span>
          <span className={summary.alpha >= 0 ? "summary-alpha-pos" : "summary-alpha-neg"}>
            α {summary.alpha >= 0 ? "+" : ""}
            {summary.alpha.toFixed(1)} pp
          </span>
        </div>
      )}

      <div className={`chart-box${isZoomed ? " is-zoomed" : ""}`} ref={chartBoxRef}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={CHART.grid} />
            <XAxis
              dataKey="date"
              type="category"
              domain={xDomain}
              allowDataOverflow
              tickFormatter={formatAxisDate}
              minTickGap={32}
              tick={{ fill: CHART.axis, fontSize: 11 }}
              axisLine={{ stroke: CHART.grid }}
              tickLine={{ stroke: CHART.grid }}
            />
            <YAxis
              domain={["auto", "auto"]}
              tickFormatter={(v) => Number(v).toFixed(0)}
              width={44}
              tick={{ fill: CHART.axis, fontSize: 11 }}
              axisLine={{ stroke: CHART.grid }}
              tickLine={{ stroke: CHART.grid }}
            />
            <ReferenceLine y={BASELINE} stroke="#aebcd0" strokeDasharray="4 4" />
            <Tooltip content={<ChartTooltip />} />
            <Line
              type="monotone"
              dataKey="benchmark_index"
              stroke={CHART.benchmark}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="strategy_flat"
              stroke={CHART.strategy}
              strokeWidth={2.5}
              strokeDasharray="6 4"
              strokeOpacity={0.9}
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="strategy_solid"
              stroke={CHART.strategy}
              strokeWidth={2.5}
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="trade_marker"
              stroke="none"
              dot={TradeMarker}
              activeDot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-legend">
        <span className="legend-strategy">Strategy (in market)</span>
        <span className="legend-strategy-flat">out of market</span>
        <span className="legend-benchmark">Buy &amp; hold</span>
        <span className="legend-baseline">Baseline 100</span>
        <span className="buy-dot">BUY</span>
        <span className="sell-dot">SELL</span>
      </div>
    </div>
  );
}

const PerformanceChart = memo(PerformanceChartInner);

function bestParams(strategy: StrategyResult): Record<string, number> {
  const best = strategy.optimization?.top_iterations?.[0]?.params;
  if (best) return best;
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(strategy.params)) {
    if (typeof value === "number") out[key] = value;
  }
  return out;
}

function formatConsistency(metrics: StrategyResult["metrics"]) {
  if (metrics.consistency_pct == null) return "—";
  const periods =
    metrics.positive_months != null && metrics.total_months != null
      ? ` (${metrics.positive_months}/${metrics.total_months} periods)`
      : "";
  return `${formatPercent(metrics.consistency_pct)}${periods}`;
}

const VERDICT_LABELS: Record<string, string> = {
  profit_factor_below_1: "Profit factor below 1.0",
  below_deposit_baseline: "Does not beat deposit baseline",
  underperforms_buy_hold: "Underperforms buy & hold",
  low_consistency: "Low period consistency",
};

function applyLiveStrategy(
  strategies: StrategyResult[],
  strategyId: string,
  strategy: StrategyResult
) {
  return strategies.map((entry) =>
    entry.strategy_id === strategyId
      ? { ...strategy, live_active: true }
      : { ...entry, live_active: false }
  );
}

function StrategyHealthPanel({
  strategy,
}: {
  strategy: StrategyResult;
}) {
  const verdict = strategy.verdict;
  if (!verdict) return null;

  const gradeClass =
    verdict.grade === "PASS"
      ? "is-pass"
      : verdict.grade === "CAUTION"
        ? "is-caution"
        : "is-fail";

  return (
    <div className={`strategy-health ${gradeClass}`} aria-label="Strategy health">
      <div className="strategy-health-head">
        <span className="strategy-health-kicker">Strategy health</span>
        <span className={`strategy-health-grade ${gradeClass}`}>{verdict.grade}</span>
      </div>
      <div className="strategy-health-metrics">
        <span>Return {formatSignedReturnPct(verdict.total_return_pct)}</span>
        <span>PF {formatNumber(verdict.profit_factor)}</span>
        <span>Consistency {formatPercent(verdict.consistency_pct)}</span>
        <span>vs B&amp;H {formatSignedReturnPct(verdict.vs_buy_hold_pct)}</span>
        <span>vs Deposit {formatSignedReturnPct(verdict.vs_deposit_pct)}</span>
      </div>
      {verdict.flags.length > 0 && (
        <ul className="strategy-health-flags">
          {verdict.flags.map((flag) => (
            <li key={flag}>{VERDICT_LABELS[flag] ?? flag}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function isStrategyEnabled(params: Record<string, number | boolean | string | undefined>) {
  const enabled = params.enabled;
  if (enabled === false || enabled === 0) return false;
  if (typeof enabled === "string") {
    const normalized = enabled.trim().toLowerCase();
    if (normalized === "0" || normalized === "false" || normalized === "no" || normalized === "off") {
      return false;
    }
  }
  return true;
}

const StrategyCardInner = ({
  strategy,
  rankEntry,
  highlighted,
  busy,
  showLoading,
  onDelete,
  onToggleLive,
  liveBusy,
  liveStrategyId,
  onToggleEnabled,
  togglingEnabled,
}: {
  strategy: StrategyResult;
  rankEntry?: RankingEntry;
  highlighted?: boolean;
  busy?: boolean;
  showLoading?: boolean;
  onDelete?: (strategyId: string) => Promise<void>;
  onToggleLive?: (strategyId: string, params: Record<string, number>, isLive: boolean) => Promise<void>;
  liveBusy?: boolean;
  liveStrategyId?: string | null;
  onToggleEnabled?: (strategyId: string, enabled: boolean) => Promise<void>;
  togglingEnabled?: boolean;
}) => {
  const isRunning = strategy.status === "running";
  const isError = strategy.status === "error";
  const cardLoading = Boolean(showLoading);
  const runEnabled = isStrategyEnabled(strategy.params);
  const isLive = liveStrategyId === strategy.strategy_id || Boolean(strategy.live_active);
  const otherLive = liveStrategyId != null && liveStrategyId !== strategy.strategy_id;
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!onDelete || cardLoading || isRunning || deleting) return;
    const label = strategy.title ?? strategy.strategy_id;
    if (!window.confirm(`Delete strategy "${label}"? This removes config/strategies/${strategy.strategy_id}.yaml and all dashboard results.`)) {
      return;
    }
    setDeleting(true);
    try {
      await onDelete(strategy.strategy_id);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <article
      id={strategyCardId(strategy.strategy_id)}
      className={`strategy-card ${cardLoading || isRunning ? "is-running" : ""}${isLive ? " is-live" : ""}${highlighted ? " is-highlighted" : ""}${runEnabled ? "" : " is-run-disabled"}`}
    >
      <header className="strategy-header">
        <div className="strategy-header-main">
          {onToggleEnabled && (
            <label className="strategy-run-toggle" title="Include in next Run backtest">
              <input
                type="checkbox"
                checked={runEnabled}
                disabled={busy || togglingEnabled || cardLoading}
                onChange={(event) => void onToggleEnabled(strategy.strategy_id, event.target.checked)}
              />
              <span>Run</span>
            </label>
          )}
          {!cardLoading && <RankBadge entry={rankEntry} />}
          <div>
            <p className="strategy-kicker">{strategy.title ?? strategy.strategy_id}</p>
            <h2 className="strategy-title">{strategy.strategy_id}</h2>
          </div>
        </div>
        <div className="strategy-status">
          {onToggleLive && !cardLoading && strategy.status === "completed" && (
            <button
              className="strategy-action-btn strategy-action-btn-live"
              type="button"
              disabled={busy || liveBusy || otherLive}
              onClick={() => void onToggleLive(strategy.strategy_id, bestParams(strategy), isLive)}
            >
              {liveBusy && isLive
                ? "Starting…"
                : isLive
                  ? "Stop Live"
                  : "Go Live"}
            </button>
          )}
          {isLive && !cardLoading && (
            <span className="status-pill status-live">Live</span>
          )}
          {onDelete && (
            <button
              className="strategy-delete-btn"
              type="button"
              disabled={busy || cardLoading || isRunning || deleting}
              onClick={handleDelete}
            >
              {deleting ? "Deleting…" : "Delete"}
            </button>
          )}
          {cardLoading && <span className="status-pill status-running">Running</span>}
          {!cardLoading && isRunning && <span className="status-pill status-running">Running</span>}
          {!cardLoading && !isRunning && !isError && strategy.status === "completed" && (
            <span className="status-pill status-done">Ready</span>
          )}
          {isError && <span className="status-pill status-error">Error</span>}
          {!cardLoading && !isRunning && strategy.final_portfolio.equity != null && (
            <span className="strategy-final">
              {formatSignedReturnPct(
                strategy.initial_capital > 0
                  ? (strategy.final_portfolio.equity - strategy.initial_capital) /
                      strategy.initial_capital
                  : null
              )}
            </span>
          )}
        </div>
      </header>

      <ParamSummary params={strategy.params} />

      {!cardLoading && strategy.optimization && (
        <OptimizationPanel summary={strategy.optimization} initialCapital={strategy.initial_capital} />
      )}

      {!cardLoading && strategy.status === "completed" && <StrategyHealthPanel strategy={strategy} />}

      {isError && strategy.error && (
        <div className="strategy-error">{formatStrategyError(strategy.error)}</div>
      )}

      {cardLoading ? (
        <StrategyLoading />
      ) : (
        <>
          <div className="metrics-grid">
            <div className="metric-card">
              <span className="metric-title">Return</span>
              <span className="metric-value">
                {formatSignedReturnPct(
                  strategy.metrics.total_return_pct ?? (
                    strategy.metrics.total_pnl != null && strategy.initial_capital > 0
                      ? strategy.metrics.total_pnl / strategy.initial_capital
                      : null
                  )
                )}
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Sharpe</span>
              <span className="metric-value">{formatNumber(strategy.metrics.sharpe_ratio)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Drawdown</span>
              <span className="metric-value">{formatPercent(strategy.metrics.max_drawdown)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Win rate</span>
              <span className="metric-value">{formatPercent(strategy.metrics.win_rate)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Profit factor</span>
              <span className="metric-value">{formatNumber(strategy.metrics.profit_factor)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Calmar</span>
              <span className="metric-value">{formatNumber(strategy.metrics.calmar_ratio)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Consistency</span>
              <span className="metric-value">{formatConsistency(strategy.metrics)}</span>
              <span className="metric-hint">Positive months</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">vs Buy&amp;Hold</span>
              <span className="metric-value">
                {formatSignedReturnPct(strategy.metrics.vs_buy_hold_pct)}
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-title">vs Deposit</span>
              <span className="metric-value">
                {formatSignedReturnPct(
                  strategy.metrics.deposit_baseline_pnl != null && strategy.initial_capital > 0
                    ? strategy.metrics.deposit_baseline_pnl / strategy.initial_capital
                    : null
                )}
              </span>
              <span className="metric-hint">13% baseline</span>
            </div>
          </div>

          <PerformanceChart
            points={strategy.chart_points ?? []}
            trades={strategy.trade_log ?? []}
          />
        </>
      )}
    </article>
  );
};

const StrategyCard = memo(StrategyCardInner);

function formatStrategyError(message: string | null | undefined) {
  if (!message) return "Unknown error";
  if (message.includes("invest-public-api.tbank.ru") || message.includes("Connection failed")) {
    return "T-Bank API unreachable (network timeout). Check internet/VPN/firewall and try again.";
  }
  return message;
}

export default function Page() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [runRequested, setRunRequested] = useState(false);
  const runStartedRef = useRef(false);
  const runStartedAtRef = useRef(0);
  const runRequestedRef = useRef(false);
  runRequestedRef.current = runRequested;
  const rankingRefreshRequested = useRef(false);
  const highlightTimerRef = useRef<number | null>(null);
  const [highlightedStrategyId, setHighlightedStrategyId] = useState<string | null>(null);
  const [liveStrategyId, setLiveStrategyId] = useState<string | null>(null);
  const liveStrategyIdRef = useRef<string | null>(null);
  liveStrategyIdRef.current = liveStrategyId;
  const [liveBusyId, setLiveBusyId] = useState<string | null>(null);
  const [togglingEnabledId, setTogglingEnabledId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const stopLiveRefresh = useCallback(async () => {
    const activeId = liveStrategyIdRef.current;
    if (!activeId) return;

    liveStrategyIdRef.current = null;
    setLiveStrategyId(null);
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        strategies: prev.strategies.map((strategy) => ({
          ...strategy,
          live_active: false,
        })),
      };
    });

    try {
      await fetch("/api/live-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "stop", strategy_id: activeId }),
      });
    } catch {
      // best effort; UI and prepare-bootstrap also clear server state
    }
  }, []);

  const applyLiveTick = useCallback((payload: {
    active?: boolean;
    strategy?: StrategyResult;
    strategy_id?: string;
    stopped_reason?: string;
  }) => {
    if (!payload.active || payload.stopped_reason) {
      setLiveStrategyId(null);
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          strategies: prev.strategies.map((strategy) => ({
            ...strategy,
            live_active: false,
          })),
        };
      });
      return;
    }
    const strategyId = payload.strategy_id ?? payload.strategy?.strategy_id;
    if (!strategyId || !payload.strategy) return;
    setLiveStrategyId(strategyId);
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        strategies: applyLiveStrategy(prev.strategies, strategyId, payload.strategy as StrategyResult),
      };
    });
  }, []);

  const toggleStrategyEnabled = useCallback(async (strategyId: string, enabled: boolean) => {
    setActionError(null);
    setTogglingEnabledId(strategyId);
    try {
      const res = await fetch(`/api/strategies/${encodeURIComponent(strategyId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      const json = (await res.json()) as { ok?: boolean; message?: string; params?: Record<string, unknown> };
      if (!res.ok || !json.ok) {
        throw new Error(json.message ?? "Failed to update strategy");
      }
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          strategies: prev.strategies.map((strategy) =>
            strategy.strategy_id === strategyId
              ? {
                  ...strategy,
                  params: {
                    ...strategy.params,
                    ...(json.params as Record<string, number | boolean> | undefined),
                    enabled,
                  },
                }
              : strategy
          ),
        };
      });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to update strategy");
    } finally {
      setTogglingEnabledId(null);
    }
  }, []);

  const toggleLiveStrategy = useCallback(
    async (strategyId: string, params: Record<string, number>, isLive: boolean) => {
      setActionError(null);
      if (isLive) {
        setLiveBusyId(strategyId);
        try {
          await stopLiveRefresh();
        } finally {
          setLiveBusyId(null);
        }
        return;
      }

      setLiveBusyId(strategyId);
      try {
        const res = await fetch("/api/live-run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "start", strategy_id: strategyId, params }),
        });
        const json = (await res.json()) as {
          ok?: boolean;
          strategy?: StrategyResult;
          strategy_id?: string;
          message?: string;
        };
        if (!res.ok || !json.ok) {
          throw new Error(json.message ?? "Failed to start live refresh");
        }
        applyLiveTick({
          active: true,
          strategy: json.strategy,
          strategy_id: json.strategy_id ?? strategyId,
        });
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "Failed to start live refresh");
      } finally {
        setLiveBusyId(null);
      }
    },
    [applyLiveTick, stopLiveRefresh]
  );

  const loadDashboard = useCallback(async () => {
    const res = await fetch("/api/dashboard", { cache: "no-store" });
    const json = (await res.json()) as DashboardData;
    setData((prev) => {
      const merged: DashboardData = {
        ...json,
        strategies: json.strategies.map((strategy) => {
          const previous = prev?.strategies.find((s) => s.strategy_id === strategy.strategy_id);
          const params = {
            ...strategy.params,
            enabled:
              strategy.params.enabled ??
              previous?.params.enabled ??
              true,
          };
          return {
            ...strategy,
            params,
          };
        }),
      };

      if (!runRequestedRef.current || !prev) {
        return merged;
      }

      const serverRunActive = merged.strategies.some((strategy) => strategy.status === "running");
      if (!serverRunActive) {
        return {
          ...merged,
          instrument: prev.instrument,
          timeframe: prev.timeframe,
          data_source: prev.data_source,
          ranking: prev.ranking,
          strategies: merged.strategies.map((strategy) => {
            const optimistic = prev.strategies.find((s) => s.strategy_id === strategy.strategy_id);
            if (optimistic?.status === "running") {
              return {
                ...strategy,
                status: "running" as const,
                error: null,
                chart_points: [],
                trade_log: [],
                params: optimistic.params,
              };
            }
            return strategy;
          }),
        };
      }

      const updatedAt = merged.last_updated ? new Date(merged.last_updated).getTime() : 0;
      if (updatedAt < runStartedAtRef.current) {
        return prev;
      }

      return merged;
    });
  }, []);

  const beginRun = useCallback((settings: RuntimeSettings) => {
    runStartedAtRef.current = Date.now();
    runStartedRef.current = true;
    setRunRequested(true);

    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        instrument: settings.instrument,
        timeframe: settings.timeframe,
        data_source: sourceDisplayName(settings.data_source),
        ranking: { computed_at: null, entries: [] },
        strategies: prev.strategies.map((strategy) => ({
          ...strategy,
          status: isStrategyEnabled(strategy.params) ? ("running" as const) : strategy.status,
          error: isStrategyEnabled(strategy.params) ? null : strategy.error,
          chart_points: isStrategyEnabled(strategy.params) ? [] : strategy.chart_points,
          trade_log: isStrategyEnabled(strategy.params) ? [] : strategy.trade_log,
        })),
      };
    });
  }, []);

  const runBacktest = useCallback(async (settings: RuntimeSettings) => {
    try {
      const saveRes = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...settings, optimization_seed: 42 }),
      });
      const saveBody = (await saveRes.json().catch(() => null)) as { message?: string } | null;
      if (!saveRes.ok) {
        throw new Error(saveBody?.message ?? "Failed to save settings");
      }

      const res = await fetch("/api/bootstrap", { method: "POST" });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { message?: string } | null;
        throw new Error(body?.message ?? "Backtest run failed");
      }
    } catch (err) {
      setRunRequested(false);
      runStartedRef.current = false;
      await loadDashboard();
      throw err;
    }
  }, [loadDashboard]);

  const deleteStrategy = useCallback(
    async (strategyId: string) => {
      const res = await fetch(`/api/strategies/${encodeURIComponent(strategyId)}`, {
        method: "DELETE",
      });
      const body = (await res.json().catch(() => null)) as { message?: string } | null;
      if (!res.ok) {
        throw new Error(body?.message ?? "Failed to delete strategy");
      }
      if (highlightedStrategyId === strategyId) {
        setHighlightedStrategyId(null);
      }
      await loadDashboard();
    },
    [highlightedStrategyId, loadDashboard]
  );

  const stopBacktest = useCallback(async () => {
    runStartedRef.current = false;
    setRunRequested(false);

    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        strategies: prev.strategies.map((strategy) =>
          strategy.status === "running"
            ? { ...strategy, status: "idle" as const, error: "Stopped by user" }
            : strategy
        ),
      };
    });

    const res = await fetch("/api/stop", { method: "POST" });
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { message?: string } | null;
      throw new Error(body?.message ?? "Stop request failed");
    }
    await loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (!runRequested) return;
    void loadDashboard();
  }, [loadDashboard, runRequested]);

  useEffect(() => {
    if (!data || rankingRefreshRequested.current) return;
    if (!needsRankingRefresh(data.strategies, data.ranking)) return;
    rankingRefreshRequested.current = true;
    fetch("/api/refresh-ranking", { method: "POST" });
  }, [data]);

  const anyRunning = useMemo(
    () => data?.strategies.some((strategy) => strategy.status === "running") ?? false,
    [data]
  );

  const bootstrapActive = useMemo(() => {
    if (!data?.strategies?.length) return runRequested;
    if (runRequested || anyRunning) return true;
    if (!runStartedRef.current) return false;
    return !isRankingReady(data.strategies, data.ranking);
  }, [anyRunning, data, runRequested]);

  const anyBusy = bootstrapActive;

  useEffect(() => {
    let cancelled = false;
    void fetch("/api/live-run", { cache: "no-store" })
      .then((res) => res.json())
      .then((json: { active?: boolean; strategy_id?: string }) => {
        if (cancelled) return;
        if (json.active && json.strategy_id) {
          setLiveStrategyId(json.strategy_id);
        }
      })
      .catch(() => {
        // ignore status errors on load
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!liveStrategyId || anyBusy) return;

    let cancelled = false;
    const timeframe = data?.timeframe ?? "1h";
    const pollMs = livePollMs(timeframe);

    const tick = async () => {
      if (cancelled || !liveStrategyIdRef.current) return;
      try {
        const res = await fetch("/api/live-run/tick", { method: "POST", cache: "no-store" });
        const json = (await res.json()) as {
          ok?: boolean;
          active?: boolean;
          cached?: boolean;
          strategy?: StrategyResult;
          stopped_reason?: string;
          message?: string;
        };
        if (!res.ok || !json.ok) {
          throw new Error(json.message ?? "Live refresh failed");
        }
        applyLiveTick(json);
      } catch (err) {
        if (!cancelled) {
          setActionError(err instanceof Error ? err.message : "Live refresh failed");
        }
      }
    };

    const timer = window.setInterval(() => void tick(), pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [liveStrategyId, anyBusy, data?.timeframe, applyLiveTick]);

  useEffect(() => {
    if (!runRequested || !data) return;
    if (anyRunning) return;

    const updatedAt = data.last_updated ? new Date(data.last_updated).getTime() : 0;
    if (updatedAt < runStartedAtRef.current) return;
    if (!isRankingReady(data.strategies, data.ranking)) return;

    setRunRequested(false);
    runStartedRef.current = false;
  }, [anyRunning, data, runRequested]);

  useEffect(() => {
    if (!runRequested) return;
    const timer = window.setTimeout(() => {
      setRunRequested(false);
      runStartedRef.current = false;
      void loadDashboard();
    }, 180_000);
    return () => window.clearTimeout(timer);
  }, [loadDashboard, runRequested]);

  useEffect(() => {
    if (!anyBusy) return;
    const ms = POLL_RUNNING_MS;
    const timer = setInterval(loadDashboard, ms);
    return () => clearInterval(timer);
  }, [loadDashboard, anyBusy]);

  const rankedStrategies = useMemo(() => {
    if (!data) return [];
    if (bootstrapActive) {
      return [...data.strategies].sort((a, b) => a.strategy_id.localeCompare(b.strategy_id));
    }
    return sortStrategiesByRank(data.strategies, data.ranking);
  }, [bootstrapActive, data]);

  const rankMap = useMemo(() => rankByStrategyId(data?.ranking), [data?.ranking]);

  const scrollToStrategy = useCallback((strategyId: string) => {
    const element = document.getElementById(strategyCardId(strategyId));
    if (!element) return;
    element.scrollIntoView({ behavior: "smooth", block: "start" });
    setHighlightedStrategyId(strategyId);
    if (highlightTimerRef.current != null) {
      window.clearTimeout(highlightTimerRef.current);
    }
    highlightTimerRef.current = window.setTimeout(() => {
      setHighlightedStrategyId((current) => (current === strategyId ? null : current));
      highlightTimerRef.current = null;
    }, 2400);
  }, []);

  useEffect(() => {
    return () => {
      if (highlightTimerRef.current != null) {
        window.clearTimeout(highlightTimerRef.current);
      }
    };
  }, []);

  return (
    <div className="page-bg">
      <main className="app-shell">
        <header className="hero">
          <div className="hero-top">
            <div className="hero-brand">
              <p className="eyebrow">Trading Analytics</p>
              <h1 className="hero-title">BackTestBench</h1>
            </div>
            <div className="hero-meta">
              <div className="meta-chip">Instrument: {data?.instrument ?? "SBER"}</div>
              <div className="meta-chip">TF: {data?.timeframe ?? "1h"}</div>
              <div className="meta-chip">Source: {data?.data_source ?? "T-Bank"}</div>
              {anyBusy && <div className="meta-chip meta-live">Updating</div>}
            </div>
          </div>
          <div className="hero-toolbar">
            <StrategySearch strategies={rankedStrategies} onNavigate={scrollToStrategy} />
          </div>
        </header>

        <BacktestControlPanel
          busy={anyBusy}
          onBeforeRun={stopLiveRefresh}
          onRunStart={beginRun}
          onRun={runBacktest}
          onStop={stopBacktest}
        />

        <AddStrategyPanel busy={anyBusy} onAdded={loadDashboard} />

        {actionError && (
          <div className="workflow-config-error" role="alert">
            {actionError}
          </div>
        )}

        <section className="strategy-list">
          {rankedStrategies.map((strategy) => (
            <StrategyCard
              key={strategy.strategy_id}
              strategy={strategy}
              rankEntry={rankMap.get(strategy.strategy_id)}
              highlighted={highlightedStrategyId === strategy.strategy_id}
              busy={anyBusy}
              showLoading={strategy.status === "running"}
              onDelete={deleteStrategy}
              onToggleLive={toggleLiveStrategy}
              liveBusy={liveBusyId === strategy.strategy_id}
              liveStrategyId={liveStrategyId}
              onToggleEnabled={toggleStrategyEnabled}
              togglingEnabled={togglingEnabledId === strategy.strategy_id}
            />
          ))}

          {!data?.strategies?.length && (
            <article className="strategy-card placeholder-card">
              <StrategyLoading />
            </article>
          )}
        </section>
      </main>
    </div>
  );
}
