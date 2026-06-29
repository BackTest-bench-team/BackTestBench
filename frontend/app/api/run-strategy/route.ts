import { spawnPython } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RunBody = {
  strategy_id?: string;
  params?: Record<string, unknown>;
};

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as RunBody;
    const strategyId = body.strategy_id?.trim();
    const params = body.params;

    if (!strategyId || !params || typeof params !== "object") {
      return Response.json(
        { ok: false, message: "strategy_id and params are required" },
        { status: 400 }
      );
    }

    spawnPython(["main.py", "run", strategyId, JSON.stringify(params)]);

    return Response.json({ ok: true, started: true, strategy_id: strategyId }, { status: 202 });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Strategy run failed",
      },
      { status: 500 }
    );
  }
}
