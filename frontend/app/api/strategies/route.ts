import { spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as { yaml?: string };
    if (!body.yaml?.trim()) {
      return Response.json({ ok: false, message: "YAML text is required" }, { status: 400 });
    }

    const payload = JSON.stringify({ yaml: body.yaml });
    const captured = await spawnPythonCapture(["main.py", "add-strategy", payload]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: captured.stderr || captured.stdout || "Validation failed" },
        { status: 400 }
      );
    }

    const result = JSON.parse(captured.stdout) as {
      ok: boolean;
      strategy: { id: string; title: string; file: string };
    };
    return Response.json({ ok: true, strategy: result.strategy });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Failed to save strategy",
      },
      { status: 500 }
    );
  }
}
