import { spawn } from "child_process";
import { existsSync, readFileSync } from "fs";
import path from "path";

export function findRepoRoot(startDir: string): string {
  let dir = startDir;
  while (true) {
    if (existsSync(path.join(dir, "main.py")) || existsSync(path.join(dir, ".env"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) return startDir;
    dir = parent;
  }
}

function loadDotEnv(envPath: string): Record<string, string> {
  if (!existsSync(envPath)) return {};
  const result: Record<string, string> = {};
  for (const rawLine of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
    result[key] = value;
  }
  return result;
}

export function spawnPython(args: string[]): void {
  const repoRoot = findRepoRoot(process.cwd());
  const pythonCmd = process.env.PYTHON_BIN ?? (process.platform === "win32" ? "py" : "python3");
  const rootEnv = loadDotEnv(path.join(repoRoot, ".env"));

  const child = spawn(pythonCmd, args, {
    cwd: repoRoot,
    detached: true,
    stdio: "ignore",
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONPATH: repoRoot,
      TINKOFF_TOKEN: rootEnv.TINKOFF_TOKEN ?? process.env.TINKOFF_TOKEN,
    },
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
  const rootEnv = loadDotEnv(path.join(repoRoot, ".env"));

  return new Promise((resolve, reject) => {
    const child = spawn(pythonCmd, args, {
      cwd: repoRoot,
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONPATH: repoRoot,
        PYTHONIOENCODING: "utf-8",
        TINKOFF_TOKEN: rootEnv.TINKOFF_TOKEN ?? process.env.TINKOFF_TOKEN,
      },
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
