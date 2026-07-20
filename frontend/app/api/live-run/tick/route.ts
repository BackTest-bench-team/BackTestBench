import { spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const captured = await spawnPythonCapture(["main.py", "live-run-tick"]);
    if (captured.exitCode !== 0) {
      let message = captured.stderr || captured.stdout || "Live tick failed";
      try {
        const parsed = JSON.parse(captured.stdout) as { message?: string };
        if (parsed.message) message = parsed.message;
      } catch {
        // keep raw message
      }
      return Response.json({ ok: false, message }, { status: 500 });
    }

    const payload = JSON.parse(captured.stdout) as {
      ok?: boolean;
      active?: boolean;
      strategy?: Record<string, unknown>;
      stopped_reason?: string;
      message?: string;
    };
    return Response.json(payload);
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Live tick failed",
      },
      { status: 500 }
    );
  }
}
