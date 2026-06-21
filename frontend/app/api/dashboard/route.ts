import { readFile } from "fs/promises";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

const fallback = {
  run_id: "mock-run",
  strategy_id: "ma_crossover",
  instrument: "SBER",
  data_source: "mock",
  status: "idle",
  current_stage: "Idle",
  pipeline: [
    { name: "Broker Adapter", status: "pending" },
    { name: "Data Loader", status: "pending" },
    { name: "Strategy Module", status: "pending" },
    { name: "Simulation Engine", status: "pending" },
    { name: "Analytics Module", status: "skipped" },
  ],
  metrics: {
    total_pnl: null,
    sharpe_ratio: null,
    max_drawdown: null,
    win_rate: null,
    deposit_baseline_pnl: null,
  },
  equity_points: [
    { date: "start", value: 100000 },
    { date: "2025-01-01", value: 100000 },
  ],
  trade_count: 0,
  final_portfolio: {
    cash: 100000,
    position_size: 0,
    equity: 100000,
  },
  last_updated: null,
  message: "",
};

async function readJson(filePath: string) {
  const raw = await readFile(filePath, "utf8");
  return JSON.parse(raw);
}

export async function GET() {
  try {
    const runtimePath = path.join(process.cwd(), "data", "runtime-dashboard.json");
    const mockPath = path.join(process.cwd(), "data", "mock-dashboard.json");

    let data: any;
    try {
      data = await readJson(runtimePath);
    } catch {
      data = await readJson(mockPath);
    }

    return Response.json(
      {
        ...fallback,
        ...data,
        metrics: {
          ...fallback.metrics,
          ...(data.metrics ?? {}),
        },
        final_portfolio: {
          ...fallback.final_portfolio,
          ...(data.final_portfolio ?? {}),
        },
      },
      { status: 200 }
    );
  } catch {
    return Response.json(fallback, { status: 200 });
  }
}