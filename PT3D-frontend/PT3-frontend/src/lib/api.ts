import {
  ADMIN_EXPORT_URL,
  ADMIN_JOBS_URL,
  ADMIN_TRAINING_CONFIG_URL,
  ADMIN_TRAINING_EXAMPLES_URL,
  ADMIN_TRAINING_EXPORT_URL,
  AUTH_CHANGE_PASSWORD_URL,
  AUTH_LOGIN_URL,
  AUTH_LOGOUT_URL,
  AUTH_ME_URL,
  AUTH_REGISTER_URL,
  GENERATE_IMAGE_URL,
  GENERATE_URL,
  GLB_BY_ID_URL,
  IMAGE_BY_ID_URL,
  JOBS_URL,
  JOB_STATUS_URL,
  LATEST_GLB_URL,
} from '@/constant'
import type {
  AuthResponse,
  GenerateResponse,
  JobStatusResponse,
  JobSummary,
  QualityPreset,
  TrainingConfig,
  TrainingExample,
  TrainingFailureLabel,
  User,
} from '@/types'
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function readError(res: Response) {
  try {
    const data = (await res.json()) as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) {
      const messages = data.detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) return String(item.msg)
          return null
        })
        .filter((message): message is string => Boolean(message))
      if (messages.length) return messages.join('; ')
    }
  } catch {
    // Use the status text below.
  }
  return `${res.status} ${res.statusText}`.trim()
}

async function requestJson<T>(
  url: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const res = await fetch(url, { ...options, headers })
  if (!res.ok) throw new ApiError(res.status, await readError(res))
  return (await res.json()) as T
}

export async function fetchBlob(url: string, token: string): Promise<Blob> {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new ApiError(res.status, await readError(res))
  return res.blob()
}

export function register(body: {
  user_id: string
  password: string
  display_name?: string
}): Promise<AuthResponse> {
  return requestJson<AuthResponse>(AUTH_REGISTER_URL, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function login(body: { user_id: string; password: string }): Promise<AuthResponse> {
  return requestJson<AuthResponse>(AUTH_LOGIN_URL, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}


export function changePassword(
  token: string,
  body: { current_password: string; new_password: string },
): Promise<{ status: string }> {
  return requestJson<{ status: string }>(
    AUTH_CHANGE_PASSWORD_URL,
    { method: 'POST', body: JSON.stringify(body) },
    token,
  )
}
export function logout(token: string): Promise<{ status: string }> {
  return requestJson<{ status: string }>(AUTH_LOGOUT_URL, { method: 'POST' }, token)
}

export function me(token: string): Promise<User> {
  return requestJson<User>(AUTH_ME_URL, {}, token)
}

export function generate(
  prompt: string,
  token: string,
  quality_preset: QualityPreset = 'balanced',
): Promise<GenerateResponse> {
  return requestJson<GenerateResponse>(
    GENERATE_URL,
    { method: 'POST', body: JSON.stringify({ prompt, quality_preset }) },
    token,
  )
}

export function generateFromImage(
  image: File,
  prompt: string,
  token: string,
  quality_preset: QualityPreset = 'balanced',
): Promise<GenerateResponse> {
  return image.arrayBuffer().then((buffer) => {
    const bytes = new Uint8Array(buffer)
    const chunks: string[] = []
    const chunkSize = 0x8000
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + chunkSize)))
    }
    return requestJson<GenerateResponse>(
      GENERATE_IMAGE_URL,
      {
        method: 'POST',
        body: JSON.stringify({
          image_base64: btoa(chunks.join('')),
          content_type: image.type || 'image/png',
          prompt: prompt || 'Uploaded reference image',
          quality_preset,
        }),
      },
      token,
    )
  })
}

export function jobs(token: string): Promise<JobSummary[]> {
  return requestJson<JobSummary[]>(JOBS_URL, {}, token)
}

export function status(jobId: string, token: string): Promise<JobStatusResponse> {
  return requestJson<JobStatusResponse>(`${JOB_STATUS_URL}/${jobId}`, {}, token)
}

export function imageBlob(jobId: string, token: string): Promise<Blob> {
  return fetchBlob(`${IMAGE_BY_ID_URL}/${jobId}`, token)
}

export function glbBlob(jobId: string, token: string): Promise<Blob> {
  return fetchBlob(`${GLB_BY_ID_URL}/${jobId}.glb`, token)
}

export function latestGlbBlob(token: string): Promise<Blob> {
  return fetchBlob(LATEST_GLB_URL, token)
}

export function adminExportBlob(token: string): Promise<Blob> {
  return fetchBlob(ADMIN_EXPORT_URL, token)
}

export function adminJobs(token: string): Promise<JobSummary[]> {
  return requestJson<JobSummary[]>(ADMIN_JOBS_URL, {}, token)
}

export function trainingConfig(token: string): Promise<TrainingConfig> {
  return requestJson<TrainingConfig>(ADMIN_TRAINING_CONFIG_URL, {}, token)
}

export function trainingExamples(token: string): Promise<TrainingExample[]> {
  return requestJson<TrainingExample[]>(ADMIN_TRAINING_EXAMPLES_URL, {}, token)
}

export function createTrainingExample(
  token: string,
  body: {
    job_id: string
    failure_label: TrainingFailureLabel
    admin_notes?: string
    include_in_sdxl_lora?: boolean
    include_in_hunyuan?: boolean
    review_status?: string
  },
): Promise<TrainingExample> {
  return requestJson<TrainingExample>(
    ADMIN_TRAINING_EXAMPLES_URL,
    { method: 'POST', body: JSON.stringify(body) },
    token,
  )
}

export function adminTrainingExportBlob(token: string): Promise<Blob> {
  return fetchBlob(ADMIN_TRAINING_EXPORT_URL, token)
}
