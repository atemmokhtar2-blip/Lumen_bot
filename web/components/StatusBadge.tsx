import type { JobStatus } from "@/lib/api";

const MAP: Record<string, string> = {
  queued: "badge-queued",
  running: "badge-running",
  paused: "badge-paused",
  succeeded: "badge-succeeded",
  failed: "badge-failed",
  cancelled: "badge-cancelled",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const cls = MAP[String(status)] || "badge-queued";
  return <span className={`badge ${cls}`}>{status}</span>;
}
