"use client";

import { useActionState } from "react";

import { uploadInvoice } from "@/app/actions";

export function UploadForm() {
  const [error, action, pending] = useActionState(uploadInvoice, null);
  return (
    <form action={action} className="flex items-center gap-3 rounded bg-white p-4 ring-1 ring-neutral-200">
      <input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg" required className="text-sm" />
      <button
        disabled={pending}
        className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {pending ? "Envoi…" : "Déposer une facture"}
      </button>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </form>
  );
}
