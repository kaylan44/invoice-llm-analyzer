"use client";

import { useActionState } from "react";

import { login } from "./actions";

export function LoginForm() {
  const [error, action, pending] = useActionState(login, null);
  return (
    <form action={action} className="mt-5 flex flex-col gap-1">
      <label htmlFor="passphrase" className="text-sm font-medium">
        Phrase secrète
      </label>
      <input
        id="passphrase"
        name="passphrase"
        type="password"
        autoComplete="current-password"
        required
        autoFocus
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "passphrase-error" : undefined}
        className="tap rounded-md border border-slate-300 px-3 text-base outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-200"
      />
      {error && (
        <p id="passphrase-error" className="text-sm text-red-700">
          {error}
        </p>
      )}
      <button
        disabled={pending}
        className="tap mt-3 rounded-md bg-brand-600 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
      >
        {pending ? "Vérification…" : "Entrer"}
      </button>
    </form>
  );
}
