import type { ReactNode } from "react";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    green: "bg-green-100 text-green-800",
    red: "bg-red-100 text-red-800",
    amber: "bg-amber-100 text-amber-800",
    blue: "bg-blue-100 text-blue-800",
    neutral: "bg-gray-100 text-gray-700",
  };
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${tones[tone] ?? tones.neutral}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const s = status?.toUpperCase();
  if (s === "ON_TIME" || s === "VERIFIED" || s === "HEALTHY" || s === "LIVE") return <Badge tone="green">{status}</Badge>;
  if (s === "LATE" || s === "UNKNOWN" || s === "UNHEALTHY" || s === "FAIL") return <Badge tone="amber">{status}</Badge>;
  if (s === "CANCELLED" || s === "RETIRED" || s === "REVOKED" || s === "INACTIVE") return <Badge tone="neutral">{status}</Badge>;
  if (s?.includes("PENDING") || s?.includes("RESERVED")) return <Badge tone="blue">{status}</Badge>;
  return <Badge tone="neutral">{status ?? "—"}</Badge>;
}

export function ScopeBadge({ scope }: { scope: boolean }) {
  return scope ? <Badge tone="green">production</Badge> : <Badge tone="neutral">excluded</Badge>;
}

export function Loading() {
  return <div className="py-8 text-center text-sm text-gray-500">Loading…</div>;
}

export function ErrorBanner({ message }: { message: string }) {
  return <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">Error: {message}</div>;
}

export function StatCard({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-gray-900">{value}</div>
      {hint ? <div className="mt-0.5 text-xs text-gray-500">{hint}</div> : null}
    </div>
  );
}
