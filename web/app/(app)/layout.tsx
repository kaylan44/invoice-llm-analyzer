import Image from "next/image";
import Link from "next/link";

// Shell of the signed-in pages. (app) is a route group: it adds a layout, not a URL segment.
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <nav className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2">
          <Link href="/" className="tap flex min-w-0 items-center gap-2.5 font-semibold text-brand-950">
            <Image src="/logo.png" alt="" width={32} height={32} priority />
            <span className="truncate">Invoice-LLM Analyzer</span>
          </Link>
          <ExportMenu />
        </nav>
      </header>
      {children}
    </>
  );
}

/** <details> gives an accessible disclosure with no client JavaScript. */
function ExportMenu() {
  return (
    <details className="relative shrink-0">
      <summary className="tap flex cursor-pointer list-none items-center gap-1.5 rounded-md px-3 text-sm text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
        <svg className="size-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M10 3a1 1 0 0 1 1 1v7.6l2.3-2.3a1 1 0 1 1 1.4 1.4l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L9 11.6V4a1 1 0 0 1 1-1ZM4 15a1 1 0 0 1 1 1h10a1 1 0 1 1 0 2H5a2 2 0 0 1-2-2 1 1 0 0 1 1-1Z" />
        </svg>
        Exporter
      </summary>
      <div className="absolute right-0 mt-1 w-60 overflow-hidden rounded-lg bg-white py-1 text-sm shadow-lg ring-1 ring-slate-200">
        <a href="/api/export?format=csv" className="tap flex flex-col justify-center px-3 hover:bg-brand-50">
          <span>CSV</span>
          <span className="text-xs text-slate-500">Factures validées, pour un tableur</span>
        </a>
        <a href="/api/export?format=json" className="tap flex flex-col justify-center px-3 hover:bg-brand-50">
          <span>JSON</span>
          <span className="text-xs text-slate-500">Avec les lignes et les catégories</span>
        </a>
      </div>
    </details>
  );
}
