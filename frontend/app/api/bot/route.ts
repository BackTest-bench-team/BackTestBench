import { spawnPython, spawnPythonCapture } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const jobId = url.searchParams.get("job_id");
  const list = url.searchParams.get("list");
  try {
    if (list) {
      const limit = url.searchParams.get("limit") ?? "30";
      const captured = await spawnPythonCapture(["main.py", "bot-list", "--limit", limit]);
      if (captured.exitCode !== 0) {
        return Response.json(
          { ok: false, message: captured.stderr || "Failed to list bot jobs" },
          { status: 500 }
        );
      }
      return Response.json(JSON.parse(captured.stdout));
    }
    if (jobId) {
      const captured = await spawnPythonCapture(["main.py", "bot-get", jobId]);
      if (captured.exitCode !== 0) {
        return Response.json(
          { ok: false, message: captured.stderr || captured.stdout || "Job not found" },
          { status: 404 }
        );
      }
      return Response.json(JSON.parse(captured.stdout));
    }
    const captured = await spawnPythonCapture(["main.py", "bot-limits"]);
    if (captured.exitCode !== 0) {
      return Response.json({ ok: false, message: captured.stderr || "Failed" }, { status: 500 });
    }
    return Response.json(JSON.parse(captured.stdout));
  } catch (error) {
    return Response.json(
      { ok: false, message: error instanceof Error ? error.message : "Failed" },
      { status: 500 }
    );
  }
}

export async function DELETE(request: Request) {
  const jobId = new URL(request.url).searchParams.get("job_id");
  if (!jobId) {
    return Response.json({ ok: false, message: "job_id is required" }, { status: 400 });
  }
  try {
    await spawnPythonCapture(["main.py", "bot-stop", jobId]);
    const captured = await spawnPythonCapture(["main.py", "bot-delete", jobId]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: captured.stderr || captured.stdout || "Failed to delete bot job" },
        { status: 500 }
      );
    }
    return Response.json(JSON.parse(captured.stdout));
  } catch (error) {
    return Response.json(
      { ok: false, message: error instanceof Error ? error.message : "Failed to delete bot job" },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    if (body.action === "stop") {
      const jobId = String(body.job_id ?? "");
      if (!jobId) {
        return Response.json({ ok: false, message: "job_id is required" }, { status: 400 });
      }
      const captured = await spawnPythonCapture(["main.py", "bot-stop", jobId]);
      if (captured.exitCode !== 0) {
        return Response.json(
          { ok: false, message: captured.stderr || captured.stdout || "Failed to stop bot" },
          { status: 400 }
        );
      }
      return Response.json(JSON.parse(captured.stdout));
    }

    if (body.action === "resume") {
      const jobId = String(body.job_id ?? "");
      if (!jobId) {
        return Response.json({ ok: false, message: "job_id is required" }, { status: 400 });
      }
      spawnPython(["main.py", "bot-job", jobId]);
      return Response.json({ ok: true, job_id: jobId, resumed: true }, { status: 202 });
    }

    const captured = await spawnPythonCapture(["main.py", "bot-start", JSON.stringify(body)]);
    if (captured.exitCode !== 0) {
      return Response.json(
        { ok: false, message: captured.stderr || captured.stdout || "Failed to start bot" },
        { status: 400 }
      );
    }
    const payload = JSON.parse(captured.stdout) as { ok: boolean; job_id: string };
    spawnPython(["main.py", "bot-job", payload.job_id]);
    return Response.json(payload, { status: 202 });
  } catch (error) {
    return Response.json(
      { ok: false, message: error instanceof Error ? error.message : "Failed to start bot" },
      { status: 500 }
    );
  }
}
