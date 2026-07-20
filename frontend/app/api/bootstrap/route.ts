import { spawnPython, spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const prepared = await spawnPythonCapture(["main.py", "prepare-bootstrap"]);
    if (prepared.exitCode !== 0) {
      let message = prepared.stderr || prepared.stdout || "Failed to prepare backtest";
      try {
        const parsed = JSON.parse(prepared.stdout) as { message?: string };
        if (parsed.message) message = parsed.message;
      } catch {
        // keep raw message
      }
      return Response.json({ ok: false, message }, { status: 500 });
    }

    spawnPython(["main.py", "bootstrap"]);
    return Response.json({ ok: true, started: true, live_stopped: true }, { status: 202 });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Bootstrap failed",
      },
      { status: 500 }
    );
  }
}
