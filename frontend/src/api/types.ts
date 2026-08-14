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
import type { components, operations } from "./generated";

type Schemas = components["schemas"];

/** Keys of the OpenAPI operations map (for QueryOf/BodyOf/JsonResponse). */
export type OperationsKey = keyof operations;

type Operations = operations;

// --- Operation-level derivation helpers -------------------------------------
// client.ts method signatures derive from the OpenAPI operations types, so the
// client contract cannot drift from the API: any backend change fails `tsc` at
// the call sites after `npm run codegen:api`.

/** Query parameters of an operation (undefined when the endpoint has none). */
export type QueryOf<OpId extends keyof Operations> = NonNullable<
  Operations[OpId]["parameters"]["query"]
>;

/** Request body JSON of an operation. */
export type BodyOf<OpId extends keyof Operations> = NonNullable<
  Operations[OpId]["requestBody"]
>["content"]["application/json"];

/** Successful response JSON of an operation (default status 200). */
export type JsonResponse<
  OpId extends keyof Operations,
  Status extends number = 200,
> = Status extends keyof Operations[OpId]["responses"]
  ? Operations[OpId]["responses"][Status] extends { content: { "application/json": infer T } }
    ? T
    : never
  : never;

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

// --- Model types derived from the OpenAPI schema ---------------------------

export type Healthz = Schemas["Healthz"];
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
export type EnrollmentNextActions = Schemas["EnrollmentNextActions"];
export type EnrollmentReserveResult = Schemas["EnrollmentReserveResult"];
export type EnrollmentTransitionResult = Schemas["EnrollmentTransitionResult"];
export type EventTypesResponse = Schemas["EventTypesResponse"];
export type AuditEvent = Schemas["AuditEvent"];
export type RankReference = Schemas["RankReference"];
export type LoginResponse = Schemas["LoginResponse"];
export type MeResponse = Schemas["MeResponse"];
export type CreateMappingResult = Schemas["CreateMappingResponse"];
