import type { NextRequest } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";

export async function GET(request: NextRequest) {
  const format = request.nextUrl.searchParams.get("format") === "csv" ? "csv" : "json";
  try {
    const upstream = await apiFetch(`/export?format=${format}`);
    return new Response(upstream.body, {
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
        "Content-Disposition": `attachment; filename="factures-validees.${format}"`,
        "Cache-Control": "private, no-store",
      },
    });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    return new Response("Export indisponible", { status });
  }
}
