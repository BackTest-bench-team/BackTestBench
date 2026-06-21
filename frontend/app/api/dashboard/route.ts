import { readFile } from "fs/promises";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

type PipelineStep = {
  name: string;
  status: "pending" | "running" | "done" | "skipped" | "error";
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
  equity_points: { date: string; value: number }[];
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

const emptyDashboard: DashboardData = {
  run_id: "local",
  strategy_id: "ma_crossover",
  strategy_version: "1",
  instrument: "SBER",
  timeframe: "1h",
  data_source: "T-Bank",
  status: "idle",
  current_stage: "Idle",
  pipeline: [
    { name: "Broker Adapter", status: "pending" },
    { name: "Strategy Module", status: "pending" },
    { name: "Simulation Engine", status: "pending" },
    { name: "Analytics Module", status: "pending" },
  ],
  metrics: {
    total_pnl: null,
    sharpe_ratio: null,
    max_drawdown: null,
    win_rate: null,
    deposit_baseline_pnl: null,
  },
  equity_points: [],
  trade_count: 0,
  final_portfolio: {
    cash: null,
    position_size: null,
    equity: null,
  },
  message: "No completed run yet",
  error: null,
  last_updated: null,
};

function mergeDashboard(runtimeData: Partial<DashboardData> | null): DashboardData {
  if (!runtimeData) return emptyDashboard;

  return {
    ...emptyDashboard,
    ...runtimeData,
    metrics: {
      ...emptyDashboard.metrics,
      ...(runtimeData.metrics ?? {}),
    },
    final_portfolio: {
      ...emptyDashboard.final_portfolio,
      ...(runtimeData.final_portfolio ?? {}),
    },
    pipeline: Array.isArray(runtimeData.pipeline) && runtimeData.pipeline.length > 0
      ? runtimeData.pipeline
      : emptyDashboard.pipeline,
    equity_points: Array.isArray(runtimeData.equity_points)
      ? runtimeData.equity_points
      : emptyDashboard.equity_points,
  };
}

async function readJson(filePath: string) {
  const raw = await readFile(filePath, "utf8");
  return JSON.parse(raw);
}

export async function GET() {
  try {
    const runtimePath = path.resolve(process.cwd(), "..", "data", "runtime-dashboard.json");
    const runtimeData = await readJson(runtimePath).catch(() => null);

    return Response.json(mergeDashboard(runtimeData), { status: 200 });
  } catch {
    return Response.json(emptyDashboard, { status: 200 });
  }
}