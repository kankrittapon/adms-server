"""Typed response models for the ADMS F1 API.

PromptID: ADMS-Frontend-F1-API-001

Frontend-safe contracts only. raw_payload, biometric data, and secrets are
never exposed here. Timestamps are timezone-aware (ISO 8601, UTC/offset
semantics preserved from the database).
"""

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int


# --- Health / system ------------------------------------------------------


class Healthz(BaseModel):
    status: str = "ok"


class HealthCheck(BaseModel):
    status: str
    database: str
    mqtt: Optional[str] = None
    collector: Optional[Dict[str, Any]] = None
    timestamp: datetime


class CollectorSummary(BaseModel):
    state: Optional[str] = None
    device_connected: Optional[bool] = None
    db_status: Optional[str] = None
    mqtt_status: Optional[str] = None
    loop_alive: Optional[bool] = None
    updated_at: Optional[datetime] = None


class DashboardSummary(BaseModel):
    humans_total: int
    humans_production_eligible: int
    humans_excluded: int
    devices_total: int
    devices_active: int
    device_users_total: int
    device_users_active: int
    device_users_unmapped: int
    attendance_total: int
    attendance_today: int
    attendance_unattributed: int
    mappings_total: int
    mappings_verified_active: int
    enrollments_by_status: Dict[str, int]
    collector: Optional[CollectorSummary] = None


# --- Human Master ---------------------------------------------------------


class RankMetadata(BaseModel):
    rank_th_original: str
    rank_th_full: Optional[str] = None
    rank_th_abbreviation: Optional[str] = None
    rank_en: Optional[str] = None
    rank_en_abbreviation: Optional[str] = None
    rank_category: Optional[str] = None
    acting: Optional[str] = None


class Human(BaseModel):
    employee_id: str
    personnel_id: Optional[str] = None
    display_name: str
    rank: Optional[str] = None
    rank_metadata: Optional[RankMetadata] = None
    position: Optional[str] = None
    branch: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    active: bool
    production_scope: bool
    source: str
    created_at: datetime
    updated_at: datetime


# --- Devices --------------------------------------------------------------


class Device(BaseModel):
    device_id: int
    serial_number: str
    device_name: str
    device_ip: str
    platform: str
    firmware_version: Optional[str] = None
    active: bool
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class DeviceUser(BaseModel):
    device_user_pk: int
    device_id: int
    device_user_id: str
    device_uid: Optional[int] = None
    device_display_name: Optional[str] = None
    privilege: int
    active: bool
    first_seen_at: datetime
    last_seen_at: datetime
    roster_last_seen_at: Optional[datetime] = None
    inactive_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# --- Attendance -----------------------------------------------------------


class Attendance(BaseModel):
    id: int
    user_id: str
    device_ip: str
    scan_time: datetime
    punch_type: Optional[str] = None
    status: str
    device_id: Optional[int] = None
    device_user_pk: Optional[int] = None
    employee_id: Optional[str] = None
    created_at: datetime


class AttendanceDetail(Attendance):
    device_name: Optional[str] = None
    device_user_id: Optional[str] = None
    employee_name: Optional[str] = None


class AttendanceRawPayload(BaseModel):
    id: int
    raw_payload: Dict[str, Any]


class AttributionReasoning(BaseModel):
    classification: str
    detail: str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    resolver_employee_id: Optional[str] = None


class UnattributedAttendance(BaseModel):
    id: int
    user_id: str
    device_ip: str
    scan_time: datetime
    punch_type: Optional[str] = None
    status: str
    device_id: Optional[int] = None
    device_user_pk: Optional[int] = None
    employee_id: Optional[str] = None
    created_at: datetime
    reasoning: AttributionReasoning


# --- Mappings -------------------------------------------------------------


class Mapping(BaseModel):
    mapping_id: int
    employee_id: str
    device_user_pk: int
    mapping_status: str
    mapping_source: str
    verified_by: Optional[str] = None
    verification_method: Optional[str] = None
    verification_note: Optional[str] = None
    valid_from: datetime
    valid_to: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    employee_name: Optional[str] = None
    device_user_id: Optional[str] = None


class MappingEligibilityItem(BaseModel):
    enrollment_id: int
    employee_id: str
    device_id: int
    reserved_device_user_id: str
    controlled_scan_time: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    notes: Optional[str] = None
    employee_name: Optional[str] = None
    device_name: Optional[str] = None
    device_user_pk: Optional[int] = None
    device_user_id: Optional[str] = None
    device_user_active: Optional[bool] = None
    controlled_attendance_id: Optional[int] = None


class MappingEligibility(BaseModel):
    items: List[MappingEligibilityItem]
    count: int


# --- Enrollment -----------------------------------------------------------


class Enrollment(BaseModel):
    enrollment_id: int
    employee_id: str
    device_id: int
    reserved_device_user_id: str
    status: str
    reserved_by: str
    reserved_at: datetime
    terminal_created_at: Optional[datetime] = None
    device_uid: Optional[int] = None
    fingerprint_confirmed_at: Optional[datetime] = None
    controlled_scan_window_until: Optional[datetime] = None
    controlled_scan_time: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    employee_name: Optional[str] = None
    device_name: Optional[str] = None


# --- Reference ------------------------------------------------------------


class AuditEvent(BaseModel):
    id: int
    device_ip: Optional[str] = None
    event_type: str
    message: Optional[str] = None
    created_at: datetime


class RankReference(BaseModel):
    rank_th_abbreviation: str
    rank_th_full: str
    rank_en: str
    rank_en_abbreviation: str
    rank_category: str
    source: str
