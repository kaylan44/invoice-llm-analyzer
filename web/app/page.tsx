import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { api, type InvoiceStatus } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/fields";

import { UploadForm } from "./upload-form";

const FILTERS: (InvoiceStatus | undefined)[] = [undefined, "to_review", "pending", "validated"];

export default function Home({ searchParams }: PageProps<"/">) {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-6">
      <UploadForm />
      {/* searchParams and the API call are request data: with cacheComponents they stream
          in behind a Suspense boundary, the rest of the page is the static shell. */}
      <Suspense fallback={<p className="mt-6 text-sm text-neutral-500">Chargement…</p>}>
        <InvoiceList searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function InvoiceList({ searchParams }: Pick<PageProps<"/">, "searchParams">) {
  const raw = (await searchParams).status;
  const status = FILTERS.find((f) => f === raw);
  const invoices = await api.list(status);
  return (
    <section className="mt-6">
      <div className="flex gap-2 text-sm">
        {FILTERS.map((f) => (
          <Link
            key={f ?? "all"}
            href={f ? `/?status=${f}` : "/"}
            className={`rounded px-3 py-1 ${f === status ? "bg-neutral-900 text-white" : "bg-white ring-1 ring-neutral-200"}`}
          >
            {f ? STATUS_LABELS[f] : "Toutes"}
          </Link>
        ))}
      </div>
      <table className="mt-4 w-full border-collapse bg-white text-sm ring-1 ring-neutral-200">
        <thead className="text-left text-neutral-500">
          <tr>
            <th className="p-2">Statut</th>
            <th className="p-2">Fournisseur</th>
            <th className="p-2">N°</th>
            <th className="p-2">Date</th>
            <th className="p-2 text-right">TTC</th>
            <th className="p-2">Motifs</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((inv) => (
            <tr key={inv.id} className="border-t border-neutral-100 hover:bg-neutral-50">
              <td className="p-2">
                <StatusBadge status={inv.status} />
              </td>
              <td className="p-2">
                <Link href={`/invoices/${inv.id}`} className="hover:underline">
                  {inv.supplier_name ?? "(en cours)"}
                </Link>
              </td>
              <td className="p-2">{inv.invoice_number ?? "—"}</td>
              <td className="p-2">{inv.issue_date ?? "—"}</td>
              <td className="p-2 text-right tabular-nums">
                {inv.total_incl_vat ? `${inv.total_incl_vat} ${inv.currency ?? ""}` : "—"}
              </td>
              <td className="p-2 text-neutral-600">
                {inv.review_reasons.map((r) => r.split(":")[0]).join(", ") || "—"}
              </td>
            </tr>
          ))}
          {invoices.length === 0 && (
            <tr>
              <td colSpan={6} className="p-4 text-center text-neutral-500">
                Aucune facture.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
