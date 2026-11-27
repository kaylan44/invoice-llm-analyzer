"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { GATE_COOKIE, expectedToken, gateToken } from "@/lib/gate";

export async function login(_previous: string | null, form: FormData): Promise<string | null> {
  const expected = await expectedToken();
  if (!expected) return "DEMO_PASSPHRASE n'est pas configurée : accès fermé.";
  const token = await gateToken(String(form.get("passphrase") ?? ""));
  if (token !== expected) return "Phrase secrète incorrecte. Vérifie les majuscules et réessaie.";
  (await cookies()).set(GATE_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 24 * 7,
    path: "/",
  });
  redirect("/");
}
