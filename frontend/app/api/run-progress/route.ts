import { readFile } from "fs/promises";

import { backtestDataPaths } from "@/lib/backtest-paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  try {
    const { dataDir } = backtestDataPaths();
    const raw = await readFile(`${dataDir}/run-progress.json`, "utf8");
    const data = JSON.parse(raw) as Record<string, unknown>;
    return Response.json({ ok: true, active: true, ...data });
  } catch {
    return Response.json({ ok: true, active: false });
  }
}
