import "server-only";

// The only module that talks to the FastAPI backend. API_URL and API_TOKEN stay on the
// server: the browser only ever calls this app (pages, server actions, route handlers).

export type InvoiceStatus = "pending" | "to_review" | "validated";

export type InvoiceSummary = {
  id: string;
  status: InvoiceStatus;
  supplier_name: string | null;
  invoice_number: string | null;
  issue_date: string | null;
  total_incl_vat: string | null;
  currency: string | null;
  review_reasons: string[];
  created_at: string;
};

export type InvoiceLine = {
  position: number;
  description: string | null;
  quantity: string | null;
  unit_price: string | null;
  vat_rate: string | null;
  amount: string | null;
  category_code: string | null;
  category_score: number | null;
};

export type Invoice = InvoiceSummary & {
  supplier_vat_number: string | null;
  supplier_siret: string | null;
  supplier_match: string | null;
  due_date: string | null;
  total_excl_vat: string | null;
  total_vat: string | null;
  language: string | null;
  updated_at: string;
  lines: InvoiceLine[];
  extraction: { model: string; prompt_version: string; error: string | null } | null;
  job: { id: string; status: "queued" | "running" | "done" | "failed"; error: string | null } | null;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function config(): { url: string; token: string } {
  const url = process.env.API_URL;
  const token = process.env.API_TOKEN;
  if (!url || !token) throw new Error("API_URL and API_TOKEN must be set (see web/.env.example)");
  return { url: url.replace(/\/$/, ""), token };
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { url, token } = config();
  const response = await fetch(`${url}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  return response;
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await apiFetch(path, init)).json() as Promise<T>;
}

export const api = {
  list: (status?: InvoiceStatus) =>
    json<InvoiceSummary[]>(`/invoices${status ? `?status=${status}` : ""}`),
  get: (id: string) => json<Invoice>(`/invoices/${encodeURIComponent(id)}`),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return json<{ invoice_id: string; job_id: string }>("/invoices", { method: "POST", body });
  },
  correct: (id: string, changes: Record<string, string | null>) =>
    json<Invoice>(`/invoices/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),
  validate: (id: string, acknowledgeReasons: boolean) =>
    json<Invoice>(`/invoices/${encodeURIComponent(id)}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledge_reasons: acknowledgeReasons }),
    }),
};
