import type { RankMetadata } from "../api/types";

/**
 * Terminal display-name preview (ADMS-OperatorUX-Fingerprint-Rank-Mapping-016).
 *
 * The terminal display name is presentation on the physical ZEM560, not
 * Human identity authority — the canonical name always stays
 * human_employees.english_name, untouched. This only computes a *default,
 * still-editable* suggestion of `rank_en_abbreviation + english_name`, so
 * an elderly/non-technical ADMIN doesn't have to type rank abbreviations
 * by hand.
 *
 * Deterministic length rule: MAX_TERMINAL_NAME_LENGTH (20, matching
 * app/enrollment.py's server-side ASCII-guard limit — see
 * validate_terminal_display_name) is never silently truncated mid-name,
 * which could produce an ambiguous/misleading identity on the device.
 * Instead: if "RANK NAME" would exceed the limit, the rank prefix is
 * dropped entirely and the plain english_name is used (still validated,
 * still fits) — never a half-cut name. The caller should show *why* the
 * rank was dropped if that happened, via `truncatedRank`.
 */

export const MAX_TERMINAL_NAME_LENGTH = 20;

export interface TerminalNamePreview {
  /** The suggested display name for the terminal — never silently cut. */
  value: string;
  /** True when a canonical rank prefix existed but had to be dropped to fit. */
  rankOmittedForLength: boolean;
}

export function computeTerminalNamePreview(
  englishName: string | null | undefined,
  rankMetadata: RankMetadata | null | undefined
): TerminalNamePreview {
  const name = (englishName ?? "").trim();
  if (!name) {
    return { value: "", rankOmittedForLength: false };
  }
  const abbr = rankMetadata?.rank_en_abbreviation?.trim();
  if (!abbr) {
    return { value: name, rankOmittedForLength: false };
  }
  const withRank = `${abbr} ${name}`;
  if (withRank.length <= MAX_TERMINAL_NAME_LENGTH) {
    return { value: withRank, rankOmittedForLength: false };
  }
  // Full canonical name always wins over a truncated/ambiguous rank+name
  // combination — the rank is metadata, not identity.
  return { value: name, rankOmittedForLength: true };
}
