// Header fields shown on the review screen, and which review reasons point at them.
// A reason looks like "totals: HT + TVA != TTC" (the check name before the colon).

export const FIELDS = [
  { name: "supplier_name", label: "Fournisseur", type: "text" },
  { name: "supplier_vat_number", label: "N° de TVA", type: "text" },
  { name: "supplier_siret", label: "SIRET", type: "text" },
  { name: "invoice_number", label: "N° de facture", type: "text" },
  { name: "issue_date", label: "Date", type: "date" },
  { name: "due_date", label: "Échéance", type: "date" },
  { name: "currency", label: "Devise", type: "text" },
  { name: "total_excl_vat", label: "Total HT", type: "number" },
  { name: "total_vat", label: "Total TVA", type: "number" },
  { name: "total_incl_vat", label: "Total TTC", type: "number" },
] as const;

export type FieldName = (typeof FIELDS)[number]["name"];

const REQUIRED: FieldName[] = [
  "supplier_name",
  "invoice_number",
  "issue_date",
  "currency",
  "total_excl_vat",
  "total_vat",
  "total_incl_vat",
];

const FIELDS_BY_CHECK: Record<string, FieldName[]> = {
  totals: ["total_excl_vat", "total_vat", "total_incl_vat"],
  lines_sum: ["total_excl_vat"],
  vat_amount: ["total_vat"],
  dates: ["issue_date", "due_date"],
  currency: ["currency"],
  identifiers: ["supplier_siret", "supplier_vat_number"],
  duplicate: ["supplier_name", "invoice_number"],
};

/** Fields to badge "À vérifier": named by a failed check, or required and empty. */
export function flaggedFields(
  reasons: string[],
  values: Partial<Record<FieldName, string | null>>,
): Set<FieldName> {
  const flagged = new Set<FieldName>();
  for (const reason of reasons) {
    const check = reason.split(":")[0];
    if (check === "extraction_failed") FIELDS.forEach((f) => flagged.add(f.name));
    if (check === "required_fields") REQUIRED.filter((f) => !values[f]).forEach((f) => flagged.add(f));
    (FIELDS_BY_CHECK[check] ?? []).forEach((f) => flagged.add(f));
  }
  return flagged;
}

/** Review form sections, in display order. */
export const FIELD_GROUPS: { title: string; fields: FieldName[] }[] = [
  { title: "Fournisseur", fields: ["supplier_name", "supplier_vat_number", "supplier_siret"] },
  { title: "Facture", fields: ["invoice_number", "issue_date", "due_date", "currency"] },
  { title: "Montants", fields: ["total_excl_vat", "total_vat", "total_incl_vat"] },
];

const CHECK_LABELS: Record<string, string> = {
  totals: "Totaux incohérents",
  lines_sum: "Somme des lignes",
  vat_amount: "Montant de TVA",
  dates: "Dates",
  currency: "Devise",
  identifiers: "Identifiants",
  duplicate: "Doublon possible",
  required_fields: "Champs manquants",
  extraction_failed: "Échec d'extraction",
};

/** "totals: HT + TVA != TTC" -> { check: "totals", label: "Totaux incohérents", detail: "HT + TVA != TTC" }. */
export function parseReason(reason: string) {
  const [check, ...rest] = reason.split(":");
  return {
    check,
    label: CHECK_LABELS[check] ?? check,
    detail: rest.join(":").trim(),
    field: FIELDS_BY_CHECK[check]?.[0] ?? null,
  };
}

export const STATUS_LABELS = {
  pending: "En attente",
  to_review: "À vérifier",
  validated: "Validée",
} as const;
