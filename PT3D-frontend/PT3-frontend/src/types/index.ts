export interface GenerateResponse {
  status: string
  job_id: string
  quality_preset: QualityPreset
}

export type QualityPreset = 'fast' | 'balanced' | 'quality'

export interface User {
  user_id: string
  display_name: string
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  user: User
}

export type JobStatus =
  | 'queued'
  | 'sdxl_running'
  | 'converting'
  | 'done'
  | 'failed'

export interface JobStatusResponse {
  job_id: string
  status: JobStatus
  quality_preset: QualityPreset
  prompt: string
  created_at: string
  error: string | null
}

export interface JobSummary {
  job_id: string
  prompt: string
  quality_preset: QualityPreset
  status: JobStatus
  created_at: string
  updated_at: string
  error: string | null
  has_image: boolean
  has_glb: boolean
}

export interface ViewerHandle {
  loadGLBFromUrl: (url: string, successMessage?: string) => Promise<boolean>
  clearModel: () => void
}

export type TrainingFailureLabel =
  | 'bad_image'
  | 'bad_shape'
  | 'bad_texture'
  | 'missing_parts'
  | 'wrong_category'
  | 'preview_failed'
  | 'good_reference'

export interface TrainingExample {
  example_id: string
  job_id: string
  user_id: string
  prompt: string
  quality_preset: QualityPreset
  failure_label: TrainingFailureLabel
  admin_notes: string | null
  include_in_sdxl_lora: boolean
  include_in_hunyuan: boolean
  review_status: string
  has_image: boolean
  has_glb: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export interface TrainingConfig {
  sdxl_lora_enabled: boolean
  sdxl_lora_path: string | null
  sdxl_lora_scale: number
  hunyuan_finetuned_enabled: boolean
  hunyuan_finetuned_model_path: string | null
  hunyuan_model_path: string
  hunyuan_subfolder: string
}
