import { readEnvFile } from "@/lib/env-file";
import { findRepoRoot } from "@/lib/spawn-python";

const TOKEN_KEYS = ["TINKOFF_TOKEN", "TWELVEDATA_TOKEN"] as const;

export type TokenInfo = {
  configured: boolean;
  masked: string | null;
};

function maskToken(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.length <= 8) return "*".repeat(trimmed.length);
  return `${trimmed.slice(0, 4)}…${trimmed.slice(-4)}`;
}

export function readTokenStatus(): { ok: true; tokens: Record<string, TokenInfo> } {
  const repoRoot = findRepoRoot(process.cwd());
  const stored = readEnvFile(repoRoot);
  const tokens: Record<string, TokenInfo> = {};

  for (const key of TOKEN_KEYS) {
    const value = process.env[key] || stored[key];
    const configured = Boolean(value && String(value).trim());
    tokens[key] = {
      configured,
      masked: configured ? maskToken(String(value)) : null,
    };
  }

  return { ok: true, tokens };
}
