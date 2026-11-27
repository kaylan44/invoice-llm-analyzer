"use client";

import { useActionState, useRef, useState } from "react";

import { uploadInvoice } from "@/app/actions";

const ACCEPT = ".pdf,.png,.jpg,.jpeg";

/** Large drop zone. Picking or dropping a file submits at once: there is nothing else to fill. */
export function UploadForm() {
  const [error, action, pending] = useActionState(uploadInvoice, null);
  const form = useRef<HTMLFormElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  function pick(camera: boolean) {
    const el = input.current;
    if (!el) return;
    // capture opens the camera on phones; desktop browsers ignore it.
    if (camera) el.setAttribute("capture", "environment");
    else el.removeAttribute("capture");
    el.accept = camera ? "image/*" : ACCEPT;
    el.click();
  }

  function submit(files: FileList | null) {
    if (!files?.length || !input.current) return;
    input.current.files = files;
    setFileName(files[0].name);
    form.current?.requestSubmit();
  }

  return (
    <form ref={form} action={action}>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(e) => {
          // Ignore leaves into a child element.
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          submit(e.dataTransfer.files);
        }}
        className={`flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-8 text-center transition sm:py-12 lg:min-h-72 lg:gap-4 lg:py-16 ${
          dragging ? "border-brand-500 bg-brand-100/70" : "border-brand-300 bg-brand-50/60"
        }`}
      >
        <span className="brand-gradient grid size-14 place-items-center rounded-2xl text-pixel shadow-lg shadow-brand-900/20 lg:size-20">
          {pending ? (
            <svg className="size-7 animate-spin lg:size-10" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".3" strokeWidth="3" />
              <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
          ) : (
            <svg className="size-7 lg:size-10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5" />
              <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
            </svg>
          )}
        </span>
        <span className="flex flex-col gap-1" aria-live="polite">
          <span className="text-base font-semibold text-brand-950 lg:text-xl">
            {pending ? (
              `Envoi de ${fileName ?? "la facture"}…`
            ) : dragging ? (
              "Lâche pour déposer la facture"
            ) : (
              <>
                <span className="hidden sm:inline">Glisse une facture ici</span>
                <span className="sm:hidden">Dépose une facture</span>
              </>
            )}
          </span>
          <span className="text-sm text-slate-500">PDF, PNG ou JPG, une facture par fichier</span>
        </span>
        <span className="flex flex-col items-stretch gap-2 self-stretch sm:flex-row sm:items-center sm:self-auto">
          <button
            type="button"
            disabled={pending}
            onClick={() => pick(false)}
            className="tap rounded-lg bg-brand-600 px-5 text-sm font-medium text-white shadow-sm hover:bg-brand-700 disabled:opacity-50"
          >
            Choisir un fichier
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => pick(true)}
            className="tap rounded-lg bg-white px-5 text-sm font-medium text-brand-800 ring-1 ring-brand-200 disabled:opacity-50 sm:hidden"
          >
            Prendre une photo
          </button>
        </span>
        <input
          ref={input}
          name="file"
          type="file"
          accept={ACCEPT}
          className="sr-only"
          tabIndex={-1}
          onChange={(e) => submit(e.currentTarget.files)}
        />
        {error && <p className="text-sm text-red-700">{error}</p>}
      </div>
    </form>
  );
}
