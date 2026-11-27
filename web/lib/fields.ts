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

export const STATUS_LABELS = {
  pending: "En attente",
  to_review: "À vérifier",
  validated: "Validée",
} as const;
