"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { STATUS_LABELS } from "@/lib/fields";

/** The list links to a detail with ?from=<status>: going back restores that filter. */
function listHref(from: string | null): string {
  return from && from in STATUS_LABELS ? `/?status=${from}` : "/";
}

function Button({ href }: { href: string }) {
  return (
    <Link
      href={href}
      className="tap group inline-flex items-center gap-1.5 rounded-full bg-white pr-4 pl-2 text-sm font-medium text-brand-800 shadow-sm ring-1 ring-slate-200 transition hover:bg-brand-50 hover:ring-brand-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
    >
      <span className="grid size-7 place-items-center rounded-full bg-brand-50 text-brand-700 transition group-hover:-translate-x-0.5 group-hover:bg-brand-100">
        <svg className="size-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M12.7 4.3a1 1 0 0 1 0 1.4L8.4 10l4.3 4.3a1 1 0 0 1-1.4 1.4l-5-5a1 1 0 0 1 0-1.4l5-5a1 1 0 0 1 1.4 0Z" />
        </svg>
      </span>
      Factures
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
