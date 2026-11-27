import type { Metadata, Viewport } from "next";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Invoice-LLM Analyzer",
  description: "Extraction de factures fournisseurs avec revue humaine",
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
};

// The header lives in app/(app)/layout.tsx: the login page has none.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-slate-50 text-slate-900">
        {children}
        <Analytics />
      </body>
    </html>
  );
}
