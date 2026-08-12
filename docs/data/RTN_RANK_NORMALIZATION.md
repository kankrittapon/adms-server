# Royal Thai Navy Rank Normalization

**PromptID:** `ADMS-Data-HumanDeviceMapping-003`
**Status:** IMPLEMENTED — reference layer `app/rtn_ranks.py` (+ tests)
**Scope:** canonical rank metadata only. Rank is NEVER an identity-matching
authority for Human ↔ Device mapping.

---

## 1. Purpose

The ADMS Human Master stores the Royal Thai Navy rank as the standard Thai
administrative abbreviation (e.g. `พ.จ.ต.`, `พลฯ`, `ว่าที่ น.ต.`) in
`human_employees.rank`. This document defines the canonical, source-backed
interpretation of those values and the production inclusion/exclusion policy.

Design decisions:

- The **original source rank text is preserved** and never rewritten.
- Canonical metadata (full Thai name, English name, English abbreviation,
  rank class) is derived deterministically by `app/rtn_ranks.py`.
- Rank is **metadata only** — it never matches a Human to a device.
- `พลทหาร` (enlisted conscripts) are **excluded from the production Human
  Master / enrollment scope** (owner policy). Existing rows are NOT deleted;
  exclusion is enforced at the import/normalization boundary.

## 2. Sources

| ID | Source | Type | Notes |
|----|--------|------|-------|
| S1 | Thai Naval Education Department — `navedu.navy.mi.th/nco/main/mri.htm` "เครื่องหมายยศทหาร" (Military Rank Insignia) | Official RTN | Authoritative Thai rank names. Page could not be fetched directly from this environment (522); its content is cited verbatim by S2's rank templates. |
| S2 | Wikipedia — "Military ranks of the Thai armed forces" + templates "Ranks and Insignia of Non NATO Navies/OF/Thailand" and "/OR/Thailand" | Secondary (cites S1) | Cross-check for Thai full names and the official English translations used by the Royal Thai Navy. |
| S3 | Thai Ministry of Defence / RTARF translation standards; Thai MFA consular military-rank glossary | Official translation references | `พลทหาร` = Private (standard abbreviation `พลฯ`); `ว่าที่` = Acting. |

Confidence: Thai full names HIGH (S1 via S2); English translations HIGH
(official RTN anglicised versions); English abbreviations MEDIUM-HIGH
(standard naval abbreviations; marked as ADMS canonical, not NATO).

## 3. Canonical Rank Table

### Commissioned officers — นายทหารสัญญาบัตร (INCLUDED)

| Thai full | Thai abbr | English full | English abbr | Source |
|-----------|-----------|--------------|--------------|--------|
| พลเรือเอก | พล.ร.อ. | Admiral | Adm | S1/S2 |
| พลเรือโท | พล.ร.ท. | Vice Admiral | VAdm | S1/S2 |
| พลเรือตรี | พล.ร.ต. | Rear Admiral | RAdm | S1/S2 |
| นาวาเอก | น.อ. | Captain | Capt | S1/S2 |
| นาวาโท | น.ท. | Commander | Cdr | S1/S2 |
| นาวาตรี | น.ต. | Lieutenant Commander | Lt Cdr | S1/S2 |
| เรือเอก | ร.อ. | Lieutenant | Lt | S1/S2 |
| เรือโท | ร.ท. | Lieutenant Junior Grade | Lt JG | S1/S2 |
| เรือตรี | ร.ต. | Sub Lieutenant | Sub Lt | S1/S2 |

> **Navy distinction:** in the Navy, `ร.อ.` = เรือเอก (Lieutenant), NOT the
> Army ร้อยเอก (Captain); `น.ต.` = นาวาตรี (Lieutenant Commander), NOT the
> Army พันตรี (Major). English abbreviations above are ADMS canonical values,
> not NATO equivalence.

### Non-commissioned officers — นายทหารประทวน (INCLUDED)

| Thai full | Thai abbr | English full | English abbr | Source |
|-----------|-----------|--------------|--------------|--------|
| พันจ่าเอก | พ.จ.อ. | Chief Petty Officer 1st Class | CPO1 | S1/S2 |
| พันจ่าโท | พ.จ.ท. | Chief Petty Officer 2nd Class | CPO2 | S1/S2 |
| พันจ่าตรี | พ.จ.ต. | Chief Petty Officer 3rd Class | CPO3 | S1/S2 |
| จ่าเอก | จ.อ. | Petty Officer 1st Class | PO1 | S1/S2 |
| จ่าโท | จ.ท. | Petty Officer 2nd Class | PO2 | S1/S2 |
| จ่าตรี | จ.ต. | Petty Officer 3rd Class | PO3 | S1/S2 |

