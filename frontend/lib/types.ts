export type Role = "PATIENT" | "DOCTOR" | "HOSPITAL_ADMIN" | "SYSTEM_ADMIN" | "REGULATOR";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  status: string;
  hospital_id: number | null;
  pseudo_id?: string;
}

export interface RecordFile {
  id: number;
  mime_type: string;
  size: number;
  checksum: string;
  key_id: string;
  key_version: number;
  report_id: number | null;
  created_at: string;
}

export interface ReportRow {
  id: number;
  file_id: number | null;
  title: string;
  status: string;
}

export interface MedicalRecord {
  id: number;
  patient_id: number;
  record_type: string;
  title: string;
  status: string;
  files: RecordFile[];
  reports: ReportRow[];
}

export interface Permission {
  id: number;
  patient_id: number;
  recipient_user_id: number;
  resource_type: string;
  resource_id: number | null;
  permission_type: string;
  status: string; // effective status (PENDING/ACTIVE/REVOKED/EXPIRED/REJECTED)
  stored_status: string;
  start_at: string | null;
  expires_at: string | null;
  granted_at: string | null;
  revoked_at: string | null;
}

export interface ConsentRequest {
  id: number;
  patient_id: number;
  requester_id: number;
  resource_type: string;
  resource_id: number | null;
  scope: string;
  status: string;
}

export interface ConsentBundle {
  permissions: Permission[];
  requests: ConsentRequest[];
}

export interface ResearchConsent {
  id: number;
  status: string;
  scope: string | null;
  allowed_organizations: number[] | null;
  expires_at: string | null;
}

export interface Notification {
  id: number;
  type: string;
  title: string;
  message: string | null;
  read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface AccessEvent {
  id: number;
  actor_id: number | null;
  role: string | null;
  action: string;
  resource_type: string | null;
  resource_id: number | null;
  outcome: string;
  created_at: string;
}

export interface Prescription {
  id: number;
  patient_id: number;
  doctor_id: number;
  medication: string;
  dosage: string | null;
  instructions: string | null;
  issued_at: string;
}

export interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  status: string;
  hospital_id: number | null;
}
