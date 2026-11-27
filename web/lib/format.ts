// Display formatting. The API sends Postgres numerics as strings with their scale
// ("1498.0000") and dates as ISO days ("2026-11-03").

const LOCALE = "fr-FR";

/** "1498.0000", "EUR" -> "1 498,00 €". Unknown or missing currency: plain number. */
export function formatMoney(value: string | null, currency: string | null): string {
  if (value == null) return "—";
  const amount = Number(value);
  if (currency) {
    try {
      return new Intl.NumberFormat(LOCALE, { style: "currency", currency }).format(amount);
    } catch {
      // RangeError on a currency code Intl does not know: fall through.
    }
  }
  return `${formatNumber(value)}${currency ? ` ${currency}` : ""}`;
}

/** "18.5000" -> "18,5". */
export function formatNumber(value: string | null): string {
  if (value == null) return "—";
  return new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 }).format(Number(value));
}

/** "2026-11-03" -> "03 nov. 2026". UTC so the day never shifts with the server's zone. */
export function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(LOCALE, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

/** "20.0000" -> "20", "4.9000" -> "4.9": the value an input should show, dot kept. */
export function trimScale(value: string | null): string {
  if (value == null) return "";
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}
