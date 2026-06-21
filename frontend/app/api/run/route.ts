import { spawn } from "child_process";
import { readFileSync, existsSync, writeFileSync, mkdirSync } from "fs";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function findRepoRoot(startDir: string): string {
  let dir = startDir;

  while (true) {
    if (
      existsSync(path.join(dir, "main.py")) ||
      existsSync(path.join(dir, ".env"))
    ) {
      return dir;
    }

    const parent = path.dirname(dir);
    if (parent === dir) return startDir;
    dir = parent;
  }
}

function loadDotEnvFile(envPath: string): Record<string, string> {
  const result: Record<string, string> = {};

  if (!existsSync(envPath)) return result;

  const content = readFileSync(envPath, "utf8");

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();

    if (!line || line.startsWith("#")) continue;

    const idx = line.indexOf("=");

    if (idx === -1) continue;

    result[line.slice(0, idx).trim()] = line
      .slice(idx + 1)
      .trim()
      .replace(/^["']|["']$/g, "");
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
          message: "TINKOFF_TOKEN missing",
        },
        { status: 500 }
      );
    }

    //
    // Сбрасываем dashboard перед запуском
    //
    const dataDir = path.join(repoRoot, "data");
    mkdirSync(dataDir, { recursive: true });

    writeFileSync(
      path.join(dataDir, "runtime-dashboard.json"),
      JSON.stringify(
        {
          status: "running",
          current_stage: "Starting",
          message: "Launching pipeline...",
          pipeline: [
            { name: "Broker Adapter", status: "running" },
            { name: "Strategy Module", status: "pending" },
            { name: "Simulation Engine", status: "pending" },
            { name: "Analytics Module", status: "pending" }
          ],
          metrics: {
            total_pnl: null,
            sharpe_ratio: null,
            max_drawdown: null,
            win_rate: null,
            deposit_baseline_pnl: null
          },
          equity_points: [],
          trade_count: 0,
          last_updated: new Date().toISOString()
        },
        null,
        2
      )
    );

    const pythonCmd =
      process.env.PYTHON_BIN ??
      (process.platform === "win32" ? "py" : "python3");

    const child = spawn(pythonCmd, ["-m", "main"], {
      cwd: repoRoot,
      detached: true,
      windowsHide: true,
      stdio: "ignore",
      env: {
        ...process.env,
        TINKOFF_TOKEN: token,
      },
    });

    child.unref();

    return Response.json(
      {
        ok: true,
        started: true,
      },
      { status: 202 }
    );
  } catch (err) {
    return Response.json(
      {
        ok: false,
        message: err instanceof Error ? err.message : "unknown error",
      },
      { status: 500 }
    );
  }
}