"""
Royal Thai Navy rank normalization catalog.

PromptID: ADMS-Data-HumanDeviceMapping-003

Provides a deterministic canonical mapping for Royal Thai Navy ranks as they
appear in the ADMS Human Master (the ``rank`` column stores the standard Thai
administrative abbreviation, e.g. ``พ.จ.ต.``, ``พลฯ``, ``ว่าที่ น.ต.``).

Design principles
-----------------
- The original source rank text is NEVER rewritten. This module only derives
  canonical metadata (full Thai name, English name, English abbreviation,
  rank class) from the stored value.
- Rank is metadata ONLY. It is NEVER an identity-matching authority for
  Human <-> Device mapping.
- A deterministic exclusion predicate classifies พลทหาร (enlisted conscripts)
  records for the production Human Master / enrollment scope policy.
  Existing rows are NEVER deleted by this module.

Sources (full evidence table in docs/data/RTN_RANK_NORMALIZATION.md)
--------------------------------------------------------------------
S1  Thai Naval Education Department (navedu.navy.mi.th) - official RTN rank
    insignia page "เครื่องหมายยศทหาร" (cited by Wikipedia rank templates
    "Ranks and Insignia of Non NATO Navies/OF(OR)/Thailand").
S2  Wikipedia "Military ranks of the Thai armed forces" - Thai full names and
    official English translations (cross-checked against S1).
S3  Thai Ministry of Defence / RTARF translation standards and the Thai
    Ministry of Foreign Affairs consular military-rank glossary: พลทหาร =
    Private (standard Thai abbreviation พลฯ); ว่าที่ = Acting.
"""

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Canonical RTN rank catalog
# ---------------------------------------------------------------------------
# Keyed by the canonical Thai abbreviation (the form stored in the Human
# Master). ``category`` uses the official Thai rank classes:
#   OFFICER  -> นายทหารสัญญาบัตร (commissioned officer)
#   NCO      -> นายทหารประทวน (non-commissioned / petty officer)
#   ENLISTED -> พลทหาร (enlisted conscript - EXCLUDED from production scope)
# English translations follow official RTN usage (naval designations).

