// ADMS API client types.
//
// PromptID: ADMS-Frontend-Codegen-001
//
// Model types are DERIVED from the FastAPI OpenAPI schema (single source of
// truth). Regenerate with `npm run codegen:api` (frontend/) after any backend
// contract change; tests/test_openapi_contract.py fails if the committed
// frontend/openapi.json snapshot is stale.
//
// Only types that do not exist in the schema (generic Page<T>, inline dict
// returns from write/transition endpoints, API error envelope) are defined
// locally here.
import type { components } from "./generated";

type Schemas = components["schemas"];

// --- Local helpers (not in the OpenAPI schema) -----------------------------

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

/** Generic pagination envelope; concrete Page_X_ types exist in the schema. */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Healthz {
  status: string;
}

/** Inline return of GET /api/v1/enrollments/{id}/next-actions. */
export interface EnrollmentNextActions {
  enrollment_id: number;
  status: string;
  next_actions: Array<{
    action: string;
    target_status: string;
    requires_role: string;
  }>;
}

/** Inline return of POST /api/v1/enrollments/reserve. */
export interface EnrollmentReserveResult {
  enrollment_id: number;
  reserved_device_user_id: string;
  status: string;
  reserved_at: string;
  employee_id: string;
  device_id: number;
}

/** Inline return of enrollment transition POSTs. */
export interface EnrollmentTransitionResult {
  enrollment_id: number;
  status: string;
}

// --- Model types derived from the OpenAPI schema ---------------------------

export type HealthCheck = Schemas["HealthCheck"];
export type CollectorSummary = Schemas["CollectorSummary"];
export type DashboardSummary = Schemas["DashboardSummary"];
export type RankMetadata = Schemas["RankMetadata"];
export type Human = Schemas["Human"];
export type Device = Schemas["Device"];
export type DeviceUser = Schemas["DeviceUser"];
export type Attendance = Schemas["Attendance"];
export type AttendanceDetail = Schemas["AttendanceDetail"];
export type AttendanceRawPayload = Schemas["AttendanceRawPayload"];
export type AttributionReasoning = Schemas["AttributionReasoning"];
export type UnattributedAttendance = Schemas["UnattributedAttendance"];
export type Mapping = Schemas["Mapping"];
export type MappingEligibilityItem = Schemas["MappingEligibilityItem"];
export type MappingEligibility = Schemas["MappingEligibility"];
export type Enrollment = Schemas["Enrollment"];
export type AuditEvent = Schemas["AuditEvent"];
export type RankReference = Schemas["RankReference"];
export type LoginResponse = Schemas["LoginResponse"];
export type MeResponse = Schemas["MeResponse"];
export type CreateMappingResult = Schemas["CreateMappingResponse"];
