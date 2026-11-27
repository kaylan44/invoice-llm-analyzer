"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { STATUS_LABELS } from "@/lib/fields";

/** The list links to a detail with ?from=<status>: going back restores that filter. */
function listHref(from: string | null): string {
  return from && from in STATUS_LABELS ? `/?status=${from}` : "/";
}

/** Square icon button that sits on the title row, like an app bar. */
function Button({ href }: { href: string }) {
  return (
    <Link
      href={href}
      aria-label="Retour aux factures"
      title="Retour aux factures"
      className="grid size-11 shrink-0 place-items-center rounded-xl bg-white text-slate-600 shadow-sm ring-1 ring-slate-200 transition hover:bg-brand-50 hover:text-brand-700 hover:ring-brand-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
    >
      <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m15 18-6-6 6-6" />
      </svg>
    </Link>
  );
}

function WithFilter() {
  return <Button href={listHref(useSearchParams().get("from"))} />;
}

export function BackToList() {
  // useSearchParams is request data: the static shell renders the plain link.
  return (
    <Suspense fallback={<Button href="/" />}>
      <WithFilter />
    </Suspense>
  );
}
