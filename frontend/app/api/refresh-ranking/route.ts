import { spawnPython } from "@/lib/spawn-python";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  try {
    spawnPython(["main.py", "refresh-ranking"]);
    return Response.json({ ok: true, started: true }, { status: 202 });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        message: error instanceof Error ? error.message : "Ranking refresh failed",
      },
      { status: 500 }
    );
  }
}
