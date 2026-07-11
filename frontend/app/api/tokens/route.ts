import { spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type TokenInfo = {
  configured: boolean;
  masked: string | null;
  valid?: boolean;
  message?: string;
};

type TokenStatusPayload = {
  ok: boolean;
  tokens: Record<string, TokenInfo>;
  message?: string;
};

export async function GET() {
  try {
    const captured = await spawnPythonCapture(["main.py", "token-status"]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: captured.stderr || "Failed to load token status" },
        { status: 500 }
      );
    }
    const payload = JSON.parse(captured.stdout) as TokenStatusPayload;
    return Response.json(payload);
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Failed to load token status",
      },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      tinkoff_token?: string;
      twelvedata_token?: string;
      verify?: boolean;
    };
    const captured = await spawnPythonCapture([
      "main.py",
      "save-tokens",
      JSON.stringify(body),
    ]);
    const payload = JSON.parse(captured.stdout || "{}") as TokenStatusPayload;
    if (captured.exitCode !== 0) {
      return Response.json(
        {
          ok: false,
          tokens: payload.tokens ?? {},
          message: payload.message || captured.stderr || "Token validation failed",
        },
        { status: 400 }
      );
    }
    return Response.json(payload);
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Failed to save tokens",
      },
      { status: 500 }
    );
  }
}
