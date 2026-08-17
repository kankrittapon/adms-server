import type { Locale } from "./types";

/**
 * Centralized backend-enum -> display-label mapping, TH/EN.
 *
 * Backend status/classification enums (RESERVED, READY_FOR_MAPPING,
 * NO_MAPPING, ...) are stable machine-readable identifiers — fine as API
 * contract values, wrong as UI copy. Previously several pages (Dashboard
 * chips, Enrollment queue cards, Mappings list, Attendance reconciliation)
 * each fell back to printing these raw strings verbatim wherever no special
 * case existed. This module is the single place that translation lives, so
 * a new enum value only needs a label added once.
 *
 * Unmapped values still render as the raw string, on the theory that an
 * ADMIN/technical viewer seeing an unrecognized code is better than the
 * value silently disappearing — but every currently-defined backend enum is
 * covered below.
 */

type LabelMap = Record<string, Record<Locale, string>>;

export const enrollmentStatusLabels: LabelMap = {
  RESERVED: { en: "Reserved", th: "จองรหัสแล้ว" },
  TERMINAL_ACCOUNT_CREATED: { en: "Terminal Account Created", th: "สร้างบัญชีบนเครื่องแล้ว" },
  FINGERPRINT_ENROLLMENT_PENDING: { en: "Fingerprint Enrollment Pending", th: "รอลงทะเบียนลายนิ้วมือ" },
  FINGERPRINT_ENROLLED: { en: "Fingerprint Enrolled", th: "ลงทะเบียนลายนิ้วมือแล้ว" },
  CONTROLLED_SCAN_PENDING: { en: "Awaiting Test Scan", th: "รอทดสอบสแกน" },
  CONTROLLED_SCAN_CONFIRMED: { en: "Test Scan Confirmed", th: "ยืนยันการทดสอบสแกนแล้ว" },
  READY_FOR_MAPPING: { en: "Ready to Confirm Identity", th: "พร้อมยืนยันตัวบุคคล" },
  RETIRED: { en: "Completed", th: "เสร็จสมบูรณ์" },
  CANCELLED: { en: "Cancelled", th: "ยกเลิกแล้ว" },
};

export const attendanceStatusLabels: LabelMap = {
  ON_TIME: { en: "On Time", th: "ตรงเวลา" },
  LATE: { en: "Late", th: "สาย" },
  UNKNOWN: { en: "Unknown", th: "ไม่ทราบสถานะ" },
};

export const mappingStatusLabels: LabelMap = {
  VERIFIED: { en: "Verified", th: "ยืนยันแล้ว" },
  PROBABLE: { en: "Probable", th: "คาดว่าถูกต้อง" },
  LEGACY: { en: "Legacy", th: "ข้อมูลเดิม" },
  CANDIDATE: { en: "Candidate", th: "รอพิจารณา" },
  REVOKED: { en: "Revoked", th: "ยกเลิกการยืนยัน" },
};

export const verificationMethodLabels: LabelMap = {
  CONTROLLED_SCAN: { en: "Controlled Test Scan", th: "ทดสอบสแกนภายใต้การควบคุม" },
  TERMINAL_ROSTER_REVIEW: { en: "Terminal Roster Review", th: "ตรวจสอบรายชื่อบนเครื่อง" },
  MANUAL_ADMIN_CONFIRMATION: { en: "Manual Admin Confirmation", th: "ผู้ดูแลระบบยืนยันด้วยตนเอง" },
  LEGACY_MIGRATION: { en: "Legacy Migration", th: "โอนย้ายจากระบบเดิม" },
};

export const attendanceReasoningLabels: LabelMap = {
  NO_DEVICE_USER: { en: "No Terminal Account Found", th: "ไม่พบบัญชีบนเครื่องสแกน" },
  LEGACY_USER: { en: "Legacy Account (Not Migrated)", th: "บัญชีเก่าที่ยังไม่โอนย้าย" },
  NO_MAPPING: { en: "No Identity Confirmed Yet", th: "ยังไม่ได้ยืนยันตัวบุคคล" },
  BEFORE_VALID_FROM: { en: "Scan Before Identity Was Confirmed", th: "สแกนก่อนวันที่ยืนยันตัวบุคคล" },
  AFTER_VALID_TO: { en: "Scan After Identity Expired", th: "สแกนหลังจากหมดอายุการยืนยัน" },
  INSIDE_INTERVAL: { en: "Matched (Diagnostic Only)", th: "จับคู่ได้ (สำหรับตรวจสอบเท่านั้น)" },
};

export function enumLabel(map: LabelMap, value: string, locale: Locale): string {
  return map[value]?.[locale] ?? value;
}
