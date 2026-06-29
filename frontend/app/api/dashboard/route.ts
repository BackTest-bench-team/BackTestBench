import { readFile } from "fs/promises";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

const emptyDashboard = {
  instrument: "SBER",
  timeframe: "1h",
  data_source: "T-Bank",
  initial_capital: 100_000,
  strategies: [] as unknown[],
  ranking: { computed_at: null as string | null, entries: [] as unknown[] },
  last_updated: null as string | null,
};

export async function GET() {
  try {
    const file = path.resolve(process.cwd(), "..", "data", "runtime-dashboard.json");
    const raw = await readFile(file, "utf8");
    const data = JSON.parse(raw);
    return Response.json({ ...emptyDashboard, ...data });
  } catch {
    return Response.json(emptyDashboard);
  }
}
