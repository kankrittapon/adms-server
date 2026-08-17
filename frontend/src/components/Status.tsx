import type { ReactNode } from "react";

export type BadgeTone = "green" | "red" | "amber" | "blue" | "indigo" | "purple" | "neutral";

export function Badge({
  children,
  tone = "neutral",
  size = "md",
}: {
  children: ReactNode;
  tone?: BadgeTone;
  size?: "sm" | "md";
}) {
  const tones: Record<BadgeTone, string> = {
    green: "bg-emerald-50 text-emerald-700 border-emerald-200",
    red: "bg-rose-50 text-rose-700 border-rose-200",
    amber: "bg-amber-50 text-amber-800 border-amber-300",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-200",
    purple: "bg-purple-50 text-purple-700 border-purple-200",
    neutral: "bg-slate-100 text-slate-700 border-slate-200",
  };

  const sizes = {
    sm: "px-1.5 py-0.2 text-[10px]",
    md: "px-2 py-0.5 text-xs",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 font-semibold rounded border ${sizes[size]} ${
        tones[tone] ?? tones.neutral
      }`}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const s = status?.toUpperCase() ?? "";
  if (s === "ON_TIME" || s === "VERIFIED" || s === "HEALTHY" || s === "LIVE" || s === "ACTIVE") {
    return (
      <Badge tone="green">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        {status}
      </Badge>
    );
  }
  if (s === "LATE" || s === "UNKNOWN" || s === "UNHEALTHY" || s === "FAIL") {
    return (
      <Badge tone="amber">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
        {status}
      </Badge>
    );
  }
  if (s === "CANCELLED" || s === "RETIRED" || s === "REVOKED" || s === "INACTIVE") {
    return <Badge tone="neutral">{status}</Badge>;
  }
  if (s.includes("PENDING") || s.includes("RESERVED")) {
    return (
      <Badge tone="blue">
        <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
        {status}
      </Badge>
    );
  }
  if (s === "READY_FOR_MAPPING") {
    return (
      <Badge tone="purple">
        <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
        {status}
      </Badge>
    );
  }
  return <Badge tone="neutral">{status || "—"}</Badge>;
}

export function ScopeBadge({ scope }: { scope: boolean }) {
  return scope ? (
    <Badge tone="green" size="sm">
      production
    </Badge>
  ) : (
    <Badge tone="neutral" size="sm">
      excluded
    </Badge>
  );
}

export function WriteGateStatusBadge({ writeEnabled }: { writeEnabled: boolean }) {
  if (writeEnabled) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md border border-amber-400 bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-900 shadow-2xs">
        <span className="h-2 w-2 rounded-full bg-amber-600 animate-ping" />
        ⚠️ WRITES ACTIVE (MUTATION ENABLED)
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs">
      <span className="h-2 w-2 rounded-full bg-slate-500" />
      🔒 WRITES LOCKED (READ-ONLY SAFE)
    </span>
  );
}

export function Loading() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-slate-500">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
      <span className="mt-2 text-xs font-medium">Loading telemetry...</span>
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-rose-200 bg-rose-50/90 p-3.5 text-xs text-rose-900 shadow-2xs">
      <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-rose-200 font-bold text-rose-800 text-[11px]">
        !
      </div>
      <div>
        <div className="font-bold">System Error</div>
        <div className="mt-0.5 leading-relaxed text-rose-800">{message}</div>
      </div>
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "normal" | "highlight";
}) {
  return (
    <div
      className={`rounded-lg border bg-white p-4 shadow-2xs transition-all ${
        tone === "highlight" ? "border-blue-300 ring-1 ring-blue-100" : "border-slate-200 hover:border-slate-300"
      }`}
    >
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-bold tracking-tight text-slate-900">{value}</div>
      {hint ? <div className="mt-1 text-[11px] text-slate-500 leading-tight">{hint}</div> : null}
    </div>
  );
}
