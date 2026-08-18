import { useApi } from "../hooks/useApi";
import { api } from "../api/client";
import { useTranslation } from "../i18n";

/**
 * ADMS-Personnel-MasterData-024: the ONE canonical rank dropdown. Always
 * fetches from GET /api/v1/reference/ranks (backed by app/rtn_ranks.py) —
 * never a hardcoded frontend rank list. The stored/selected value is the
 * canonical Thai abbreviation (e.g. "พ.จ.อ."), the exact identifier the
 * backend validates against and derives the English abbreviation from.
 */
export function RankSelect({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (rank: string) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const ranks = useApi((s) => api.ranks(s), []);

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled || ranks.loading}
      className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
    >
      <option value="">{t.personnel.selectRankPlaceholder}</option>
      {(ranks.data ?? []).map((r) => (
        <option key={r.rank_th_abbreviation} value={r.rank_th_abbreviation}>
          {r.rank_th_full} ({r.rank_th_abbreviation})
        </option>
      ))}
    </select>
  );
}
