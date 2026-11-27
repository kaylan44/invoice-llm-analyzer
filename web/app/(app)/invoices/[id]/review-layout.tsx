"use client";

import { useState, useSyncExternalStore, type ReactNode } from "react";

const DESKTOP = "(min-width: 1024px)"; // Tailwind lg

function subscribe(onChange: () => void) {
  const query = window.matchMedia(DESKTOP);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/**
 * Desktop: document and data side by side. Below lg: two tabs.
 * The iframe mounts only when it is visible, so a phone never fetches (or downloads) the
 * PDF unless the reviewer opens the Document tab.
 */
export function ReviewLayout({
  documentUrl,
  flaggedCount,
  children,
}: {
  documentUrl: string;
  flaggedCount: number;
  children: ReactNode;
}) {
  const [tab, setTab] = useState<"data" | "doc">("data");
  const desktop = useSyncExternalStore(subscribe, () => window.matchMedia(DESKTOP).matches, () => false);
  const showDocument = desktop || tab === "doc";

  return (
    <>
      <div className="sticky top-[61px] z-10 -mx-4 mt-4 bg-slate-50/95 px-4 py-2 backdrop-blur lg:hidden">
        <div role="tablist" className="grid grid-cols-2 rounded-lg bg-slate-200/70 p-1 text-sm">
          {(
            [
              ["data", "Données"],
              ["doc", "Document"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              role="tab"
              type="button"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={`tap rounded-md ${tab === id ? "bg-white font-medium shadow-sm" : "text-slate-600"}`}
            >
              {label}
              {id === "data" && flaggedCount > 0 && <span className="text-amber-700"> · {flaggedCount}</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 grid gap-6 pb-6 lg:mt-6 lg:grid-cols-2 lg:items-start">
        <div className={`${tab === "doc" ? "flex" : "hidden"} flex-col gap-3 lg:sticky lg:top-20 lg:flex`}>
          {showDocument && (
            <iframe
              // PDF open parameters: fit the page width, hide the dark toolbar and the
              // thumbnails pane. Chrome/Edge read view, toolbar and navpanes; Firefox's
              // pdf.js reads zoom and pagemode. Images ignore the fragment.
              src={`${documentUrl}#view=FitH&zoom=page-width&toolbar=0&navpanes=0&pagemode=none`}
              title="Document"
              className="h-[70dvh] w-full rounded-xl bg-white ring-1 ring-slate-200 lg:h-[calc(100dvh-7rem)]"
            />
          )}
          <a
            href={documentUrl}
            target="_blank"
            rel="noopener"
            // On desktop too: with the toolbar hidden, the new tab is where zoom and download live.
            className="tap flex items-center justify-center rounded-md text-sm text-brand-800 ring-1 ring-slate-200 hover:bg-white"
          >
            Ouvrir le document en plein écran ↗
          </a>
        </div>
        <div className={`${tab === "data" ? "" : "hidden"} min-w-0 lg:block`}>{children}</div>
      </div>
    </>
  );
}
