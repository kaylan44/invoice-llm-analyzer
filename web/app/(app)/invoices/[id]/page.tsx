import { Suspense, type ReactNode } from "react";

import { BackToList } from "@/components/back-to-list";
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
      <Suspense
        fallback={
          <>
            <Header title={<span className="inline-block h-7 w-48 animate-pulse rounded bg-slate-200" />} />
            <ReviewSkeleton />
          </>
        }
      >
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
        <Header title="Nouvelle facture" />
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
      <Header
        title={invoice.supplier_name ?? "Fournisseur inconnu"}
        badge={<StatusBadge status={invoice.status} />}
        meta={
          <>
            N° {invoice.invoice_number ?? "—"} · {formatMoney(invoice.total_incl_vat, invoice.currency)}
            {invoice.extraction && (
              <span className="hidden text-slate-400 sm:inline">
                {" "}
                · {invoice.extraction.model}, prompt {invoice.extraction.prompt_version}
              </span>
            )}
          </>
        }
      />
      <ReviewLayout
        documentUrl={`/api/invoices/${id}/document`}
        flaggedCount={flaggedFields(invoice.review_reasons, invoice).size}
      >
        <ReviewForm invoice={invoice} />
      </ReviewLayout>
    </>
  );
}

/** Title row: back button, then the title block, like an app bar. */
function Header({ title, badge, meta }: { title: ReactNode; badge?: ReactNode; meta?: ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <BackToList />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="min-w-0 truncate text-xl font-semibold tracking-tight text-brand-950 sm:text-2xl">{title}</h1>
          {badge}
        </div>
        {meta && <p className="truncate text-sm text-slate-500">{meta}</p>}
      </div>
    </div>
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
