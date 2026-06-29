"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Brush,
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
};

type StrategyResult = {
  strategy_id: string;
  strategy_version: string;
  title?: string;
  status: "idle" | "running" | "completed" | "error";
  params: Record<string, number>;
  parameter_specs?: ParamSpec[];
  initial_capital: number;
  metrics: {
    total_pnl: number | null;
    sharpe_ratio: number | null;
    max_drawdown: number | null;
    win_rate: number | null;
    deposit_baseline_pnl: number | null;
    deposit_baseline_final?: number | null;
  };
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

const POLL_IDLE_MS = 4000;
const POLL_RUNNING_MS = 350;
const BASELINE = 100;

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

function paramsEqual(a: Record<string, number>, b: Record<string, number>) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function runSettled(strategy: StrategyResult, expectedParams: Record<string, number>) {
  if (strategy.status === "error") return true;
  if (strategy.status !== "completed") return false;
  if (!paramsEqual(strategy.params, expectedParams)) return false;
  return (strategy.chart_points?.length ?? 0) > 0;
}

function buildChartRows(points: ChartPoint[], trades: TradePoint[]): ChartRow[] {
  const actionByDate = new Map(trades.map((t) => [t.timestamp, t.action]));
  return points.map((point) => ({
    ...point,
    action: actionByDate.get(point.date) ?? null,
    alpha: point.strategy_index - point.benchmark_index,
  }));
}

function needsBootstrap(strategies: StrategyResult[]) {
  if (!strategies.length) return true;
  return strategies.every(
    (s) => s.status === "idle" && (s.chart_points?.length ?? 0) === 0
  );
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
          type="search"
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

function ParamEditor({
  specs,
  params,
  disabled,
  onCommit,
}: {
  specs: ParamSpec[];
  params: Record<string, number>;
  disabled: boolean;
  onCommit: (next: Record<string, number>) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)]))
  );
  const editingRef = useRef(false);

  useEffect(() => {
    if (editingRef.current) return;
    setDraft(Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)])));
  }, [params]);

  const ordered: ParamSpec[] = specs.length
    ? specs
    : Object.keys(params).map((name) => ({
        name,
        type: "float",
        default: params[name],
      }));

  function parseDraft(): Record<string, number> | null {
    const next: Record<string, number> = {};
    for (const spec of ordered) {
      const raw = draft[spec.name]?.trim();
      if (!raw) return null;
      const parsed = spec.type === "int" ? parseInt(raw, 10) : parseFloat(raw);
      if (Number.isNaN(parsed)) return null;
      if (spec.minimum != null && parsed < spec.minimum) return null;
      if (spec.maximum != null && parsed > spec.maximum) return null;
      next[spec.name] = parsed;
    }
    return next;
  }

  function commitIfChanged() {
    editingRef.current = false;
    const next = parseDraft();
    if (!next) return;
    if (paramsEqual(next, params)) return;
    onCommit(next);
  }

  return (
    <div className="params-form">
      {ordered.map((spec) => (
        <label className="param-field" key={spec.name}>
          <span className="param-label">{formatParamLabel(spec.name)}</span>
          <input
            className="param-input"
            type="number"
            step={spec.type === "int" ? 1 : 0.1}
            min={spec.minimum}
            max={spec.maximum}
            disabled={disabled}
            value={draft[spec.name] ?? String(spec.default)}
            onFocus={() => {
              editingRef.current = true;
            }}
            onChange={(e) => {
              editingRef.current = true;
              setDraft((prev) => ({ ...prev, [spec.name]: e.target.value }));
            }}
            onBlur={commitIfChanged}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
          />
          {spec.description && <span className="param-hint">{spec.description}</span>}
        </label>
      ))}
    </div>
  );
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

function PerformanceChart({ points, trades = [] }: { points: ChartPoint[]; trades: TradePoint[] }) {
  const data = useMemo(() => buildChartRows(points, trades), [points, trades]);

  const dataSignature = useMemo(
    () => `${data.length}:${data[0]?.date ?? ""}:${data[data.length - 1]?.date ?? ""}`,
    [data]
  );

  const lastSignature = useRef("");
  const [brushIndices, setBrushIndices] = useState({ startIndex: 0, endIndex: 0 });

  useEffect(() => {
    if (!data.length) return;
    const lastIndex = data.length - 1;
    if (lastSignature.current !== dataSignature) {
      lastSignature.current = dataSignature;
      setBrushIndices({ startIndex: 0, endIndex: lastIndex });
    }
  }, [dataSignature, data.length]);

  const handleBrushChange = (range: { startIndex?: number; endIndex?: number }) => {
    if (range.startIndex == null || range.endIndex == null) return;
    setBrushIndices({ startIndex: range.startIndex, endIndex: range.endIndex });
  };

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

      <div className="chart-box">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={CHART.grid} />
            <XAxis
              dataKey="date"
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
              dataKey="strategy_index"
              stroke={CHART.strategy}
              strokeWidth={2.5}
              dot={TradeMarker}
              activeDot={{ r: 4, fill: CHART.strategy }}
              isAnimationActive={false}
            />
            <Brush
              dataKey="date"
              height={22}
              stroke={CHART.brush}
              fill="rgba(71, 94, 230, 0.1)"
              tickFormatter={formatAxisDate}
              travellerWidth={10}
              startIndex={brushIndices.startIndex}
              endIndex={brushIndices.endIndex}
              onChange={handleBrushChange}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-legend">
        <span className="legend-strategy">Strategy index</span>
        <span className="legend-benchmark">Buy &amp; hold</span>
        <span className="legend-baseline">Baseline 100</span>
        <span className="buy-dot">BUY</span>
        <span className="sell-dot">SELL</span>
        <span className="legend-brush">Drag brush to zoom</span>
      </div>
    </div>
  );
}

