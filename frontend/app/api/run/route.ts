import { spawn } from "child_process";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const rootDir = path.resolve(process.cwd(), "..");
    const pythonCmd =
      process.env.PYTHON_BIN ??
      (process.platform === "win32" ? "py" : "python3");

    const child = spawn(pythonCmd, ["main.py"], {
      cwd: rootDir,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
    });

    child.unref();

    return Response.json(
      { ok: true, started: true, message: "Pipeline started" },
      { status: 202 }
    );
  } catch {
    return Response.json(
      { ok: false, started: false, message: "Failed to start pipeline" },
      { status: 500 }
    );
  }
}