import type {
  Attendance,
  AttendanceDetail,
  DashboardSummary,
  Device,
  DeviceUser,
  Enrollment,
  HealthCheck,
  Healthz,
  Human,
  Mapping,
  Page,
  RankReference,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://192.168.1.248:8081";

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

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
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

export const api = {
  baseUrl: BASE_URL,

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

  // Reference
  ranks: (signal?: AbortSignal) => request<RankReference[]>("/api/v1/reference/ranks", signal),
};
