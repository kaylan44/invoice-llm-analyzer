import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";

import { ReviewForm } from "./review-form";

export default function ReviewPage({ params }: PageProps<"/invoices/[id]">) {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-6">
      <Link href="/" className="text-sm text-neutral-600 hover:underline">
        ← Toutes les factures
      </Link>
      <Suspense fallback={<p className="mt-6 text-sm text-neutral-500">Chargement…</p>}>
        <Review params={params} />
      </Suspense>
    </main>
  );
}

async function Review({ params }: Pick<PageProps<"/invoices/[id]">, "params">) {
  const { id } = await params;
  const invoice = await api.get(id);
  const processing = invoice.job && ["queued", "running"].includes(invoice.job.status);

  return (
    <div className="mt-4 grid gap-6 lg:grid-cols-2">
      {/* Left: the document, served by our route handler (the API token stays server-side). */}
      <iframe
        src={`/api/invoices/${id}/document`}
        title="Document"
        className="h-[85vh] w-full rounded bg-white ring-1 ring-neutral-200"
      />
      <section className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <StatusBadge status={invoice.status} />
          {invoice.extraction && (
            <span className="text-xs text-neutral-500">
              {invoice.extraction.model}, {invoice.extraction.prompt_version}
            </span>
          )}
        </div>
        {processing ? (
          <p className="rounded bg-white p-4 text-sm ring-1 ring-neutral-200">
            Extraction en cours ({invoice.job?.status}).{" "}
            <Link href={`/invoices/${id}`} className="underline">
              Actualiser
            </Link>
          </p>
        ) : (
          <ReviewForm invoice={invoice} />
        )}
      </section>
    </div>
  );
}
