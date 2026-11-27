import type { InvoiceStatus } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/fields";

const STYLES: Record<InvoiceStatus, string> = {
  pending: "bg-sky-50 text-sky-800 ring-sky-200",
  to_review: "bg-amber-50 text-amber-900 ring-amber-200",
  validated: "bg-check-50 text-check-800 ring-check-200",
};

export function StatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      {status === "pending" && <span className="size-1.5 animate-pulse rounded-full bg-sky-500" />}
      {STATUS_LABELS[status]}
    </span>
  );
}
