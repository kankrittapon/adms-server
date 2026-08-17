-- SQL Migration 010: Add ENROLLMENT_OPERATOR Role
-- PromptID: ADMS-Frontend-I18n-RBAC-Personnel-004
-- Description: Update operators and api_tokens check constraints to include ENROLLMENT_OPERATOR role.

BEGIN;

ALTER TABLE operators DROP CONSTRAINT IF EXISTS operators_role_check;
ALTER TABLE operators ADD CONSTRAINT operators_role_check 
  CHECK (role IN ('VIEWER', 'ENROLLMENT_OPERATOR', 'OPERATOR', 'ADMIN'));

ALTER TABLE api_tokens DROP CONSTRAINT IF EXISTS api_tokens_role_check;
ALTER TABLE api_tokens ADD CONSTRAINT api_tokens_role_check 
  CHECK (role IN ('VIEWER', 'ENROLLMENT_OPERATOR', 'OPERATOR', 'ADMIN'));

COMMIT;
