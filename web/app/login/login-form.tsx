"use client";

import { useActionState } from "react";

import { login } from "./actions";

export function LoginForm() {
  const [error, action, pending] = useActionState(login, null);
  return (
    <form action={action} className="mt-6 flex flex-col gap-3">
      <input
        name="passphrase"
        type="password"
        required
        autoFocus
        className="rounded border border-neutral-300 px-3 py-2"
        aria-label="Phrase secrète"
      />
      <button
        disabled={pending}
        className="rounded bg-neutral-900 px-3 py-2 text-white disabled:opacity-50"
      >
        Entrer
      </button>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </form>
  );
}
