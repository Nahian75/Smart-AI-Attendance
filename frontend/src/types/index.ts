export interface AttendanceLog {
  id: string;
  employee_id: string;
  attendance_date: string;
  check_in_at: string | null;
  check_out_at: string | null;
  status: "present" | "late" | "absent" | "half_day" | "holiday";
  is_late: boolean;
  late_by_min: number;
  is_early_leave: boolean;
  early_by_min: number;
  working_hours: number | null;
  overtime_seconds: number;
}

export interface AttendanceSummary {
  date: string;
  total_employees: number;
  present: number;
  absent: number;
  late: number;
  early_leave: number;
  attendance_rate: number;
}

export interface LiveEvent {
  // Backend processed event fields
  action?: "check_in" | "check_out" | "skip";
  employee_id?: string | null;
  employee_name?: string | null;
  department?: string | null;
  status?: string;
  is_late?: boolean;
  late_by_min?: number;
  overtime_seconds?: number;
  // Raw edge event fields
  type?: string;
  camera_id?: string | null;
  track_id?: number | null;
  confidence?: number | null;
  spoof_score?: number | null;
  is_live?: boolean;
  snapshot_url?: string | null;
  // Shared
  timestamp?: string | number | null;
}

export interface Employee {
  id: string;
  full_name: string;
  employee_code: string | null;
  email: string | null;
  phone: string | null;
  department: string | null;
  designation: string | null;
  is_enrolled: boolean;
  is_active: boolean;
  is_blacklisted: boolean;
  is_vip: boolean;
  face_enrolled_at: string | null;
}

export interface Camera {
  id: string;
  name: string;
  location: string | null;
  rtsp_url: string | null;
  fps_target: number;
  status: string;
  direction: string;
  camera_role: string;
  camera_zone: string | null;
  is_restricted: boolean;
  is_active: boolean;
  last_seen_at: string | null;
}

export interface AlertItem {
  id: string;
  type: string;
  severity: "high" | "medium" | "low";
  message: string;
  employee_id: string | null;
  camera_id: string | null;
  snapshot_url: string | null;
  is_acknowledged: boolean;
  created_at: string | null;
}

export interface ComplianceRow {
  employee_id: string;
  name: string;
  code: string | null;
  dept: string | null;
  total: number;
  on_time: number;
  late: number;
  absent: number;
  on_time_pct: number;
}

