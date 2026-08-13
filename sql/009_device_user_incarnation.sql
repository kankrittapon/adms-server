-- SQL Migration 009: Device User Account Incarnation Tracking
-- PromptID: ADMS-Data-DeviceUserLifecycleHardening-001
-- Description: Additive, reversible schema change adding account_incarnation to
--              device_users. Tracks how many times a terminal account
--              (device_id, device_user_id) has been (re)created, so that
--              account reuse after disappearance is explicit and auditable.
--
--              Identity safety is NOT stored here — it remains in the temporal
--              [valid_from, valid_to) employee_device_mappings model. On a
--              confirmed disappearance, any open VERIFIED mapping is closed at
--              the lifecycle boundary (app/db.py reconcile_roster_lifecycle),
--              and a reappearance increments account_incarnation without
--              reopening or inheriting the previous mapping.
--
--              Reversible: DROP COLUMN restores the previous schema (no data
--              loss — column is derived lifecycle metadata only).

BEGIN;

ALTER TABLE device_users
  ADD COLUMN IF NOT EXISTS account_incarnation INTEGER NOT NULL DEFAULT 1;

COMMIT;
