"use client";

import { useActionState } from "react";

import { saveCorrections, validateInvoice, type ReviewState } from "@/app/actions";
import type { Invoice } from "@/lib/api";
import { FIELDS, flaggedFields } from "@/lib/fields";

const INITIAL: ReviewState = { error: null, saved: false };

/** "20.0000" -> "20", "4.9000" -> "4.9": Postgres numeric keeps its scale, a reader doesn't need it. */
function trim(value: string | null): string {
  if (value == null) return "—";
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

export function ReviewForm({ invoice }: { invoice: Invoice }) {
  // bind fixes the first argument (the invoice id): the action then has the
  // (previousState, formData) signature useActionState expects.
  const [saveState, save, saving] = useActionState(saveCorrections.bind(null, invoice.id), INITIAL);
  const [validateState, validate, validating] = useActionState(
    validateInvoice.bind(null, invoice.id),
    INITIAL,
  );
  const locked = invoice.status === "validated";
  const flagged = flaggedFields(invoice.review_reasons, invoice);

  return (
    <>
      {invoice.review_reasons.length > 0 && (
        <ul className="rounded bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200">
          {invoice.review_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}

      {/* key: remount with the new values after a save, so the inputs show what is stored. */}
      <form key={invoice.updated_at} action={save} className="grid grid-cols-2 gap-3 rounded bg-white p-4 ring-1 ring-neutral-200">
        {FIELDS.map(({ name, label, type }) => {
          const value = invoice[name] ?? "";
          return (
            <label key={name} className="flex flex-col gap-1 text-sm">
              <span className="flex items-center gap-2 text-neutral-600">
                {label}
                <span
                  className={`rounded px-1.5 text-xs ${flagged.has(name) ? "bg-amber-100 text-amber-900" : "bg-emerald-50 text-emerald-700"}`}
                >
                  {flagged.has(name) ? "À vérifier" : "Sûr"}
                </span>
              </span>
              <input
                name={name}
                type={type}
                step={type === "number" ? "0.01" : undefined}
                defaultValue={value}
                disabled={locked}
                className="rounded border border-neutral-300 px-2 py-1 tabular-nums disabled:bg-neutral-100"
              />
              <input type="hidden" name={`original:${name}`} value={value} />
            </label>
          );
        })}
        {!locked && (
          <div className="col-span-2 flex items-center gap-3">
            <button disabled={saving} className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
              Enregistrer les corrections
            </button>
            {saveState.saved && <span className="text-sm text-emerald-700">Enregistré, contrôles relancés.</span>}
            {saveState.error && <span className="text-sm text-red-700">{saveState.error}</span>}
          </div>
        )}
      </form>

      {!locked && (
        <form action={validate} className="flex flex-wrap items-center gap-3 rounded bg-white p-4 ring-1 ring-neutral-200">
          {invoice.status === "to_review" && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" name="acknowledge" required />
              Je valide malgré les motifs ci-dessus
            </label>
          )}
          <button disabled={validating} className="rounded bg-emerald-700 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            Valider la facture
          </button>
          {validateState.error && <span className="text-sm text-red-700">{validateState.error}</span>}
        </form>
      )}

      <table className="w-full border-collapse bg-white text-sm ring-1 ring-neutral-200">
        <thead className="text-left text-neutral-500">
          <tr>
            <th className="p-2">Libellé</th>
            <th className="p-2 text-right">Qté</th>
            <th className="p-2 text-right">PU</th>
            <th className="p-2 text-right">TVA</th>
            <th className="p-2 text-right">Montant</th>
            <th className="p-2">Catégorie</th>
          </tr>
        </thead>
        <tbody>
          {invoice.lines.map((line) => (
            <tr key={line.position} className="border-t border-neutral-100">
              <td className="p-2">{line.description}</td>
              <td className="p-2 text-right tabular-nums">{trim(line.quantity)}</td>
              <td className="p-2 text-right tabular-nums">{trim(line.unit_price)}</td>
              <td className="p-2 text-right tabular-nums whitespace-nowrap">{trim(line.vat_rate)} %</td>
              <td className="p-2 text-right tabular-nums">{line.amount}</td>
              <td className="p-2">
                {line.category_code ?? "—"}
                {line.category_score != null && (
                  <span className="ml-1 text-xs text-neutral-500">({line.category_score.toFixed(2)})</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
