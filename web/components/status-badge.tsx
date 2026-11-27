import type { InvoiceStatus } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/fields";

const STYLES: Record<InvoiceStatus, string> = {
  pending: "bg-sky-100 text-sky-800",
  to_review: "bg-amber-100 text-amber-900",
  validated: "bg-emerald-100 text-emerald-800",
};

export function StatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}
