import { ApiClientError } from "../api/client";
import type { Translations } from "./types";

/**
 * ADMS-FrontendUX-ConsistencySweep-026: single place to turn an API error
 * into operator-facing copy. Several pages (System, Mappings, Enrollments)
 * previously fell back to `${err.code}: ${err.message}` — a raw backend
 * string shown directly to an elderly, non-technical operator. Callers
 * that already have a more specific mapping (e.g. Enrollments' per-action
 * ENROLLMENT_CONFLICT sub-cases) should keep their own logic and only use
 * this as the final fallback, so specificity is never lost.
 */
export function friendlyApiError(err: unknown, t: Translations): string {
  if (err instanceof ApiClientError) {
    switch (err.code) {
      case "WRITE_DISABLED":
      case "WRITE_SESSION_REQUIRED":
        return t.enrollment.writeSessionLockedBody;
      case "WRITE_SESSION_EXPIRED":
        return t.enrollment.writeSessionExpiredMidWorkflow;
      case "VALIDATION_ERROR":
        return t.common.apiErrors.validationError;
      case "NOT_FOUND":
        return t.common.apiErrors.notFound;
      case "RATE_LIMITED":
        return t.common.apiErrors.rateLimited;
      case "UNAUTHORIZED":
        return t.common.unauthorized;
      case "FORBIDDEN":
        return t.common.forbidden;
      case "INTERNAL_ERROR":
        return t.common.apiErrors.internalError;
      default:
        // Unmapped code: never show err.message (may echo raw backend/SQL
        // text) — generic copy only, code kept out of the string shown to
        // an elderly operator.
        return t.common.apiErrors.genericErrorPrefix;
    }
  }
  return t.common.apiErrors.internalError;
}
