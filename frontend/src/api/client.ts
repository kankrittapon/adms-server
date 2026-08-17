import type {
  Attendance,
  AttendanceDetail,
  AuditEvent,
  CreateMappingResult,
  DashboardSummary,
  Device,
  DeviceUser,
  Enrollment,
  EnrollmentNextActions,
  EnrollmentReserveResult,
  EnrollmentTransitionResult,
  EventTypesResponse,
  HealthCheck,
  Healthz,
  Human,
  LoginResponse,
  Mapping,
  MappingEligibility,
  MeResponse,
  Page,
  RankReference,
  UnattributedAttendance,
  CreateOperatorRequest,
  OperatorOut,
  ToggleActiveResponse,
  WriteSessionStatus,
  BodyOf,
  JsonResponse,
  OperationsKey,
  QueryOf,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://192.168.1.248:8081";
const TOKEN_KEY = "adms_token";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export class ApiClientError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiClientError";
    this.code = code;
    this.status = status;
  }
}

export class UnauthorizedError extends Error {
  constructor() {
    super("unauthorized");
    this.name = "UnauthorizedError";
  }
}

async function request<T>(path: string, signal?: AbortSignal, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(init?.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers, signal });
  if (res.status === 401) {
    clearToken();
    throw new UnauthorizedError();
  }
  if (!res.ok) {
    let code = "HTTP_" + res.status;
    let message = res.statusText;
    try {
      const body = await res.json();
      if (body?.error?.code) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // non-JSON error body
    }
    throw new ApiClientError(res.status, code, message);
  }
  return (await res.json()) as T;
}

async function requestAuth<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(init?.headers as Record<string, string>) };
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let code = "HTTP_" + res.status;
    let message = res.statusText;
    try {
      const body = await res.json();
      if (body?.error?.code) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // non-JSON error body
    }
    throw new ApiClientError(res.status, code, message);
  }
  return res.json();
}

function qs(params: QueryOf<OperationsKey> | undefined): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v === undefined || v === null) continue;
    q.set(k, String(v));
  }
  const s = q.toString();
  return s ? "?" + s : "";
}

