import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import type { Human } from "../api/types";

interface Props {
  humans: Human[] | undefined;
  value: string;
  onChange: (employeeId: string) => void;
  disabled?: boolean;
}

/**
 * ADMS-FrontendUX-ConsistencySweep-026 Phase 5: replaces the flat
 * <select> of every eligible Human (120+ and growing) with a type-to-
 * filter combobox — elderly Thai staff scrolling a long alphabetical list
 * to find one name was a recurring pain point. Filters on display_name,
 * english_name, rank, and personnel_id; never invents matching beyond a
 * simple case-insensitive substring search (this is a UI convenience, not
 * an identity resolver — selecting a row is still the only thing that
 * sets employeeId).
 */
export function PersonCombobox({ humans, value, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selected = (humans ?? []).find((h) => h.employee_id === value);

  // Keep the displayed text in sync when the selection changes from
  // outside this component (e.g. cleared back to "" after a successful
  // reservation) — but never fight the operator's in-progress typing.
  useEffect(() => {
    if (!open) {
      setQuery(selected ? `${selected.display_name}${selected.rank ? ` (${selected.rank})` : ""}` : "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const q = query.trim().toLowerCase();
  const filtered = (humans ?? []).filter((h) => {
    if (!q) return true;
    return (
      h.display_name.toLowerCase().includes(q) ||
      (h.english_name ?? "").toLowerCase().includes(q) ||
      (h.rank ?? "").toLowerCase().includes(q) ||
      (h.personnel_id ?? "").toLowerCase().includes(q)
    );
  });

  function select(h: Human) {
    onChange(h.employee_id);
    setQuery(`${h.display_name}${h.rank ? ` (${h.rank})` : ""}`);
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={query}
        disabled={disabled}
        placeholder={t.enrollment.searchPersonPlaceholder}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          if (value) onChange("");
        }}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100 disabled:text-slate-500"
      />
      {open && !disabled && (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-xs text-slate-400">{t.enrollment.noPersonMatchFound}</div>
          ) : (
            filtered.slice(0, 100).map((h) => (
              <button
                type="button"
                key={h.employee_id}
                onClick={() => select(h)}
                className="block w-full px-3 py-1.5 text-left text-xs text-slate-800 hover:bg-blue-50"
              >
                {h.display_name} {h.rank ? <span className="text-slate-500">({h.rank})</span> : null}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
