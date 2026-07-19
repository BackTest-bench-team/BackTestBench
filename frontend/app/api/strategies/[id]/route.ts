import { spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function PATCH(request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    const strategyId = id?.trim();
    if (!strategyId) {
      return Response.json({ ok: false, message: "Strategy id is required" }, { status: 400 });
    }

    const body = (await request.json()) as { enabled?: boolean };
    if (typeof body.enabled !== "boolean") {
      return Response.json({ ok: false, message: "enabled must be a boolean" }, { status: 400 });
    }

    const captured = await spawnPythonCapture([
      "main.py",
      "set-strategy-enabled",
      JSON.stringify({ strategy_id: strategyId, enabled: body.enabled }),
    ]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: captured.stderr || captured.stdout || "Update failed" },
        { status: 400 }
      );
    }

    const result = JSON.parse(captured.stdout) as {
      ok: boolean;
      strategy_id: string;
      enabled: boolean;
      params: Record<string, unknown>;
    };
    return Response.json({ ok: true, strategy_id: result.strategy_id, enabled: result.enabled, params: result.params });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Failed to update strategy",
      },
      { status: 500 }
    );
  }
}

export async function DELETE(_request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    const strategyId = id?.trim();
    if (!strategyId) {
      return Response.json({ ok: false, message: "Strategy id is required" }, { status: 400 });
    }

    const captured = await spawnPythonCapture(["main.py", "delete-strategy", strategyId]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: captured.stderr || captured.stdout || "Delete failed" },
        { status: 400 }
      );
    }

    const result = JSON.parse(captured.stdout) as { ok: boolean; deleted: string; file: string };
    return Response.json({ ok: true, deleted: result.deleted, file: result.file });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Failed to delete strategy",
      },
      { status: 500 }
    );
  }
}
