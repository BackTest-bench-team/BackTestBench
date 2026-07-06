import { execFile } from "child_process";
import { mkdir, readFile, writeFile } from "fs/promises";
import path from "path";
import { promisify } from "util";
import {
  backtestDataPaths,
  markDashboardStopped,
  type DashboardPayload,
} from "@/lib/backtest-paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const execFileAsync = promisify(execFile);

async function writeStopRequest(stopFile: string) {
  await mkdir(path.dirname(stopFile), { recursive: true });
  await writeFile(stopFile, new Date().toISOString(), "utf8");
}

async function killBacktestPid(pidFile: string) {
  let pid: number;
  try {
    pid = parseInt((await readFile(pidFile, "utf8")).trim(), 10);
  } catch {
    return false;
  }
  if (!Number.isFinite(pid) || pid <= 0) return false;

  try {
    if (process.platform === "win32") {
      await execFileAsync("taskkill", ["/PID", String(pid), "/T", "/F"], {
        windowsHide: true,
      });
    } else {
      process.kill(pid, "SIGTERM");
    }
    return true;
  } catch {
    try {
      process.kill(pid, "SIGKILL");
      return true;
    } catch {
      return false;
    }
  }
}

async function patchDashboard(dashboardFile: string) {
  try {
    const raw = await readFile(dashboardFile, "utf8");
    const data = markDashboardStopped(JSON.parse(raw) as DashboardPayload);
    await writeFile(dashboardFile, JSON.stringify(data, null, 2), "utf8");
    return true;
  } catch {
    return false;
  }
}

export async function POST() {
  try {
    const { stopFile, pidFile, dashboardFile } = backtestDataPaths(process.cwd());

    await writeStopRequest(stopFile);
    const killed = await killBacktestPid(pidFile);
    const dashboardUpdated = await patchDashboard(dashboardFile);

    return Response.json(
      {
        ok: true,
        stopped: true,
        killed,
        dashboard_updated: dashboardUpdated,
      },
      { status: 202 }
    );
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Stop request failed",
      },
      { status: 500 }
    );
  }
}
