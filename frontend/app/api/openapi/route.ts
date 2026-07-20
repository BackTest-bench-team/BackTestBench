import { readFile } from "fs/promises";
import path from "path";

import { findRepoRoot } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

async function readSpec(filePath: string): Promise<string | null> {
  try {
    return await readFile(filePath, "utf8");
  } catch {
    return null;
  }
}

async function loadOpenApiYaml(): Promise<string> {
  const candidates = [
    path.join(process.cwd(), "public", "openapi.yaml"),
    process.env.REPO_ROOT
      ? path.join(path.resolve(process.env.REPO_ROOT), "docs", "openapi.yaml")
      : null,
  ];

  try {
    candidates.push(path.join(findRepoRoot(process.cwd()), "docs", "openapi.yaml"));
  } catch {
    // Standalone runtime may not have main.py on the search path.
  }

  for (const candidate of candidates) {
    if (!candidate) continue;
    const yaml = await readSpec(candidate);
    if (yaml) return yaml;
  }

  throw new Error("OpenAPI spec not found");
}

export async function GET() {
  try {
    const yaml = await loadOpenApiYaml();
    return new Response(yaml, {
      headers: {
        "Content-Type": "application/yaml; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "OpenAPI spec not found",
      },
      { status: 500 }
    );
  }
}
