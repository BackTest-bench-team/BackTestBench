import { spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type LiveRunResponse = {
  ok?: boolean;
  active?: boolean;
  strategy_id?: string;
  strategy?: Record<string, unknown>;
  live?: Record<string, unknown>;
  stopped_reason?: string;
  message?: string;
};

function readMessage(stdout: string, stderr: string, fallback: string) {
  try {
    const parsed = JSON.parse(stdout) as { message?: string };
    if (parsed.message) return parsed.message;
  } catch {
    // keep fallback
  }
  return stderr || stdout || fallback;
}

export async function GET() {
  try {
    const captured = await spawnPythonCapture(["main.py", "live-run-status"]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: readMessage(captured.stdout, captured.stderr, "Live status failed") },
        { status: 500 }
      );
    }
    const payload = JSON.parse(captured.stdout) as LiveRunResponse;
    return Response.json(payload);
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Live status failed",
      },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      action?: "start" | "stop";
      strategy_id?: string;
      params?: Record<string, number>;
    };
    const action = body.action;
    if (action !== "start" && action !== "stop") {
      return Response.json({ ok: false, message: "action must be start or stop" }, { status: 400 });
    }

    const strategyId = body.strategy_id?.trim();
    if (!strategyId) {
      return Response.json({ ok: false, message: "strategy_id is required" }, { status: 400 });
    }

    const command = action === "start" ? "live-run-start" : "live-run-stop";
    const payload =
      action === "start"
        ? JSON.stringify({ strategy_id: strategyId, params: body.params ?? {} })
        : JSON.stringify({ strategy_id: strategyId });

    const captured = await spawnPythonCapture(["main.py", command, payload]);
    if (captured.exitCode !== 0) {
      return Response.json(
        {
          ok: false,
          message: readMessage(captured.stdout, captured.stderr, "Live run request failed"),
        },
        { status: 400 }
      );
    }

    const result = JSON.parse(captured.stdout) as LiveRunResponse;
    if (!result.ok) {
      return Response.json(
        { ok: false, message: result.message ?? "Live run request failed" },
        { status: 400 }
      );
    }
    return Response.json(result);
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Live run request failed",
      },
      { status: 500 }
    );
  }
}
