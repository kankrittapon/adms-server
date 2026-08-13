import type {
  Attendance,
  AttendanceDetail,
  DashboardSummary,
  Device,
  DeviceUser,
  Enrollment,
  EnrollmentNextActions,
  EnrollmentReserveResult,
  EnrollmentTransitionResult,
  HealthCheck,
  Healthz,
  Human,
  Mapping,
  Page,
  RankReference,
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

export interface LoginResponse {
  token: string;
  token_type: string;
  role: string;
  expires_at: string;
  operator_id: number;
  username: string;
  display_name: string;
}

export interface MeResponse {
  operator_id: number;
  username: string;
  display_name: string;
  role: string;
}

export const api = {
  baseUrl: BASE_URL,

  // Auth
  login: (username: string, password: string) =>
    requestAuth<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<unknown>("/api/v1/auth/logout", undefined, { method: "POST" }),
  me: (signal?: AbortSignal) => request<MeResponse>("/api/v1/auth/me", signal),

  // System / health
  healthz: (signal?: AbortSignal) => request<Healthz>("/healthz", signal),
  health: (signal?: AbortSignal) => request<HealthCheck>("/api/v1/health", signal),
  dashboard: (signal?: AbortSignal) => request<DashboardSummary>("/api/v1/dashboard/summary", signal),

  // Humans
  humans: (params: { limit?: number; offset?: number; production_scope?: boolean; search?: string; category?: string }, signal?: AbortSignal) => {
    const q = new URLSearchParams();
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    if (params.production_scope !== undefined) q.set("production_scope", String(params.production_scope));
    if (params.search) q.set("search", params.search);
    if (params.category) q.set("category", params.category);
    const qs = q.toString();
    return request<Page<Human>>(`/api/v1/humans${qs ? "?" + qs : ""}`, signal);
  },
  human: (employeeId: string, signal?: AbortSignal) => request<Human>(`/api/v1/humans/${employeeId}`, signal),

  // Devices
  devices: (signal?: AbortSignal) => request<Page<Device>>("/api/v1/devices", signal),
  device: (deviceId: number, signal?: AbortSignal) => request<Device>(`/api/v1/devices/${deviceId}`, signal),

  // Device users
  deviceUsers: (params: { device_id?: number; active?: boolean; limit?: number }, signal?: AbortSignal) => {
    const q = new URLSearchParams();
    if (params.device_id !== undefined) q.set("device_id", String(params.device_id));
    if (params.active !== undefined) q.set("active", String(params.active));
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    const qs = q.toString();
    return request<Page<DeviceUser>>(`/api/v1/device-users${qs ? "?" + qs : ""}`, signal);
  },
  deviceUser: (pk: number, signal?: AbortSignal) => request<DeviceUser>(`/api/v1/device-users/${pk}`, signal),

  // Attendance
  attendance: (params: { limit?: number; offset?: number; status?: string; date_from?: string; date_to?: string; employee_id?: string; device_user_pk?: number }, signal?: AbortSignal) => {
    const q = new URLSearchParams();
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    if (params.status) q.set("status", params.status);
    if (params.date_from) q.set("date_from", params.date_from);
    if (params.date_to) q.set("date_to", params.date_to);
    if (params.employee_id) q.set("employee_id", params.employee_id);
    if (params.device_user_pk !== undefined) q.set("device_user_pk", String(params.device_user_pk));
    const qs = q.toString();
    return request<Page<Attendance>>(`/api/v1/attendance${qs ? "?" + qs : ""}`, signal);
  },
  attendanceDetail: (id: number, signal?: AbortSignal) => request<AttendanceDetail>(`/api/v1/attendance/${id}`, signal),

  // Mappings
  mappings: (params: { limit?: number; mapping_status?: string }, signal?: AbortSignal) => {
    const q = new URLSearchParams();
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.mapping_status) q.set("mapping_status", params.mapping_status);
    const qs = q.toString();
    return request<Page<Mapping>>(`/api/v1/mappings${qs ? "?" + qs : ""}`, signal);
  },
  mapping: (id: number, signal?: AbortSignal) => request<Mapping>(`/api/v1/mappings/${id}`, signal),

  // Enrollments
  enrollments: (params: { limit?: number; status?: string }, signal?: AbortSignal) => {
    const q = new URLSearchParams();
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.status) q.set("status", params.status);
    const qs = q.toString();
    return request<Page<Enrollment>>(`/api/v1/enrollments${qs ? "?" + qs : ""}`, signal);
  },
  enrollment: (id: number, signal?: AbortSignal) => request<Enrollment>(`/api/v1/enrollments/${id}`, signal),
  enrollmentNextActions: (id: number, signal?: AbortSignal) =>
    request<EnrollmentNextActions>(`/api/v1/enrollments/${id}/next-actions`, signal),

  // Enrollment workflow writes (gated server-side by API_WRITE_ENABLED + role)
  reserveEnrollment: (payload: {
    employee_id: string;
    device_id: number;
    operator: string;
    roster_user_ids?: string[];
  }) =>
    request<EnrollmentReserveResult>("/api/v1/enrollments/reserve", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  startFingerprintEnrollment: (id: number, operator: string, notes?: string) =>
    enrollmentTransition(`/api/v1/enrollments/${id}/start-fingerprint-enrollment`, operator, notes),
  confirmFingerprintEnrolled: (id: number, operator: string, notes?: string) =>
    enrollmentTransition(`/api/v1/enrollments/${id}/confirm-fingerprint`, operator, notes),
  startControlledScan: (id: number, operator: string, notes?: string) =>
    enrollmentTransition(`/api/v1/enrollments/${id}/start-controlled-scan`, operator, notes),
  confirmControlledScan: (id: number, operator: string, scanTime: string, notes?: string) =>
    request<EnrollmentTransitionResult>(`/api/v1/enrollments/${id}/confirm-controlled-scan`, undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator, scan_time: scanTime, notes }),
    }),
  markReadyForMapping: (id: number, operator: string, notes?: string) =>
    enrollmentTransition(`/api/v1/enrollments/${id}/mark-ready-for-mapping`, operator, notes),
  cancelEnrollment: (id: number, operator: string, notes: string) =>
    request<EnrollmentTransitionResult>(`/api/v1/enrollments/${id}/cancel`, undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator, notes }),
    }),

  // Reference
  ranks: (signal?: AbortSignal) => request<RankReference[]>("/api/v1/reference/ranks", signal),
};

function enrollmentTransition(
  path: string,
  operator: string,
  notes?: string
): Promise<EnrollmentTransitionResult> {
  return request<EnrollmentTransitionResult>(path, undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operator, notes }),
  });
}
