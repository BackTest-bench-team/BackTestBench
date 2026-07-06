import { spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ id: string }>;
};

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
