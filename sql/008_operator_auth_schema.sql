-- SQL Migration 008: Operator Auth & Role Tokens
-- PromptID: ADMS-Frontend-F5-Auth-001
-- Description: Additive, reversible F5 authentication schema.
--
--   operators   : named operator accounts (VIEWER / OPERATOR / ADMIN) with
--                 PBKDF2-SHA256 password hashes. No plaintext passwords.
--   api_tokens  : opaque Bearer tokens, stored ONLY as SHA-256 hashes.
--                 Tokens carry a role snapshot and an expiry; revocation is
--                 reversible (revoked_at, never DELETE).
--
-- Safety:
--   - Additive only. No existing table is altered.
--   - Passwords and tokens are never stored in plaintext.
--   - Token revocation keeps the row (audit trail) — revoke is reversible
--     by clearing revoked_at, but operators must rotate the secret anyway.
--   - Strict posture: the API rejects requests without a valid token
--     (401) unless the operator is granted the required role (403).
--   - Bootstrap: the first ADMIN account is created via a CLI
--     (`python -m app.api.bootstrap_admin`) — never auto-created from env.

BEGIN;

CREATE TABLE IF NOT EXISTS operators (
  operator_id   BIGSERIAL PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('VIEWER', 'OPERATOR', 'ADMIN')),
  password_hash TEXT NOT NULL,
  active        BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_tokens (
  token_id     BIGSERIAL PRIMARY KEY,
  operator_id  BIGINT NOT NULL REFERENCES operators(operator_id) ON DELETE CASCADE,
  token_hash   TEXT NOT NULL UNIQUE,
  role         TEXT NOT NULL CHECK (role IN ('VIEWER', 'OPERATOR', 'ADMIN')),
  issued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  revoked_at   TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_hash
  ON api_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_api_tokens_operator_active
  ON api_tokens (operator_id, revoked_at);

COMMIT;
