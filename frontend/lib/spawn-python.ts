import { spawn } from "child_process";
import { existsSync } from "fs";
import path from "path";

import { readEnvFile } from "@/lib/env-file";

export function findRepoRoot(startDir: string): string {
  let dir = startDir;
  while (true) {
    if (existsSync(path.join(dir, "main.py"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) return startDir;
    dir = parent;
  }
}

function pythonChildEnv(repoRoot: string): NodeJS.ProcessEnv {
  const fromFile = readEnvFile(repoRoot);
  return {
    ...process.env,
    ...fromFile,
    PYTHONPATH: repoRoot,
    PYTHONIOENCODING: "utf-8",
  };
}

export function spawnPython(args: string[]): void {
  const repoRoot = findRepoRoot(process.cwd());
  const pythonCmd = process.env.PYTHON_BIN ?? (process.platform === "win32" ? "py" : "python3");

  const child = spawn(pythonCmd, args, {
    cwd: repoRoot,
    detached: true,
    stdio: "ignore",
    windowsHide: true,
    env: pythonChildEnv(repoRoot),
  });

  child.unref();
}

export type SpawnCaptureResult = {
  stdout: string;
  stderr: string;
  exitCode: number;
};

function decodeChunk(chunk: Buffer | string): string {
  return typeof chunk === "string" ? chunk : chunk.toString("utf8");
}

export function spawnPythonCapture(args: string[]): Promise<SpawnCaptureResult> {
  const repoRoot = findRepoRoot(process.cwd());
  const pythonCmd = process.env.PYTHON_BIN ?? (process.platform === "win32" ? "py" : "python3");

  return new Promise((resolve, reject) => {
    const child = spawn(pythonCmd, args, {
      cwd: repoRoot,
      windowsHide: true,
      env: pythonChildEnv(repoRoot),
    });

    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (chunk: Buffer | string) => {
      stdout += decodeChunk(chunk);
    });
    child.stderr?.on("data", (chunk: Buffer | string) => {
      stderr += decodeChunk(chunk);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      resolve({ stdout: stdout.trim(), stderr: stderr.trim(), exitCode: code ?? 1 });
    });
  });
}
