/** Types mirroring the backend's Pydantic schemas (see docs/api.md). */

export type UserRole = "USER" | "ADMIN";

export type VideoStatus =
  | "DRAFT"
  | "QUEUED"
  | "PROCESSING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type JobStatus = "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type StepStatus = "pending" | "active" | "done" | "failed";

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  /** Session minted by /api/auth/guest rather than a chosen account. The
   *  address is a synthetic `@guest.aseelo.example` one, so never show it as theirs. */
  is_guest: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Brand {
  id: string;
  brand_name: string;
  logo_url: string | null;
  /** Upload response only: false means the logo has no alpha and will render as a solid box. */
  logo_has_transparency?: boolean | null;
  logo_cutout_applied?: boolean | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  font: string;
  phone: string | null;
  whatsapp: string | null;
  website: string | null;
  social_media: Record<string, string>;
  address: string | null;
  tagline: string | null;
  created_at: string;
  updated_at: string;
}

export type BrandUpdate = Partial<
  Pick<
    Brand,
    | "brand_name"
    | "primary_color"
    | "secondary_color"
    | "accent_color"
    | "font"
    | "phone"
    | "whatsapp"
    | "website"
    | "address"
    | "tagline"
    | "social_media"
  >
>;

export interface Template {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  preview_url: string | null;
  configuration: Record<string, unknown>;
  is_active: boolean;
  sort_order: number;
}

export interface JobStep {
  key: string;
  label: string;
  label_ar: string;
  status: StepStatus;
  progress: number;
}

export interface Job {
  id: string;
  video_id: string;
  status: JobStatus;
  progress: number;
  current_step: string;
  error_message: string | null;
  attempt: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  steps: JobStep[];
}

export interface Video {
  id: string;
  title: string | null;
  text_content: string;
  template_id: string | null;
  status: VideoStatus;
  output_file_url: string | null;
  thumbnail_url: string | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  has_audio: boolean;
  output_file_size: number | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  template: Template | null;
  job: Job | null;
}

export interface VideoList {
  items: Video[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardStats {
  total_videos: number;
  videos_today: number;
  processing_jobs: number;
  completed_videos: number;
  failed_videos: number;
  storage_used_bytes: number;
  recent_videos: Video[];
}

export type VideoFilter = "all" | "processing" | "completed" | "failed";

/** One entry of the backend's `error.details` array. */
export interface ApiErrorDetail {
  field: string;
  message: string;
}
