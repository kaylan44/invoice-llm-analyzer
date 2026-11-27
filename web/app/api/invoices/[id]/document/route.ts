import { ApiError, apiFetch } from "@/lib/api";

// Relay: the browser asks this app, this app asks the API with the token.
export async function GET(_request: Request, { params }: RouteContext<"/api/invoices/[id]/document">) {
  const { id } = await params;
  try {
    const upstream = await apiFetch(`/invoices/${encodeURIComponent(id)}/document`);
    return new Response(upstream.body, {
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/octet-stream",
        "Content-Disposition": "inline",
        "Cache-Control": "private, no-store",
      },
    });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    return new Response("Document indisponible", { status });
  }
}
