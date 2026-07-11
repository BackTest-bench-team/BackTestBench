import { existsSync, readFileSync } from "fs";
import path from "path";

export function parseEnvLines(text: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const rawLine of text.split(/\r?\n/)) {
    let line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("export ")) {
      line = line.slice("export ".length).trim();
    }
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key) values[key] = value;
  }
  return values;
}

export function readEnvFile(repoRoot: string): Record<string, string> {
  const envPath = path.join(repoRoot, ".env");
  if (!existsSync(envPath)) return {};
  return parseEnvLines(readFileSync(envPath, "utf8"));
}
