import { appendFileSync, existsSync, mkdirSync } from "fs";
import { spawn } from "child_process";
import path from "path";

import { readEnvFile } from "@/lib/env-file";

export function findRepoRoot(startDir: string): string {
  if (process.env.REPO_ROOT) {
    const envRoot = path.resolve(process.env.REPO_ROOT);
    if (existsSync(path.join(envRoot, "main.py"))) {
      return envRoot;
    }
  }

  let dir = path.resolve(startDir);
  while (true) {
    if (existsSync(path.join(dir, "main.py"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      break;
    }
    dir = parent;
  }

  throw new Error(
    `Repository root not found (main.py missing). Started from ${startDir}. Set REPO_ROOT.`
  );
}

function pythonChildEnv(repoRoot: string): NodeJS.ProcessEnv {
  const fromFile = readEnvFile(repoRoot);
  return {
    ...process.env,
    ...fromFile,
    REPO_ROOT: repoRoot,
    PYTHONPATH: repoRoot,
    PYTHONIOENCODING: "utf-8",
  };
}

function logSpawnError(repoRoot: string, message: string) {
  try {
    const logPath = path.join(repoRoot, "data", "bootstrap-spawn.log");
    mkdirSync(path.dirname(logPath), { recursive: true });
    appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`);
  } catch {
    // ignore log failures
  }
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

  child.on("error", (err) => {
    logSpawnError(repoRoot, `spawn error (${args.join(" ")}): ${err.message}`);
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
    child.on("error", (err) => {
      logSpawnError(repoRoot, `capture error (${args.join(" ")}): ${err.message}`);
      reject(err);
    });
    child.on("close", (code) => {
      resolve({ stdout: stdout.trim(), stderr: stderr.trim(), exitCode: code ?? 1 });
    });
  });
}
