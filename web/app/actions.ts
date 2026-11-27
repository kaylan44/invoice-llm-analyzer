"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import { FIELDS } from "@/lib/fields";

function message(error: unknown): string {
  return error instanceof ApiError ? `${error.status} : ${error.message}` : "Erreur inattendue.";
}

export async function uploadInvoice(_previous: string | null, form: FormData): Promise<string | null> {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return "Choisis un fichier.";
  let invoiceId: string;
  try {
    invoiceId = (await api.upload(file)).invoice_id;
  } catch (error) {
    return message(error);
  }
  redirect(`/invoices/${invoiceId}`); // outside try: redirect() works by throwing
}

export type ReviewState = { error: string | null; saved: boolean };

/** Send only the fields the reviewer changed; an emptied field becomes null. */
export async function saveCorrections(
  id: string,
  _previous: ReviewState,
  form: FormData,
): Promise<ReviewState> {
  const changes: Record<string, string | null> = {};
  for (const { name } of FIELDS) {
    const value = String(form.get(name) ?? "").trim();
    const original = String(form.get(`original:${name}`) ?? "");
    if (value !== original) changes[name] = value === "" ? null : value;
  }
  if (Object.keys(changes).length === 0) return { error: null, saved: false };
  try {
    await api.correct(id, changes);
  } catch (error) {
    return { error: message(error), saved: false };
  }
  revalidatePath(`/invoices/${id}`);
  return { error: null, saved: true };
}

export async function validateInvoice(
  id: string,
  _previous: ReviewState,
  form: FormData,
): Promise<ReviewState> {
  try {
    await api.validate(id, form.get("acknowledge") === "on");
  } catch (error) {
    return { error: message(error), saved: false };
  }
  revalidatePath(`/invoices/${id}`);
  return { error: null, saved: true };
}
