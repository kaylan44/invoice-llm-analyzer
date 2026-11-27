import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <main className="mx-auto mt-24 max-w-sm px-4">
      <h1 className="text-xl font-semibold">Accès à la démo</h1>
      <p className="mt-2 text-sm text-neutral-600">Saisis la phrase secrète de la démo.</p>
      <LoginForm />
    </main>
  );
}
