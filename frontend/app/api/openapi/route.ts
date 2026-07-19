import { readFile } from "fs/promises";
import path from "path";

import { findRepoRoot } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  try {
    const specPath = path.join(findRepoRoot(process.cwd()), "docs", "openapi.yaml");
    const yaml = await readFile(specPath, "utf8");
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
