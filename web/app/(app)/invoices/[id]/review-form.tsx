"use client";

import { useActionState, useState, type FormEvent } from "react";

import { saveCorrections, validateInvoice, type ReviewState } from "@/app/actions";
import type { Invoice, InvoiceLine } from "@/lib/api";
import { FIELD_GROUPS, FIELDS, flaggedFields, parseReason, type FieldName } from "@/lib/fields";
import { formatNumber, trimScale } from "@/lib/format";

const INITIAL: ReviewState = { error: null, saved: false };
const SAVE_FORM = "corrections";

export function ReviewForm({ invoice }: { invoice: Invoice }) {
  // bind fixes the first argument (the invoice id): the action then has the
  // (previousState, formData) signature useActionState expects.
  const [saveState, save, saving] = useActionState(saveCorrections.bind(null, invoice.id), INITIAL);
  const [validateState, validate, validating] = useActionState(
    validateInvoice.bind(null, invoice.id),
    INITIAL,
  );
  // Fields whose input differs from the stored value. Validating with unsaved edits
  // would silently drop them, so the Validate button waits until they are saved.
  const [dirty, setDirty] = useState<ReadonlySet<string>>(new Set());
  // A save remounts the form with the stored values (key below): forget the edits then.
  const [version, setVersion] = useState(invoice.updated_at);
  if (version !== invoice.updated_at) {
    setVersion(invoice.updated_at);
    setDirty(new Set());
  }

  const locked = invoice.status === "validated";
  const flagged = flaggedFields(invoice.review_reasons, invoice);
  const byName = new Map(FIELDS.map((f) => [f.name, f]));
  // Where a reason with no field of its own (required_fields) leads: the first flagged field.
  const firstFlagged = FIELD_GROUPS.flatMap((g) => g.fields).find((name) => flagged.has(name)) ?? null;

  function track(event: FormEvent<HTMLFormElement>) {
    const input = event.target as HTMLInputElement;
    if (!byName.has(input.name as FieldName)) return;
    const changed = input.value !== input.defaultValue;
    setDirty((previous) => {
      if (previous.has(input.name) === changed) return previous;
      const next = new Set(previous);
      if (changed) next.add(input.name);
      else next.delete(input.name);
      return next;
    });
  }

  function focusField(name: string | null) {
    if (!name) return;
    const el = document.getElementById(`field-${name}`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    el?.focus({ preventScroll: true });
  }

  return (
    <div className="flex flex-col gap-4">
      {locked && (
        <p className="rounded-xl bg-check-50 p-4 text-sm text-check-900 ring-1 ring-check-200">
          Facture validée : lecture seule. Elle figure dans les exports.
        </p>
      )}

      {invoice.review_reasons.length > 0 && (
        <section className="rounded-xl bg-amber-50 p-4 ring-1 ring-amber-200">
          <h2 className="text-sm font-semibold text-amber-900">
            {invoice.review_reasons.length} point{invoice.review_reasons.length > 1 ? "s" : ""} à vérifier
          </h2>
          <ul className="mt-2 flex flex-col gap-2 text-sm text-amber-900">
            {invoice.review_reasons.map((reason) => {
              const { label, detail, field } = parseReason(reason);
              return (
                <li key={reason}>
                  <button type="button" onClick={() => focusField(field ?? firstFlagged)} className="text-left hover:underline">
                    <span className="font-medium">{label}</span>
                    {detail && ` · ${detail}`}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* key: remount with the new values after a save, so the inputs show what is stored. */}
      <form key={invoice.updated_at} id={SAVE_FORM} action={save} onInput={track} className="flex flex-col gap-4">
        {FIELD_GROUPS.map((group) => (
          <fieldset key={group.title} className="rounded-xl bg-white p-4 ring-1 ring-slate-200">
            <legend className="float-left mb-3 w-full text-sm font-semibold">{group.title}</legend>
            <div className="clear-both grid grid-cols-1 gap-3 sm:grid-cols-2">
              {group.fields.map((name) => {
                const { label, type } = byName.get(name)!;
                const raw = invoice[name];
                // Numbers lose their scale ("1240.0000" -> "1240") in the input AND in the
                // original, so an untouched field is never sent as a change.
                const value = type === "number" ? trimScale(raw) : (raw ?? "");
                const isFlagged = flagged.has(name);
                return (
                  <label key={name} className={`flex flex-col gap-1 ${name === "supplier_name" ? "sm:col-span-2" : ""}`}>
                    <span className="flex items-center gap-2 text-sm text-slate-600">
                      {label}
                      {isFlagged && (
                        <span className="rounded bg-amber-100 px-1.5 text-xs font-medium text-amber-900">À vérifier</span>
                      )}
                      {dirty.has(name) && <span className="rounded bg-brand-100 px-1.5 text-xs text-brand-800">Modifié</span>}
                    </span>
                    <input
                      id={`field-${name}`}
                      name={name}
                      type={type}
                      step={type === "number" ? "0.01" : undefined}
                      inputMode={type === "number" ? "decimal" : undefined}
                      defaultValue={value}
                      disabled={locked}
                      // text-base on phones: Safari iOS zooms into inputs under 16 px.
                      className={`tap w-full rounded-md border bg-white px-3 text-base tabular-nums outline-none focus:ring-2 sm:text-sm disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-700 ${
                        isFlagged
                          ? "border-amber-400 bg-amber-50/40 focus:ring-amber-300"
                          : "border-slate-300 focus:border-brand-500 focus:ring-brand-200"
                      }`}
                    />
                    <input type="hidden" name={`original:${name}`} value={value} />
                  </label>
                );
              })}
            </div>
          </fieldset>
        ))}
      </form>

      {invoice.lines.length > 0 && <Lines lines={invoice.lines} />}

      {!locked && (
        <form
          action={validate}
          // Sticky at the bottom of the screen on phones, a plain card on desktop.
          className="sticky bottom-0 z-10 -mx-4 border-t border-slate-200 bg-white/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur lg:static lg:mx-0 lg:rounded-xl lg:border-0 lg:pb-3 lg:ring-1 lg:ring-slate-200"
        >
          {dirty.size > 0 ? (
            <p className="mb-2 text-sm text-brand-800">
              {dirty.size} modification{dirty.size > 1 ? "s" : ""} non enregistrée{dirty.size > 1 ? "s" : ""}. Enregistre
              avant de valider.
            </p>
          ) : (
            invoice.status === "to_review" && (
              <label className="mb-3 flex items-start gap-2 text-sm">
                <input type="checkbox" name="acknowledge" required className="mt-0.5 size-4 accent-brand-600" />
                Je valide malgré les motifs signalés
              </label>
            )
          )}
          {saveState.saved && dirty.size === 0 && (
            <p className="mb-2 text-sm text-check-700">Enregistré, contrôles relancés.</p>
          )}
          {saveState.error && <p className="mb-2 text-sm text-red-700">{saveState.error}</p>}
          {validateState.error && <p className="mb-2 text-sm text-red-700">{validateState.error}</p>}
          <div className="flex gap-2">
            {/* form= ties this button to the corrections form above. */}
            <button
              form={SAVE_FORM}
              disabled={saving || dirty.size === 0}
              className="tap flex-1 rounded-md px-4 text-sm font-medium text-brand-800 ring-1 ring-brand-200 hover:bg-brand-50 disabled:text-slate-400 disabled:ring-slate-200 disabled:hover:bg-transparent sm:flex-none"
            >
              {saving ? "Enregistrement…" : "Enregistrer"}
            </button>
            <button
              disabled={validating || dirty.size > 0}
              className="tap flex-1 rounded-md bg-check-700 px-4 text-sm font-medium text-white hover:bg-check-800 disabled:bg-slate-200 disabled:text-slate-500 sm:flex-none"
            >
              {validating ? "Validation…" : "Valider la facture"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function Category({ line }: { line: InvoiceLine }) {
  if (!line.category_code) return <span className="text-slate-400">—</span>;
  return (
    <>
      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs">{line.category_code}</span>
      {line.category_score != null && (
        <span className={`ml-1.5 text-xs ${line.category_score < 0.7 ? "text-amber-700" : "text-slate-400"}`}>
          {line.category_score.toFixed(2)}
        </span>
      )}
    </>
  );
}

function Lines({ lines }: { lines: InvoiceLine[] }) {
  return (
    <section className="rounded-xl bg-white ring-1 ring-slate-200">
      <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
        Lignes <span className="font-normal text-slate-400">{lines.length}</span>
      </h2>
      <ul className="divide-y divide-slate-100 md:hidden">
        {lines.map((line) => (
          <li key={line.position} className="px-4 py-3 text-sm">
            <div className="flex justify-between gap-3">
              <span className="min-w-0">{line.description ?? "—"}</span>
              <span className="shrink-0 font-medium tabular-nums">{formatNumber(line.amount)}</span>
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {formatNumber(line.quantity)} × {formatNumber(line.unit_price)} · TVA {formatNumber(line.vat_rate)} %
            </div>
            <div className="mt-1.5">
              <Category line={line} />
            </div>
          </li>
        ))}
      </ul>
      <table className="hidden w-full text-sm md:table">
        <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2 font-medium">Libellé</th>
            <th className="px-2 py-2 text-right font-medium">Qté</th>
            <th className="px-2 py-2 text-right font-medium">PU</th>
            <th className="px-2 py-2 text-right font-medium">TVA</th>
            <th className="px-2 py-2 text-right font-medium">Montant</th>
            <th className="px-4 py-2 font-medium">Catégorie</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {lines.map((line) => (
            <tr key={line.position}>
              <td className="px-4 py-2">{line.description ?? "—"}</td>
              <td className="px-2 text-right tabular-nums">{formatNumber(line.quantity)}</td>
              <td className="px-2 text-right tabular-nums">{formatNumber(line.unit_price)}</td>
              <td className="px-2 text-right whitespace-nowrap tabular-nums">{formatNumber(line.vat_rate)} %</td>
              <td className="px-2 text-right tabular-nums">{formatNumber(line.amount)}</td>
              <td className="px-4 py-2 whitespace-nowrap">
                <Category line={line} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
