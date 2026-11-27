import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import { flaggedFields } from "@/lib/fields";
import { formatMoney } from "@/lib/format";

import { AutoRefresh } from "./auto-refresh";
import { ReviewForm } from "./review-form";
import { ReviewLayout } from "./review-layout";

export default function ReviewPage({ params }: PageProps<"/invoices/[id]">) {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 pt-4 sm:pt-6">
      <Link href="/" className="tap -ml-2 inline-flex items-center rounded-md px-2 text-sm text-slate-600 hover:bg-slate-100">
        ← Factures
      </Link>
      <Suspense fallback={<ReviewSkeleton />}>
        <Review params={params} />
      </Suspense>
    </main>
  );
}

async function Review({ params }: Pick<PageProps<"/invoices/[id]">, "params">) {
  const { id } = await params;
  const invoice = await api.get(id);
  const processing = invoice.job && ["queued", "running"].includes(invoice.job.status);

  if (processing) {
    return (
      <>
        <AutoRefresh />
        <div className="mt-4 flex items-center gap-3 rounded-xl bg-white p-4 ring-1 ring-slate-200">
          <Spinner />
          <div className="text-sm">
            <div className="font-medium">Extraction en cours</div>
            <div className="text-slate-500">Gemini lit le document. La page se met à jour seule.</div>
          </div>
        </div>
        <ReviewSkeleton />
      </>
    );
  }

  return (
    <>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="min-w-0 text-xl font-semibold tracking-tight text-brand-950 sm:text-2xl">
          {invoice.supplier_name ?? "Fournisseur inconnu"}
        </h1>
        <StatusBadge status={invoice.status} />
      </div>
      <p className="text-sm text-slate-500">
        N° {invoice.invoice_number ?? "—"} · {formatMoney(invoice.total_incl_vat, invoice.currency)}
        {invoice.extraction && (
          <span className="text-slate-400">
            {" "}
            · {invoice.extraction.model}, prompt {invoice.extraction.prompt_version}
          </span>
        )}
      </p>
      <ReviewLayout
        documentUrl={`/api/invoices/${id}/document`}
        flaggedCount={flaggedFields(invoice.review_reasons, invoice).size}
      >
        <ReviewForm invoice={invoice} />
      </ReviewLayout>
    </>
  );
}

function Spinner() {
  return (
    <svg className="size-5 shrink-0 animate-spin text-brand-600" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function ReviewSkeleton() {
  return (
    <div className="mt-4 grid animate-pulse gap-6 lg:grid-cols-2" aria-label="Chargement">
      <div className="hidden h-[calc(100dvh-7rem)] rounded-xl bg-slate-200 lg:block" />
      <div className="flex flex-col gap-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-xl bg-white p-4 ring-1 ring-slate-200">
            <div className="h-4 w-24 rounded bg-slate-200" />
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="h-11 rounded bg-slate-200" />
              <div className="h-11 rounded bg-slate-200" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
