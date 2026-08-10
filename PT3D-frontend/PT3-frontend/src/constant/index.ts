export const API_BASE =
  import.meta.env.VITE_API_URL ?? (import.meta.env.PROD ? '/api' : 'http://127.0.0.1:8000')

export const AUTH_REGISTER_URL = `${API_BASE}/auth/register`
export const AUTH_LOGIN_URL    = `${API_BASE}/auth/login`
export const AUTH_LOGOUT_URL   = `${API_BASE}/auth/logout`
export const AUTH_ME_URL       = `${API_BASE}/auth/me`
export const AUTH_CHANGE_PASSWORD_URL = `${API_BASE}/auth/change-password`
export const ADMIN_EXPORT_URL  = `${API_BASE}/admin/export.csv`
export const ADMIN_JOBS_URL    = `${API_BASE}/admin/jobs`
export const ADMIN_TRAINING_CONFIG_URL = `${API_BASE}/admin/training/config`
export const ADMIN_TRAINING_EXAMPLES_URL = `${API_BASE}/admin/training/examples`
export const ADMIN_TRAINING_EXPORT_URL = `${API_BASE}/admin/training/examples.csv`
export const GENERATE_URL     = `${API_BASE}/generate`
export const GENERATE_IMAGE_URL = `${API_BASE}/generate/image`
export const JOBS_URL         = `${API_BASE}/jobs`
export const JOB_STATUS_URL   = `${API_BASE}/status`      // GET /status/{job_id}
export const GLB_BY_ID_URL    = `${API_BASE}/glb`         // GET /glb/{job_id}.glb
export const LATEST_GLB_URL   = `${API_BASE}/latest.glb`  // GET /latest.glb
export const IMAGE_BY_ID_URL  = `${API_BASE}/image`       // GET /image/{job_id}
export const LATEST_IMAGE_URL = `${API_BASE}/latest-image`
