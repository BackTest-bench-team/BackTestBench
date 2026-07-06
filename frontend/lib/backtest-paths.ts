import path from "path";
import { findRepoRoot } from "@/lib/spawn-python";

export function backtestDataPaths(cwd = process.cwd()) {
  const repoRoot = findRepoRoot(cwd);
  const dataDir = path.join(repoRoot, "data");
  return {
    repoRoot,
    dataDir,
    stopFile: path.join(dataDir, "backtest.stop"),
    pidFile: path.join(dataDir, "backtest.pid"),
    dashboardFile: path.join(dataDir, "runtime-dashboard.json"),
  };
}

export type DashboardPayload = {
  strategies?: Array<{ status?: string; error?: string | null; [key: string]: unknown }>;
  last_updated?: string | null;
  [key: string]: unknown;
};

export function markDashboardStopped(data: DashboardPayload): DashboardPayload {
  const next = { ...data, strategies: [...(data.strategies ?? [])] };
  next.strategies = next.strategies.map((entry) => {
    if (entry.status !== "running") return entry;
    return { ...entry, status: "idle", error: "Stopped by user" };
  });
  next.last_updated = new Date().toISOString();
  return next;
}
