import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Factures fournisseurs",
  description: "Extraction de factures avec revue humaine",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-neutral-50 text-neutral-900">
        <header className="border-b border-neutral-200 bg-white">
          <nav className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 text-sm">
            <Link href="/" className="font-semibold">
              Factures fournisseurs
            </Link>
            <a href="/api/export?format=csv" className="text-neutral-600 hover:underline">
              Export CSV
            </a>
            <a href="/api/export?format=json" className="text-neutral-600 hover:underline">
              Export JSON
            </a>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
