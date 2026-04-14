export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "user" | "admin";
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export type ApplicationStatus =
  | "pending"
  | "processing"
  | "ready_for_review"
  | "approved"
  | "rejected"
  | "error";

export type DocumentType = "passport" | "national_id" | "drivers_license";

export interface ExtractedFields {
  full_name: string | null;
  dob: string | null;
  document_number: string | null;
  expiry_date: string | null;
  nationality: string | null;
  gender: string | null;
  national_id_number: string | null;
  father_name: string | null;
  place_of_birth: string | null;
  issuing_authority: string | null;
  confidences: Record<string, number>;
  raw_text: string | null;
}

export interface Document {
  id: string;
  application_id: string;
  doc_type: DocumentType;
  file_path: string;
  original_filename: string;
  file_size: number;
  mime_type: string;
  ocr_data: Record<string, string> | null;
  ocr_raw_text: string | null;
  fraud_score: number | null;
  fraud_details: FraudDetails | null;
  uploaded_at: string;
}

export interface FraudDetails {
  overall_score: number;
  is_flagged: boolean;
  threshold: number;
  checks: FraudCheck[];
}

export interface FraudCheck {
  name: string;
  score: number;
  weight: number;
  details: string;
  passed: boolean;
}

export interface FaceVerification {
  id: string;
  application_id: string;
  selfie_path: string;
  document_face_path: string | null;
  similarity_score: number | null;
  is_match: boolean | null;
  model_used: string | null;
  verified_at: string | null;
}

// Matches backend IDVStatusResponse schema
export interface IDVApplication {
  id: string;
  status: ApplicationStatus;
  submitted_at: string;
  reviewed_at: string | null;
  rejection_reason: string | null;
  documents: Document[];
  face_match_score: number | null;
  face_is_match: boolean | null;
}

// Matches backend ApplicationListItem schema
export interface ApplicationListItem {
  id: string;
  user_email: string;
  user_full_name: string;
  status: ApplicationStatus;
  submitted_at: string;
  reviewed_at: string | null;
  document_count: number;
}

// Matches backend ApplicationListResponse schema
export interface ApplicationListResponse {
  items: ApplicationListItem[];
  total: number;
  page: number;
  page_size: number;
}

// Pipeline types
export interface PipelineStageResult {
  stage: number;
  name: string;
  passed: boolean;
  hard_fail: boolean;
  details: Record<string, unknown>;
  flags: PipelineFlag[];
  reason_codes: PipelineReasonCode[];
  duration_ms: number;
}

export interface PipelineFlag {
  flag_type: string;
  detail: string;
  stage?: number;
}

export interface PipelineReasonCode {
  code: string;
  stage: number;
  severity: "critical" | "warning" | "error";
  message: string;
}

export interface PipelineChannelScores {
  channel_a: number | null;
  channel_b: number | null;
  channel_c: number | null;
  channel_d: number | null;
  channel_e: number | null;
}

export interface PipelineResult {
  id: string;
  pipeline_version: string;
  stage_0_result: PipelineStageResult | null;
  stage_1_result: PipelineStageResult | null;
  stage_2_result: PipelineStageResult | null;
  stage_3_result: PipelineStageResult | null;
  stage_4_result: PipelineStageResult | null;
  channel_scores: PipelineChannelScores | null;
  weighted_total: number | null;
  hard_rules_result: Record<string, unknown> | null;
  decision_override: string | null;
  final_decision: string | null;
  reason_codes: PipelineReasonCode[] | null;
  flags: PipelineFlag[] | null;
  started_at: string | null;
  completed_at: string | null;
}

// Matches backend ApplicationDetailResponse schema
export interface ApplicationDetail {
  id: string;
  user_id: string;
  user_email: string;
  user_full_name: string;
  status: ApplicationStatus;
  submitted_at: string;
  reviewed_at: string | null;
  rejection_reason: string | null;
  reviewer_id: string | null;
  documents: Document[];
  face_match_score: number | null;
  face_is_match: boolean | null;
  pipeline_version: string | null;
  pipeline_decision: string | null;
  verification_score: number | null;
  score_details: Record<string, unknown> | null;
  pipeline_result: PipelineResult | null;
}

export interface StatsResponse {
  total_applications: number;
  pending: number;
  processing: number;
  ready_for_review: number;
  approved: number;
  rejected: number;
  error: number;
  avg_processing_hours: number | null;
  fraud_flag_rate: number | null;
}

export interface AuditLog {
  id: string;
  application_id: string;
  action: string;
  performed_by: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface ApiError {
  detail: string;
}
