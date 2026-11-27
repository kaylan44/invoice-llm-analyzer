import Image from "next/image";

import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <main className="brand-gradient flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center text-white">
          <Image src="/logo.png" alt="" width={80} height={80} priority className="drop-shadow-xl" />
          <span className="text-lg font-semibold">Invoice-LLM Analyzer</span>
        </div>
        <div className="rounded-2xl bg-white p-6 shadow-xl shadow-black/20">
          <h1 className="text-lg font-semibold">Accès à la démo</h1>
          <p className="mt-1 text-sm text-slate-500">Extraction de factures par Gemini, contrôlée par un humain.</p>
          <LoginForm />
        </div>
      </div>
    </main>
  );
}