function StrategyCard({
  strategy,
  pendingParams,
  rankEntry,
  highlighted,
  onParamsCommit,
}: {
  strategy: StrategyResult;
  pendingParams?: Record<string, number>;
  rankEntry?: RankingEntry;
  highlighted?: boolean;
  onParamsCommit: (strategyId: string, params: Record<string, number>) => void;
}) {
  const displayParams = pendingParams ?? strategy.params;
  const isBusy =
    strategy.status === "running" ||
    (pendingParams != null && !runSettled(strategy, pendingParams));
  const isError = strategy.status === "error";

  return (
    <article
      id={strategyCardId(strategy.strategy_id)}
      className={`strategy-card ${isBusy ? "is-running" : ""}${highlighted ? " is-highlighted" : ""}`}
    >
      <header className="strategy-header">
        <div className="strategy-header-main">
          <RankBadge entry={rankEntry} />
          <div>
            <p className="strategy-kicker">{strategy.title ?? strategy.strategy_id}</p>
            <h2 className="strategy-title">{strategy.strategy_id}</h2>
          </div>
        </div>
        <div className="strategy-status">
          {isBusy && <span className="status-pill status-running">Running</span>}
          {!isBusy && !isError && strategy.status === "completed" && (
            <span className="status-pill status-done">Ready</span>
          )}
          {isError && <span className="status-pill status-error">Error</span>}
          {!isBusy && strategy.final_portfolio.equity != null && (
            <span className="strategy-final">{formatMoney(strategy.final_portfolio.equity)}</span>
          )}
        </div>
      </header>

      <ParamEditor
        specs={strategy.parameter_specs ?? []}
        params={displayParams}
        disabled={isBusy}
        onCommit={(next) => onParamsCommit(strategy.strategy_id, next)}
      />

      {isError && strategy.error && <div className="strategy-error">{strategy.error}</div>}

      {isBusy ? (
        <StrategyLoading />
      ) : (
        <>
          <div className="metrics-grid">
            <div className="metric-card">
              <span className="metric-title">P&amp;L</span>
              <span className="metric-value">{formatMoney(strategy.metrics.total_pnl)}</span>
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
              <span className="metric-title">Deposit</span>
              <span className="metric-value">
                {formatMoney(
                  strategy.metrics.deposit_baseline_final ??
                    strategy.initial_capital + (strategy.metrics.deposit_baseline_pnl ?? 0)
                )}
              </span>
              <span className="metric-hint">Bank baseline</span>
            </div>
            <div className="metric-card">
              <span className="metric-title">Capital</span>
              <span className="metric-value">{formatMoney(strategy.initial_capital)}</span>
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
}

export default function Page() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [pendingRuns, setPendingRuns] = useState<Record<string, Record<string, number>>>({});
  const bootstrapRequested = useRef(false);
  const rankingRefreshRequested = useRef(false);
  const highlightTimerRef = useRef<number | null>(null);
  const [highlightedStrategyId, setHighlightedStrategyId] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    const res = await fetch("/api/dashboard", { cache: "no-store" });
    const json = (await res.json()) as DashboardData;
    setData(json);

    setPendingRuns((prev) => {
      const next = { ...prev };
      for (const [strategyId, expectedParams] of Object.entries(prev)) {
        const strategy = json.strategies.find((s) => s.strategy_id === strategyId);
        if (strategy && runSettled(strategy, expectedParams)) {
          delete next[strategyId];
        }
      }
      return next;
    });
  }, []);

  const runStrategy = useCallback(async (strategyId: string, params: Record<string, number>) => {
    setPendingRuns((prev) => ({ ...prev, [strategyId]: params }));

    const res = await fetch("/api/run-strategy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy_id: strategyId, params }),
    });

    if (!res.ok) {
      setPendingRuns((prev) => {
        const next = { ...prev };
        delete next[strategyId];
        return next;
      });
      const body = (await res.json().catch(() => null)) as { message?: string } | null;
      console.error(body?.message ?? "Strategy run failed");
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (!data || bootstrapRequested.current) return;
    if (!needsBootstrap(data.strategies)) return;
    bootstrapRequested.current = true;
    fetch("/api/bootstrap", { method: "POST" });
  }, [data]);

  useEffect(() => {
    if (!data || rankingRefreshRequested.current) return;
    if (needsBootstrap(data.strategies)) return;
    if (!needsRankingRefresh(data.strategies, data.ranking)) return;
    rankingRefreshRequested.current = true;
    fetch("/api/refresh-ranking", { method: "POST" });
  }, [data]);

  const anyBusy = useMemo(() => {
    if (!data) return false;
    return data.strategies.some(
      (s) =>
        s.status === "running" ||
        (pendingRuns[s.strategy_id] != null && !runSettled(s, pendingRuns[s.strategy_id]))
    );
  }, [data, pendingRuns]);

  useEffect(() => {
    const ms = anyBusy ? POLL_RUNNING_MS : POLL_IDLE_MS;
    const timer = setInterval(loadDashboard, ms);
    return () => clearInterval(timer);
  }, [loadDashboard, anyBusy]);

  const rankedStrategies = useMemo(
    () => (data ? sortStrategiesByRank(data.strategies, data.ranking) : []),
    [data]
  );

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

        <section className="strategy-list">
          {rankedStrategies.map((strategy) => (
            <StrategyCard
              key={strategy.strategy_id}
              strategy={strategy}
              rankEntry={rankMap.get(strategy.strategy_id)}
              highlighted={highlightedStrategyId === strategy.strategy_id}
              pendingParams={pendingRuns[strategy.strategy_id]}
              onParamsCommit={runStrategy}
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
