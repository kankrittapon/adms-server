// Types mirroring the ADMS F1 API contract (docs/API_CONTRACT.md).
// Generated-compatible with the OpenAPI schema at /openapi.json.

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Healthz {
  status: string;
}

export interface CollectorSummary {
  state?: string | null;
  device_connected?: boolean | null;
  db_status?: string | null;
  mqtt_status?: string | null;
  loop_alive?: boolean | null;
  updated_at?: string | null;
}

export interface HealthCheck {
  status: string;
  database: string;
  mqtt?: string | null;
  collector?: CollectorSummary | null;
  timestamp: string;
}

export interface DashboardSummary {
  humans_total: number;
  humans_production_eligible: number;
  humans_excluded: number;
  devices_total: number;
  devices_active: number;
  device_users_total: number;
  device_users_active: number;
  device_users_unmapped: number;
  attendance_total: number;
  attendance_today: number;
  attendance_unattributed: number;
  mappings_total: number;
  mappings_verified_active: number;
  enrollments_by_status: Record<string, number>;
  collector?: CollectorSummary | null;
}

export interface RankMetadata {
  rank_th_original: string;
  rank_th_full?: string | null;
  rank_th_abbreviation?: string | null;
  rank_en?: string | null;
  rank_en_abbreviation?: string | null;
  rank_category?: string | null;
  acting?: string | null;
}

export interface Human {
  employee_id: string;
  personnel_id?: string | null;
  display_name: string;
  rank?: string | null;
  rank_metadata?: RankMetadata | null;
  position?: string | null;
  branch?: string | null;
  category?: string | null;
  notes?: string | null;
  active: boolean;
  production_scope: boolean;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface Device {
  device_id: number;
  serial_number: string;
  device_name: string;
  device_ip: string;
  platform: string;
  firmware_version?: string | null;
  active: boolean;
  first_seen_at: string;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export interface DeviceUser {
  device_user_pk: number;
  device_id: number;
  device_user_id: string;
  device_uid?: number | null;
  device_display_name?: string | null;
  privilege: number;
  active: boolean;
  first_seen_at: string;
  last_seen_at: string;
  roster_last_seen_at?: string | null;
  inactive_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Attendance {
  id: number;
  user_id: string;
  device_ip: string;
  scan_time: string;
  punch_type?: string | null;
  status: string;
  device_id?: number | null;
  device_user_pk?: number | null;
  employee_id?: string | null;
  created_at: string;
}

export interface AttendanceDetail extends Attendance {
  device_name?: string | null;
  device_user_id?: string | null;
  employee_name?: string | null;
}

export interface Mapping {
  mapping_id: number;
  employee_id: string;
  device_user_pk: number;
  mapping_status: string;
  mapping_source: string;
  verified_by?: string | null;
  verification_method?: string | null;
  verification_note?: string | null;
  valid_from: string;
  valid_to?: string | null;
  verified_at?: string | null;
  created_at: string;
  updated_at: string;
  employee_name?: string | null;
  device_user_id?: string | null;
}

export interface Enrollment {
  enrollment_id: number;
  employee_id: string;
  device_id: number;
  reserved_device_user_id: string;
  status: string;
  reserved_by: string;
  reserved_at: string;
  terminal_created_at?: string | null;
  device_uid?: number | null;
  fingerprint_confirmed_at?: string | null;
  controlled_scan_window_until?: string | null;
  controlled_scan_time?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  employee_name?: string | null;
  device_name?: string | null;
}

export interface RankReference {
  rank_th_abbreviation: string;
  rank_th_full: string;
  rank_en: string;
  rank_en_abbreviation: string;
  rank_category: string;
  source: string;
}
