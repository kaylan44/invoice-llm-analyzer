import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { api, type InvoiceStatus, type InvoiceSummary } from "@/lib/api";
import { parseReason } from "@/lib/fields";
import { formatDate, formatMoney } from "@/lib/format";

import { UploadForm } from "./upload-form";

const FILTERS: { status: InvoiceStatus | undefined; label: string }[] = [
  { status: undefined, label: "Toutes" },
  { status: "to_review", label: "À vérifier" },
  { status: "pending", label: "En attente" },
  { status: "validated", label: "Validées" },
];

export default function Home({ searchParams }: PageProps<"/">) {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-5 sm:py-8">
      <h1 className="mb-4 text-xl font-semibold tracking-tight text-brand-950 sm:text-2xl">Factures</h1>
      <UploadForm />
      {/* searchParams and the API call are request data: with cacheComponents they stream
          in behind a Suspense boundary, the rest of the page is the static shell. */}
      <Suspense fallback={<ListSkeleton />}>
        <InvoiceList searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function InvoiceList({ searchParams }: Pick<PageProps<"/">, "searchParams">) {
  const raw = (await searchParams).status;
  const status = FILTERS.find((f) => f.status === raw)?.status;
  // One call for everything, filtered here: the counts on the filters need the full list.
  const all = await api.list();
  const invoices = status ? all.filter((inv) => inv.status === status) : all;
  const count = (s: InvoiceStatus | undefined) => (s ? all.filter((inv) => inv.status === s).length : all.length);

  return (
    <section className="mt-6">
      <nav aria-label="Filtrer par statut" className="grid grid-cols-4 gap-1.5 sm:flex sm:gap-2">
        {FILTERS.map((f) => {
          const active = f.status === status;
          return (
            <Link
              key={f.label}
              href={f.status ? `/?status=${f.status}` : "/"}
              aria-current={active ? "page" : undefined}
              className={`tap flex min-w-0 flex-col items-center justify-center rounded-xl px-1 py-2 text-xs leading-tight sm:flex-row sm:gap-2 sm:rounded-full sm:px-4 sm:py-0 sm:text-sm ${
                active ? "bg-brand-700 text-white shadow-sm" : "bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-brand-50"
              }`}
            >
              <span
                className={`text-lg font-semibold tabular-nums sm:order-2 sm:text-sm sm:font-normal ${
                  active ? "" : f.status === "to_review" ? "text-amber-700" : "text-slate-900 sm:text-slate-400"
                }`}
              >
                {count(f.status)}
              </span>
              <span className="w-full truncate text-center sm:order-1 sm:w-auto">{f.label}</span>
            </Link>
          );
        })}
      </nav>

      {invoices.length === 0 ? (
        <p className="mt-4 rounded-xl bg-white p-8 text-center text-sm text-slate-500 ring-1 ring-slate-200">
          Aucune facture dans ce filtre.
        </p>
      ) : (
        <>
          <ul className="mt-4 flex flex-col gap-2 md:hidden">
            {invoices.map((inv) => (
              <li key={inv.id}>
                <InvoiceCard invoice={inv} from={status} />
              </li>
            ))}
          </ul>
          <InvoiceTable invoices={invoices} from={status} />
        </>
      )}
    </section>
  );
}

function Reasons({ reasons }: { reasons: string[] }) {
  // Two reasons can share a check ("totals" twice): show each label once.
  const labels = [...new Set(reasons.map((r) => parseReason(r).label))];
  return (
    <span className="flex flex-wrap gap-1">
      {labels.map((label) => (
        <span key={label} className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-900">
          {label}
        </span>
      ))}
    </span>
  );
}

const supplier = (inv: InvoiceSummary) =>
  inv.supplier_name ?? <span className="font-normal text-slate-500">Extraction en cours…</span>;

function InvoiceCard({ invoice: inv, from }: { invoice: InvoiceSummary; from?: InvoiceStatus }) {
  return (
    <Link
      href={detailHref(inv.id, from)}
      className="block rounded-xl bg-white p-4 ring-1 ring-slate-200 active:bg-slate-50"
    >
      <span className="flex items-start justify-between gap-3">
        <span className="min-w-0 truncate font-medium">{supplier(inv)}</span>
        <StatusBadge status={inv.status} />
      </span>
      <span className="mt-1 flex items-baseline justify-between gap-3 text-sm text-slate-500">
        <span className="truncate">
          {inv.invoice_number ?? "—"} · {formatDate(inv.issue_date)}
        </span>
        <span className="shrink-0 font-medium tabular-nums text-slate-900">
          {formatMoney(inv.total_incl_vat, inv.currency)}
        </span>
      </span>
      {inv.review_reasons.length > 0 && (
        <span className="mt-2 block">
          <Reasons reasons={inv.review_reasons} />
        </span>
      )}
    </Link>
  );
}

function InvoiceTable({ invoices, from }: { invoices: InvoiceSummary[]; from?: InvoiceStatus }) {
  return (
    <div className="mt-4 hidden overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 md:block">
      <table className="w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3 font-medium">Statut</th>
            <th className="px-4 py-3 font-medium">Fournisseur</th>
            <th className="px-4 py-3 font-medium">N°</th>
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 text-right font-medium">TTC</th>
            <th className="px-4 py-3 font-medium">Motifs</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {invoices.map((inv) => (
            // relative + the link's after:inset-0 make the whole row clickable, keeping one real link.
            <tr key={inv.id} className="relative hover:bg-brand-50/50">
              <td className="px-4 py-3">
                <StatusBadge status={inv.status} />
              </td>
              <td className="px-4 py-3 font-medium">
                <Link href={detailHref(inv.id, from)} className="after:absolute after:inset-0 focus-visible:underline">
                  {supplier(inv)}
                </Link>
              </td>
              <td className="px-4 py-3 text-slate-600">{inv.invoice_number ?? "—"}</td>
              <td className="px-4 py-3 whitespace-nowrap text-slate-600">{formatDate(inv.issue_date)}</td>
              <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">
                {formatMoney(inv.total_incl_vat, inv.currency)}
              </td>
              <td className="px-4 py-3">
                {inv.review_reasons.length > 0 ? <Reasons reasons={inv.review_reasons} /> : <span className="text-slate-400">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="mt-6 animate-pulse" aria-label="Chargement">
      <div className="grid grid-cols-4 gap-1.5 sm:flex sm:gap-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-14 rounded-xl bg-slate-200 sm:h-11 sm:w-28 sm:rounded-full" />
        ))}
      </div>
      <div className="mt-4 flex flex-col gap-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 rounded-xl bg-slate-200 md:h-12" />
        ))}
      </div>
    </div>
  );
}

/** ?from= lets the detail page's back button return to the same filter. */
function detailHref(id: string, from: InvoiceStatus | undefined): string {
  return `/invoices/${id}${from ? `?from=${from}` : ""}`;
}