export const api = {
  baseUrl: BASE_URL,

  // Auth
  login: (username: string, password: string) =>
    requestAuth<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password } satisfies BodyOf<"login_api_v1_auth_login_post">),
    }),
  logout: () =>
    request<JsonResponse<"logout_api_v1_auth_logout_post">>("/api/v1/auth/logout", undefined, { method: "POST" }),
  me: (signal?: AbortSignal) => request<MeResponse>("/api/v1/auth/me", signal),
  changePassword: (current_password: string, new_password: string) =>
    request<JsonResponse<"change_password_api_v1_auth_change_password_post">>("/api/v1/auth/change-password", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password, new_password } satisfies BodyOf<"change_password_api_v1_auth_change_password_post">),
    }),

  // System / health
  healthz: (signal?: AbortSignal) => request<Healthz>("/healthz", signal),
  health: (signal?: AbortSignal) => request<HealthCheck>("/api/v1/health", signal),
  dashboard: (signal?: AbortSignal) => request<DashboardSummary>("/api/v1/dashboard/summary", signal),

  // Humans
  humans: (params: QueryOf<"list_humans_api_v1_humans_get">, signal?: AbortSignal) =>
    request<Page<Human>>(`/api/v1/humans${qs(params)}`, signal),
  human: (employeeId: string, signal?: AbortSignal) => request<Human>(`/api/v1/humans/${employeeId}`, signal),

  // Devices
  devices: (signal?: AbortSignal) => request<Page<Device>>("/api/v1/devices", signal),
  device: (deviceId: number, signal?: AbortSignal) => request<Device>(`/api/v1/devices/${deviceId}`, signal),

  // Device users
  deviceUsers: (params: QueryOf<"list_device_users_api_v1_device_users_get">, signal?: AbortSignal) =>
    request<Page<DeviceUser>>(`/api/v1/device-users${qs(params)}`, signal),
  deviceUser: (pk: number, signal?: AbortSignal) => request<DeviceUser>(`/api/v1/device-users/${pk}`, signal),

  // Attendance
  attendance: (params: QueryOf<"list_attendance_api_v1_attendance_get">, signal?: AbortSignal) =>
    request<Page<Attendance>>(`/api/v1/attendance${qs(params)}`, signal),
  attendanceDetail: (id: number, signal?: AbortSignal) => request<AttendanceDetail>(`/api/v1/attendance/${id}`, signal),

  // Mappings
  mappings: (params: QueryOf<"list_mappings_api_v1_mappings_get">, signal?: AbortSignal) =>
    request<Page<Mapping>>(`/api/v1/mappings${qs(params)}`, signal),
  mapping: (id: number, signal?: AbortSignal) => request<Mapping>(`/api/v1/mappings/${id}`, signal),
  mappingEligibility: (signal?: AbortSignal) =>
    request<MappingEligibility>("/api/v1/mappings/eligibility", signal),
  createMapping: (payload: BodyOf<"create_mapping_api_v1_mappings_post">) =>
    request<CreateMappingResult>("/api/v1/mappings", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  // F4 reconciliation diagnostics (ADMIN)
  unattributedAttendance: (params: QueryOf<"unattributed_api_v1_attendance_unattributed_get">, signal?: AbortSignal) =>
    request<Page<UnattributedAttendance>>(`/api/v1/attendance/unattributed${qs(params)}`, signal),

  // Enrollments
  enrollments: (params: QueryOf<"list_enrollments_api_v1_enrollments_get">, signal?: AbortSignal) =>
    request<Page<Enrollment>>(`/api/v1/enrollments${qs(params)}`, signal),
  enrollment: (id: number, signal?: AbortSignal) => request<Enrollment>(`/api/v1/enrollments/${id}`, signal),
  enrollmentNextActions: (id: number, signal?: AbortSignal) =>
    request<EnrollmentNextActions>(`/api/v1/enrollments/${id}/next-actions`, signal),

  // Enrollment workflow writes (gated server-side by API_WRITE_ENABLED + role)
  reserveEnrollment: (payload: BodyOf<"reserve_api_v1_enrollments_reserve_post">) =>
    request<EnrollmentReserveResult>("/api/v1/enrollments/reserve", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  createTerminalAccount: (id: number, displayName: string, operator: string) =>
    request<EnrollmentTransitionResult>(`/api/v1/enrollments/${id}/create-terminal-account`, undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: displayName,
        operator,
      } satisfies BodyOf<"create_terminal_account_api_v1_enrollments__enrollment_id__create_terminal_account_post">),
    }),
  startFingerprintEnrollment: (id: number, operator: string, notes?: string) =>
    enrollmentTransition<"start_fingerprint_api_v1_enrollments__enrollment_id__start_fingerprint_enrollment_post">(
      id,
      "start-fingerprint-enrollment",
      operator,
      notes
    ),
  confirmFingerprintEnrolled: (id: number, operator: string, notes?: string) =>
    enrollmentTransition<"confirm_fingerprint_api_v1_enrollments__enrollment_id__confirm_fingerprint_post">(
      id,
      "confirm-fingerprint",
      operator,
      notes
    ),
  startControlledScan: (id: number, operator: string, notes?: string) =>
    enrollmentTransition<"start_scan_window_api_v1_enrollments__enrollment_id__start_controlled_scan_post">(
      id,
      "start-controlled-scan",
      operator,
      notes
    ),
  confirmControlledScan: (id: number, operator: string, scanTime: string) =>
    request<EnrollmentTransitionResult>(`/api/v1/enrollments/${id}/confirm-controlled-scan`, undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operator,
        scan_time: scanTime,
      } satisfies BodyOf<"confirm_scan_api_v1_enrollments__enrollment_id__confirm_controlled_scan_post">),
    }),
  markReadyForMapping: (id: number, operator: string, notes?: string) =>
    enrollmentTransition<"mark_ready_api_v1_enrollments__enrollment_id__mark_ready_for_mapping_post">(
      id,
      "mark-ready-for-mapping",
      operator,
      notes
    ),
  cancelEnrollment: (id: number, operator: string, notes: string) =>
    request<EnrollmentTransitionResult>(`/api/v1/enrollments/${id}/cancel`, undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator, notes } satisfies BodyOf<"cancel_api_v1_enrollments__enrollment_id__cancel_post">),
    }),

  // Reference
  ranks: (signal?: AbortSignal) => request<RankReference[]>("/api/v1/reference/ranks", signal),

  // Humans update
  updateHumanEnglishName: (employeeId: string, englishName: string | null) =>
    request<Human>(`/api/v1/humans/${employeeId}`, undefined, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ english_name: englishName } satisfies BodyOf<"update_human_english_name_api_v1_humans__employee_id__patch">),
    }),

  // Operator Management (admin)
  listOperators: (signal?: AbortSignal) => request<OperatorOut[]>("/api/v1/operators", signal),
  createOperator: (payload: CreateOperatorRequest) =>
    request<OperatorOut>("/api/v1/operators", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload satisfies BodyOf<"create_operator_api_v1_operators_post">),
    }),
  toggleOperatorActive: (operatorId: number, active: boolean) =>
    request<ToggleActiveResponse>(`/api/v1/operators/${operatorId}/toggle-active`, undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active } satisfies BodyOf<"toggle_active_api_v1_operators__operator_id__toggle_active_post">),
    }),

  // F5 hardening: audit trail (admin)
  auditEvents: (params: QueryOf<"list_events_api_v1_audit_events_get">, signal?: AbortSignal) =>
    request<Page<AuditEvent>>(`/api/v1/audit/events${qs(params)}`, signal),
  auditEventTypes: (signal?: AbortSignal) =>
    request<EventTypesResponse>("/api/v1/audit/event-types", signal),

  // Runtime write session (Layer 2 write control; ADMIN opens/closes, any
  // authenticated role can read status)
  writeSessionStatus: (signal?: AbortSignal) =>
    request<WriteSessionStatus>("/api/v1/write-session", signal),
  openWriteSession: (reason: string) =>
    request<WriteSessionStatus>("/api/v1/write-session/open", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason } satisfies BodyOf<"open_session_api_v1_write_session_open_post">),
    }),
  closeWriteSession: () =>
    request<WriteSessionStatus>("/api/v1/write-session/close", undefined, { method: "POST" }),
};

function enrollmentTransition<OpId extends OperationsKey>(
  id: number,
  action: string,
  operator: string,
  notes?: string
): Promise<EnrollmentTransitionResult> {
  return request<EnrollmentTransitionResult>(`/api/v1/enrollments/${id}/${action}`, undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      operator,
      notes,
    } satisfies BodyOf<OpId>),
  });
}