### Enlisted — พลทหาร (EXCLUDED from production scope)

| Thai full | Thai abbr | English full | English abbr | Source |
|-----------|-----------|--------------|--------------|--------|
| พลทหาร | พลฯ | Private (Seaman) | Pvt | S2/S3 |

### Acting (ว่าที่) forms

The `ว่าที่` prefix is issued by the Minister of Defence for commissioned ranks
pending the royal decree conferring the permanent rank (regulatory basis:
Military Rank Act / MoD regulations). ADMS normalizes it as `acting=true` and
prefixes the English name, e.g. `ว่าที่ น.ต.` → **Acting Lieutenant Commander**
(`Act Lt Cdr`).

## 4. Production Inclusion / Exclusion Policy

| Population | Policy |
|------------|--------|
| Royal Thai Navy commissioned officers (นายทหารสัญญาบัตร) | **INCLUDED** |
| RTN NCO / petty officers represented by the approved Human Master (นายทหารประทวน) | **INCLUDED** |
| พลทหาร (enlisted conscripts) | **EXCLUDED FROM PRODUCTION HUMAN MASTER / ENROLLMENT SCOPE** |

Deterministic predicate: `app.rtn_ranks.is_plothan()` matches the variants
`พลฯ`, `พลทหาร`, `พลทหารกองประจำการ`, `พล.ทหาร`.

### Current Human Master audit (LIVE, 2026-08-12)

| Rank value | Count | Category |
|------------|-------|----------|
| พ.จ.อ. | 52 | NCO (พันจ่า) |
| พลฯ | **36** | **ENLISTED (พลทหาร) — EXCLUDED** |
| พ.จ.ต. | 8 | NCO (พันจ่า) |
| ว่าที่ ร.ต. | 7 | Officer |
| จ.อ. | 6 | NCO (จ่า) |
| พ.จ.ท. | 3 | NCO (พันจ่า) |
| ว่าที่ น.ต. | 2 | Officer |
| ร.อ. | 2 | Officer |
| ร.ท. | 2 | Officer |
| น.ท. | 1 | Officer |
| น.ต. | 1 | Officer |
| **Total** | **120** | |

Category totals: นายทหาร 20 · พันจ่า 58 · จ่า 6 · พลทหาร **36**.

**Findings:** the current Human Master contains **36 พลทหาร records** (rank
`พลฯ`, category `พลทหาร`).

**Action taken:** those rows are **NOT deleted**. The exclusion is enforced
at the import/normalization boundary (`--exclude-plothan` flag on
`app/import_excel_human_master.py`; `filter_excluded_records()`) and via a
reversible **production-scope flag** (migration `sql/007_plothan_production_scope.sql`,
`ADMS-Data-PlothanProductionExclusion-001`): the **36 พลทหาร records are now
flagged `production_scope=false`** while their UUIDs, provenance, and history
are fully preserved. `reserve_next_device_user_id()` additionally requires
`production_scope = true`, excluding พลทหาร from future production
enrollment. Rollback: `UPDATE human_employees SET production_scope = true
WHERE category = 'พลทหาร';`.

## 5. Implementation

- `app/rtn_ranks.py` — canonical catalog + `normalize_rtn_rank()`,
  `is_plothan()`, `classify_rank()`, `production_scope_allowed()`.
- `app/import_excel_human_master.py` — `filter_excluded_records()` +
  `--exclude-plothan` (backward compatible; default OFF).
- `sql/007_plothan_production_scope.sql` — additive `production_scope` flag
  + deterministic flip of the 36 พลทหาร records (reversible, idempotent).
- `app/enrollment.py` — `reserve_next_device_user_id()` requires
  `production_scope = true` (future-enrollment enforcement).
- `tests/test_rtn_rank_normalization.py` — catalog integrity, normalization,
  acting forms, exclusion predicate (24 tests).

**Rank is never an identity-matching authority.** The first VERIFIED mapping
(ADMS-Data-HumanDeviceMapping-003) was created solely from pilot evidence
(owner-confirmed Human + reserved account 1001 + physical fingerprint
enrollment + controlled scan id 12 + explicit owner confirmation).
