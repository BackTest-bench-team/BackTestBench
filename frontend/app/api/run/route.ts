import { randomUUID } from "crypto";
import { spawn } from "child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function findRepoRoot(startDir: string): string {
  let dir = startDir;

  while (true) {
    const mainPath = path.join(dir, "main.py");
    const envPath = path.join(dir, ".env");

    if (existsSync(mainPath) || existsSync(envPath)) {
      return dir;
    }

    const parent = path.dirname(dir);
    if (parent === dir) {
      return startDir;
    }
    dir = parent;
  }
}

function loadDotEnvFile(envPath: string): Record<string, string> {
  const result: Record<string, string> = {};

  if (!existsSync(envPath)) {
    return result;
  }

  const content = readFileSync(envPath, "utf8");
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const idx = line.indexOf("=");
    if (idx === -1) continue;

    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
    result[key] = value;
  }

  return result;
}

export async function POST() {
  try {
    const repoRoot = findRepoRoot(process.cwd());
    const rootEnv = loadDotEnvFile(path.join(repoRoot, ".env"));

    const token = rootEnv.TINKOFF_TOKEN || process.env.TINKOFF_TOKEN;
    if (!token) {
      return Response.json(
        {
          ok: false,
          started: false,
          message: "TINKOFF_TOKEN is missing in repository root .env",
        },
        { status: 500 }
      );
    }

    const runId = randomUUID();

    const dataDir = path.join(repoRoot, "data");
    mkdirSync(dataDir, { recursive: true });

    writeFileSync(
      path.join(dataDir, "runtime-dashboard.json"),
      JSON.stringify(
        {
          run_id: runId,
          strategy_id: "ma_crossover",
          strategy_version: "1",
          instrument: "SBER",
          timeframe: "1h",
          data_source: "T-Bank",
          status: "running",
          current_stage: "Starting",
          pipeline: [
            { name: "Broker Adapter", status: "running" },
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
          message: "Launching pipeline...",
          error: null,
          last_updated: new Date().toISOString(),
        },
        null,
        2
      )
    );

    const pythonCmd =
      process.env.PYTHON_BIN ??
      (process.platform === "win32" ? "py" : "python3");

    const child = spawn(pythonCmd, ["main.py"], {
      cwd: repoRoot,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env: {
        ...process.env,
        RUN_ID: runId,
        PYTHONPATH: repoRoot,
        TINKOFF_TOKEN: token,
      },
    });

    child.unref();

    return Response.json(
      {
        ok: true,
        started: true,
        run_id: runId,
        message: "Pipeline started",
      },
      { status: 202 }
    );
  } catch (error) {
    return Response.json(
      {
        ok: false,
        started: false,
        message: `Failed to start pipeline: ${
          error instanceof Error ? error.message : "unknown error"
        }`,
      },
      { status: 500 }
    );
  }
}