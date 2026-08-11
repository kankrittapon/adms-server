-- SQL Migration 003: Legacy Identity Constraint Removal
-- PromptID: ADMS-Data-LegacyIdentityConstraint-002
-- Description: Drop obsolete foreign key constraint coupling raw attendance user_id to legacy employees table

ALTER TABLE attendance_logs DROP CONSTRAINT attendance_logs_user_id_fkey;