RTN_RANK_CATALOG: Dict[str, Dict[str, str]] = {
    # --- Commissioned officers (นายทหารสัญญาบัตร) ---
    "พล.ร.อ.": {
        "rank_th_full": "พลเรือเอก",
        "rank_th_abbreviation": "พล.ร.อ.",
        "rank_en": "Admiral",
        "rank_en_abbreviation": "Adm",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    "พล.ร.ท.": {
        "rank_th_full": "พลเรือโท",
        "rank_th_abbreviation": "พล.ร.ท.",
        "rank_en": "Vice Admiral",
        "rank_en_abbreviation": "VAdm",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    "พล.ร.ต.": {
        "rank_th_full": "พลเรือตรี",
        "rank_th_abbreviation": "พล.ร.ต.",
        "rank_en": "Rear Admiral",
        "rank_en_abbreviation": "RAdm",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    "น.อ.": {
        "rank_th_full": "นาวาเอก",
        "rank_th_abbreviation": "น.อ.",
        "rank_en": "Captain",
        "rank_en_abbreviation": "Capt",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    "น.ท.": {
        "rank_th_full": "นาวาโท",
        "rank_th_abbreviation": "น.ท.",
        "rank_en": "Commander",
        "rank_en_abbreviation": "Cdr",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    "น.ต.": {
        "rank_th_full": "นาวาตรี",
        "rank_th_abbreviation": "น.ต.",
        "rank_en": "Lieutenant Commander",
        "rank_en_abbreviation": "Lt Cdr",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    "ร.อ.": {
        "rank_th_full": "เรือเอก",
        "rank_th_abbreviation": "ร.อ.",
        "rank_en": "Lieutenant",
        "rank_en_abbreviation": "Lt",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    "ร.ท.": {
        "rank_th_full": "เรือโท",
        "rank_th_abbreviation": "ร.ท.",
        "rank_en": "Lieutenant Junior Grade",
        "rank_en_abbreviation": "Lt JG",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    "ร.ต.": {
        "rank_th_full": "เรือตรี",
        "rank_th_abbreviation": "ร.ต.",
        "rank_en": "Sub Lieutenant",
        "rank_en_abbreviation": "Sub Lt",
        "rank_category": "OFFICER",
        "source": "S1/S2",
    },
    # --- Non-commissioned officers (นายทหารประทวน) ---
    "พ.จ.อ.": {
        "rank_th_full": "พันจ่าเอก",
        "rank_th_abbreviation": "พ.จ.อ.",
        "rank_en": "Chief Petty Officer 1st Class",
        "rank_en_abbreviation": "CPO1",
        "rank_category": "NCO",
        "source": "S1/S2",
    },
    "พ.จ.ท.": {
        "rank_th_full": "พันจ่าโท",
        "rank_th_abbreviation": "พ.จ.ท.",
        "rank_en": "Chief Petty Officer 2nd Class",
        "rank_en_abbreviation": "CPO2",
        "rank_category": "NCO",
        "source": "S1/S2",
    },
    "พ.จ.ต.": {
        "rank_th_full": "พันจ่าตรี",
        "rank_th_abbreviation": "พ.จ.ต.",
        "rank_en": "Chief Petty Officer 3rd Class",
        "rank_en_abbreviation": "CPO3",
        "rank_category": "NCO",
        "source": "S1/S2",
    },
    "จ.อ.": {
        "rank_th_full": "จ่าเอก",
        "rank_th_abbreviation": "จ.อ.",
        "rank_en": "Petty Officer 1st Class",
        "rank_en_abbreviation": "PO1",
        "rank_category": "NCO",
        "source": "S1/S2",
    },
    "จ.ท.": {
        "rank_th_full": "จ่าโท",
        "rank_th_abbreviation": "จ.ท.",
        "rank_en": "Petty Officer 2nd Class",
        "rank_en_abbreviation": "PO2",
        "rank_category": "NCO",
        "source": "S1/S2",
    },
    "จ.ต.": {
        "rank_th_full": "จ่าตรี",
        "rank_th_abbreviation": "จ.ต.",
        "rank_en": "Petty Officer 3rd Class",
        "rank_en_abbreviation": "PO3",
        "rank_category": "NCO",
        "source": "S1/S2",
    },
    # --- Enlisted (พลทหาร) ---
    # EXCLUDED from the production Human Master / enrollment scope by owner
    # policy (Section D of ADMS-Data-HumanDeviceMapping-003). The catalog
    # entry exists so normalization is complete and deterministic.
    "พลฯ": {
        "rank_th_full": "พลทหาร",
        "rank_th_abbreviation": "พลฯ",
        "rank_en": "Private (Seaman)",
        "rank_en_abbreviation": "Pvt",
        "rank_category": "ENLISTED",
        "source": "S2/S3",
    },
}

# Full Thai rank names -> canonical abbreviation (accepts both forms in input).
_RANK_FULL_TO_ABBR: Dict[str, str] = {
    entry["rank_th_full"]: abbr for abbr, entry in RTN_RANK_CATALOG.items()
}

# Variants of the พลทหาร rank that must be excluded deterministically.
_PLOTHAN_VARIANTS = ("พลฯ", "พลทหาร", "พลทหารกองประจำการ", "พล.ทหาร")

ACTING_PREFIX_TH = "ว่าที่"
ACTING_PREFIX_EN = "Acting"

CATEGORY_LABELS: Dict[str, str] = {
    "OFFICER": "นายทหารสัญญาบัตร (commissioned officer)",
    "NCO": "นายทหารประทวน (NCO / petty officer)",
    "ENLISTED": "พลทหาร (enlisted conscript) — EXCLUDED FROM PRODUCTION SCOPE",
    "UNKNOWN": "UNKNOWN",
}

# Rank classes represented in the production Human Master inclusion scope.
INCLUDED_CATEGORIES = ("OFFICER", "NCO")


def _clean(rank_text: str) -> str:
    """Normalizes whitespace on a raw rank value ('' for empty/None)."""
    if not rank_text:
        return ""
    return " ".join(str(rank_text).split())


def is_plothan(rank_text: str) -> bool:
    """
    Deterministic exclusion predicate for พลทหาร (enlisted conscripts).

    Owner policy: พลทหาร are NOT part of the production ADMS Human Master /
    enrollment population. Returns True for any stored rank value that is the
    พลทหาร rank (abbreviation or full form). Existing records are never
    deleted by callers of this predicate; it only classifies.
    """
    cleaned = _clean(rank_text)
    if not cleaned:
        return False
    return cleaned in _PLOTHAN_VARIANTS


def normalize_rtn_rank(rank_text: str) -> Optional[Dict[str, str]]:
    """
    Returns canonical rank metadata for a Human Master rank value, or None if
    the value cannot be matched to the canonical catalog.

    Accepts the standard Thai abbreviation (e.g. ``พ.จ.ต.``) and the full Thai
    name (e.g. ``พันจ่าตรี``). The ``ว่าที่`` (acting) prefix is preserved as an
    ``acting`` flag and an ``Acting ...`` English form. The original input is
    returned untouched as ``rank_th_original``.
    """
    cleaned = _clean(rank_text)
    if not cleaned:
        return None

    acting = False
    base = cleaned
    if cleaned.startswith(ACTING_PREFIX_TH):
        acting = True
        base = _clean(cleaned[len(ACTING_PREFIX_TH):])

    abbr = base
    if base not in RTN_RANK_CATALOG and base in _RANK_FULL_TO_ABBR:
        abbr = _RANK_FULL_TO_ABBR[base]
    entry = RTN_RANK_CATALOG.get(abbr)
    if entry is None:
        return None

    result = dict(entry)
    result["rank_th_original"] = cleaned
    if acting:
        result["acting"] = "true"
        result["rank_en"] = "%s %s" % (ACTING_PREFIX_EN, entry["rank_en"])
        result["rank_en_abbreviation"] = "Act " + entry["rank_en_abbreviation"]
    else:
        result["acting"] = "false"
    return result


def classify_rank(rank_text: str) -> str:
    """
    Returns the rank class for a Human Master rank value:
    OFFICER / NCO / ENLISTED / UNKNOWN. Metadata only; never identity.
    """
    entry = normalize_rtn_rank(rank_text)
    if entry is None:
        return "UNKNOWN"
    return entry["rank_category"]


def production_scope_allowed(rank_text: str) -> bool:
    """
    Returns True when a Human Master record is within the production
    enrollment scope. The rank column (if populated) is used as supporting
    metadata; the authoritative inclusion scope is defined by the owner
    policy. พลทหาร records are excluded deterministically.
    """
    cleaned = _clean(rank_text)
    if not cleaned:
        # Empty rank is not, by itself, exclusion evidence.
        return True
    return not is_plothan(cleaned)


def all_canonical_ranks() -> List[Dict[str, str]]:
    """Returns the full canonical catalog as a list (for docs/reporting)."""
    return [
        dict(RTN_RANK_CATALOG[abbr], rank_th_abbreviation=abbr)
        for abbr in RTN_RANK_CATALOG
    ]
