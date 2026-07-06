import { spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RuntimeSettings = {
  instrument?: string;
  timeframe?: string;
  lookback_days?: number;
  initial_capital?: number;
  optimization_mode?: string;
  optimization_iterations?: number;
  optimization_seed?: number;
};

export async function GET() {
  try {
    const captured = await spawnPythonCapture(["main.py", "config-schema"]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: captured.stderr || "Failed to load config schema" },
        { status: 500 }
      );
    }
    const payload = JSON.parse(captured.stdout) as {
      settings: Record<string, unknown>;
      schema: Record<string, unknown>;
    };
    return Response.json({ ok: true, settings: payload.settings, schema: payload.schema });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Failed to load config",
      },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as RuntimeSettings;
    const captured = await spawnPythonCapture(["main.py", "save-settings", JSON.stringify(body)]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: captured.stderr || captured.stdout || "Validation failed" },
        { status: 400 }
      );
    }
    const settings = JSON.parse(captured.stdout) as Record<string, unknown>;
    return Response.json({ ok: true, settings });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Failed to save config",
      },
      { status: 500 }
    );
  }
}
