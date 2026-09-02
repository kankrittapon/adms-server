import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { useTranslation } from "../i18n";
import { friendlyApiError } from "../i18n/apiErrors";
import { computeTerminalNamePreview } from "../lib/terminalName";
import type { Human, RankReference } from "../api/types";
import { RankSelect } from "./RankSelect";
import { useApi } from "../hooks/useApi";

interface Props {
  mode: "create" | "edit";
  human?: Human;
  onClose: () => void;
  onSaved: (human: Human) => void;
}

/**
 * ADMS-Personnel-MasterData-024: single form for both เพิ่มกำลังพล (create)
 * and แก้ไขข้อมูล (edit) — same fields, same validation, same terminal-name
 * preview logic, so the two flows can never silently drift apart.
 */
export function PersonnelFormModal({ mode, human, onClose, onSaved }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { canManagePersonnel } = useAuth();
  const ranks = useApi((s) => api.ranks(s), []);

  const [displayName, setDisplayName] = useState(human?.display_name ?? "");
  const [rank, setRank] = useState(human?.rank ?? "");
  const [englishName, setEnglishName] = useState(human?.english_name ?? "");
  const [personnelId, setPersonnelId] = useState(human?.personnel_id ?? "");
  const [branch, setBranch] = useState(human?.branch ?? "");
  const [category, setCategory] = useState(human?.category ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<Human | null>(null);

  if (!canManagePersonnel) return null;

  const rankMeta: RankReference | undefined = (ranks.data ?? []).find((r) => r.rank_th_abbreviation === rank);
  const namePreview = computeTerminalNamePreview(
    englishName,
    rankMeta
      ? {
          rank_th_original: rankMeta.rank_th_abbreviation,
          rank_en: rankMeta.rank_en,
          rank_en_abbreviation: rankMeta.rank_en_abbreviation,
        }
      : null
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!displayName.trim()) {
      setError(t.personnel.displayNameRequired);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (mode === "create") {
        const created = await api.createHuman({
          display_name: displayName.trim(),
          rank: rank || undefined,
          english_name: englishName.trim() || undefined,
          personnel_id: personnelId.trim() || undefined,
          branch: branch.trim() || undefined,
          category: category.trim() || undefined,
        });
        setJustCreated(created);
        onSaved(created);
      } else if (human) {
        const updated = await api.updateHuman(human.employee_id, {
          display_name: displayName.trim(),
          rank: rank || null,
          english_name: englishName.trim() || null,
          personnel_id: personnelId.trim() || null,
          branch: branch.trim() || null,
          category: category.trim() || null,
        });
        onSaved(updated);
        onClose();
      }
    } catch (err) {
      if (err instanceof ApiClientError && err.code === "PERSONNEL_DUPLICATE") {
        setError(t.personnel.duplicatePersonnelIdBody);
      } else if (
        err instanceof ApiClientError &&
        (err.code === "WRITE_DISABLED" || err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_SESSION_EXPIRED")
      ) {
        setError(t.personnel.writesDisabledNotice);
      } else {
        setError(friendlyApiError(err, t));
      }
    } finally {
      setBusy(false);
    }
  }

  // Success state after create — offer the Enrollment handoff, never
  // auto-start it (Phase 13).
  if (justCreated) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
          <div className="text-sm font-bold text-emerald-800">✓ {t.personnel.createSuccessTitle}</div>
          <p className="mt-2 text-xs text-slate-600">{justCreated.display_name}</p>
          <div className="mt-5 flex flex-col gap-2">
            <button
              onClick={() => navigate("/enrollments")}
              className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700"
            >
              {t.personnel.goToEnrollmentButton}
            </button>
            <button
              onClick={onClose}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              {t.common.close}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <form onSubmit={submit} className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl space-y-4">
        <div className="text-sm font-bold text-slate-900">
          {mode === "create" ? t.personnel.addPersonnelTitle : t.personnel.editPersonnelTitle}
        </div>

        {error && (
          <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-xs text-rose-800">{error}</div>
        )}

        <div>
          <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
            {t.personnel.thaiFullNameLabel}
          </label>
          <input
            type="text"
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              {t.personnel.rank}
            </label>
            <RankSelect value={rank} onChange={setRank} disabled={busy} />
          </div>
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              {t.personnel.personnelIdLabel}
            </label>
            <input
              type="text"
              value={personnelId}
              onChange={(e) => setPersonnelId(e.target.value)}
              disabled={busy}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          </div>
        </div>

        <div>
          <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
            {t.personnel.englishName}
          </label>
          <input
            type="text"
            value={englishName}
            onChange={(e) => setEnglishName(e.target.value)}
            disabled={busy}
            className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              {t.personnel.branch}
            </label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              disabled={busy}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          </div>
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              {t.personnel.category}
            </label>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              disabled={busy}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          </div>
        </div>

        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            {t.enrollment.terminalDisplayName}
          </div>
          {englishName.trim() ? (
            <div className="mt-1 font-mono text-sm font-bold text-slate-800">{namePreview.value}</div>
          ) : (
            <div className="mt-1 text-xs text-amber-700">{t.personnel.englishNameRequiredForTerminalHint}</div>
          )}
          {namePreview.rankOmittedForLength && (
            <div className="mt-1 text-[11px] text-amber-700">{t.enrollment.terminalNameRankOmittedHint}</div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            {t.common.cancel}
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? t.common.saving : t.common.save}
          </button>
        </div>
      </form>
    </div>
  );
}
