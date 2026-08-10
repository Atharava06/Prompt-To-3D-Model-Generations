import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import * as api from '@/lib/api'
import type {
  JobStatus,
  JobSummary,
  QualityPreset,
  TrainingConfig,
  TrainingExample,
  TrainingFailureLabel,
  User,
  ViewerHandle,
} from '@/types'

const TOKEN_KEY = 'pt3_access_token'
const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === 'true'
const DEV_TOKEN = 'dev-auth-disabled'
const DEV_USER: User = {
  user_id: 'dev',
  display_name: 'Dev User',
  created_at: '2026-01-01T00:00:00+00:00',
}

const ThreeViewer = lazy(() => import('@/components/Viewer/ThreeViewer'))

const STATUS_LABELS: Record<JobStatus, string> = {
  queued: 'Queued',
  sdxl_running: 'Generating image',
  converting: 'Converting to 3D',
  done: 'Ready',
  failed: 'Failed',
}

const QUALITY_LABELS: Record<QualityPreset, string> = {
  fast: 'Fast',
  balanced: 'Balanced',
  quality: 'Quality',
}

const GENERATION_STEPS = [
  'Understanding Your Prompt',
  'Generating Concept Image',
  'Converting Image to 3D Model',
  'Optimizing & Building GLB',
  'Preparing Interactive Viewport',
  '3D Model Ready for Preview',
]

const TRAINING_LABELS: Record<TrainingFailureLabel, string> = {
  bad_image: 'Bad image',
  bad_shape: 'Bad shape',
  bad_texture: 'Bad texture',
  missing_parts: 'Missing parts',
  wrong_category: 'Wrong category',
  preview_failed: 'Preview failed',
  good_reference: 'Good reference',
}

type AppView = 'create' | 'models' | 'viewer' | 'profile'
type AuthMode = 'login' | 'signup'

function ArrowIcon({ direction = 'down' }: { direction?: 'down' | 'up' }) {
  return (
    <svg
      className={`arrow-icon arrow-icon-${direction}`}
      xmlns="http://www.w3.org/2000/svg"
      width="15"
      height="18"
      viewBox="0 0 15 18"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M8.36377 1C8.36377 0.447715 7.91605 7.24234e-08 7.36377 0C6.81148 -7.24234e-08 6.36377 0.447715 6.36377 1L7.36377 1L8.36377 1ZM6.65666 17.7071C7.04718 18.0976 7.68035 18.0976 8.07087 17.7071L14.4348 11.3431C14.8254 10.9526 14.8254 10.3195 14.4348 9.92893C14.0443 9.53841 13.4111 9.53841 13.0206 9.92893L7.36377 15.5858L1.70691 9.92893C1.31639 9.53841 0.683225 9.53841 0.292701 9.92893C-0.0978239 10.3195 -0.097824 10.9526 0.2927 11.3431L6.65666 17.7071ZM7.36377 1L6.36377 1L6.36377 17L7.36377 17L8.36377 17L8.36377 1L7.36377 1Z"
        fill="currentColor"
      />
    </svg>
  )
}

function EyeIcon() {
  return (
    <svg
      className="eye-icon"
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M2.25 12C3.72 8.64 7.12 6.25 12 6.25C16.88 6.25 20.28 8.64 21.75 12C20.28 15.36 16.88 17.75 12 17.75C7.12 17.75 3.72 15.36 2.25 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3.25" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg
      className="refresh-icon"
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M15.75 8.25C15.75 4.94 13.06 2.25 9.75 2.25C7.72 2.25 5.93 3.26 4.85 4.8L3.75 3.7V7.5H7.55L5.93 5.88C6.73 4.6 8.14 3.75 9.75 3.75C12.23 3.75 14.25 5.77 14.25 8.25C14.25 10.73 12.23 12.75 9.75 12.75C8.02 12.75 6.52 11.77 5.77 10.33L4.44 11.02C5.44 12.94 7.44 14.25 9.75 14.25C13.06 14.25 15.75 11.56 15.75 8.25Z"
        fill="currentColor"
      />
    </svg>
  )
}

export default function App() {
  const viewerRef = useRef<ViewerHandle>(null)
  const fullViewerRef = useRef<ViewerHandle>(null)
  const imageUploadInputRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const viewerObjectUrlRef = useRef<string | null>(null)
  const fullViewerObjectUrlRef = useRef<string | null>(null)
  const generatedImageObjectUrlRef = useRef<string | null>(null)
  const selectedViewerImageObjectUrlRef = useRef<string | null>(null)
  const autoLoadedCreateJobRef = useRef<string | null>(null)
  const imageUrlsRef = useRef<Record<string, string>>({})
  const imagePreviewRunRef = useRef(0)

  const [booting, setBooting] = useState(true)
  const [token, setToken] = useState<string | null>(() =>
    AUTH_DISABLED ? DEV_TOKEN : localStorage.getItem(TOKEN_KEY),
  )
  const [user, setUser] = useState<User | null>(() => (AUTH_DISABLED ? DEV_USER : null))
  const [authMode, setAuthMode] = useState<AuthMode>('login')
  const [authError, setAuthError] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  const [authForm, setAuthForm] = useState({
    user_id: '',
    password: '',
    display_name: '',
  })
  const [passwordForm, setPasswordForm] = useState({ current_password: '', new_password: '' })
  const [passwordLoading, setPasswordLoading] = useState(false)

  const [activeView, setActiveView] = useState<AppView>('create')
  const [prompt, setPrompt] = useState('')
  const [qualityPreset, setQualityPreset] = useState<QualityPreset>('balanced')
  const [status, setStatus] = useState('Ready')
  const [rotationLabel, setRotationLabel] = useState('Auto rotate on')
  const [modelLoaded, setModelLoaded] = useState(false)
  const [fullModelLoaded, setFullModelLoaded] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [activeGenerationJobId, setActiveGenerationJobId] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [generationStepIndex, setGenerationStepIndex] = useState(0)
  const [generatedImageUrl, setGeneratedImageUrl] = useState<string | null>(null)
  const [selectedViewerImageUrl, setSelectedViewerImageUrl] = useState<string | null>(null)
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [jobsLoading, setJobsLoading] = useState(false)
  const [imageUrls, setImageUrls] = useState<Record<string, string>>({})
  const [visibleModelCount, setVisibleModelCount] = useState(6)
  const [adminJobs, setAdminJobs] = useState<JobSummary[]>([])
  const [trainingExamples, setTrainingExamples] = useState<TrainingExample[]>([])
  const [trainingConfig, setTrainingConfig] = useState<TrainingConfig | null>(null)
  const [trainingLoading, setTrainingLoading] = useState(false)

  const stats = useMemo(() => {
    const completed = jobs.filter((job) => job.status === 'done').length
    const failed = jobs.filter((job) => job.status === 'failed').length
    return { total: jobs.length, completed, failed }
  }, [jobs])

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const revokeImagePreviews = useCallback(() => {
    Object.values(imageUrlsRef.current).forEach((url) => URL.revokeObjectURL(url))
    imageUrlsRef.current = {}
    setImageUrls({})
  }, [])

  const revokeViewerUrl = useCallback((urlRef: { current: string | null }) => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
  }, [])

  const clearSession = useCallback(() => {
    stopPoll()
    imagePreviewRunRef.current += 1
    revokeImagePreviews()
    revokeViewerUrl(viewerObjectUrlRef)
    revokeViewerUrl(fullViewerObjectUrlRef)
    revokeViewerUrl(selectedViewerImageObjectUrlRef)
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
    setJobs([])
    setActiveGenerationJobId(null)
    setGeneratedImageUrl(null)
    setSelectedViewerImageUrl(null)
    setPrompt('')
    setStatus('Ready')
    setModelLoaded(false)
    autoLoadedCreateJobRef.current = null
    setGenerationStepIndex(0)
    revokeViewerUrl(generatedImageObjectUrlRef)
    setActiveView('create')
  }, [revokeImagePreviews, revokeViewerUrl, stopPoll])

  const refreshJobs = useCallback(
    async (activeToken = token) => {
      if (!activeToken) return
      setJobsLoading(true)

      try {
        const nextJobs = await api.jobs(activeToken)
        const previewRunId = imagePreviewRunRef.current + 1
        imagePreviewRunRef.current = previewRunId
        setJobs(nextJobs)

        void (async () => {
          const nextImageUrls: Record<string, string> = {}

          await Promise.all(
            nextJobs.map(async (job) => {
              if (!job.has_image) return
              try {
                const blob = await api.imageBlob(job.job_id, activeToken)
                nextImageUrls[job.job_id] = URL.createObjectURL(blob)
              } catch {
                // A job can report an image that disappears during cleanup; omit its thumbnail.
              }
            }),
          )

          if (imagePreviewRunRef.current !== previewRunId) {
            Object.values(nextImageUrls).forEach((url) => URL.revokeObjectURL(url))
            return
          }

          revokeImagePreviews()
          imageUrlsRef.current = nextImageUrls
          setImageUrls(nextImageUrls)
        })()
      } catch (error) {
        if (error instanceof api.ApiError && error.status === 401) clearSession()
      } finally {
        setJobsLoading(false)
      }
    },
    [clearSession, revokeImagePreviews, token],
  )

  const waitForViewer = useCallback(
    async (targetRef: { current: ViewerHandle | null }) => {
      for (let attempt = 0; attempt < 100; attempt += 1) {
        if (targetRef.current) return targetRef.current
        await new Promise((resolve) => window.setTimeout(resolve, 100))
      }
      return null
    },
    [],
  )

  const loadModelBlob = useCallback(
    async (
      blob: Blob,
      successMessage: string,
      targetRef: { current: ViewerHandle | null } = viewerRef,
      urlRef: { current: string | null } = viewerObjectUrlRef,
    ) => {
      const viewer = await waitForViewer(targetRef)
      if (!viewer) {
        setStatus('3D viewer is still loading. Please try again.')
        return false
      }
      const objectUrl = URL.createObjectURL(blob)
      const loaded = await viewer.loadGLBFromUrl(objectUrl, successMessage)
      if (loaded) {
        revokeViewerUrl(urlRef)
        urlRef.current = objectUrl
      } else {
        URL.revokeObjectURL(objectUrl)
      }
      return Boolean(loaded)
    },
    [revokeViewerUrl, waitForViewer],
  )

  const loadJobModel = useCallback(
    async (jobId: string, activeToken = token) => {
      if (!activeToken) return false
      setStatus('Loading model')
      try {
        const blob = await api.glbBlob(jobId, activeToken)
        const loaded = await loadModelBlob(blob, '3D model loaded')
        if (loaded) setModelLoaded(true)
        return loaded
      } catch (error) {
        setStatus(error instanceof Error ? error.message : 'Model could not load')
        return false
      }
    },
    [loadModelBlob, token],
  )

  const loadJobImage = useCallback(
    async (jobId: string, activeToken = token) => {
      if (!activeToken) return false
      try {
        const blob = await api.imageBlob(jobId, activeToken)
        const objectUrl = URL.createObjectURL(blob)
        revokeViewerUrl(generatedImageObjectUrlRef)
        generatedImageObjectUrlRef.current = objectUrl
        setGeneratedImageUrl(objectUrl)
        return true
      } catch (error) {
        if (error instanceof api.ApiError && error.status === 404) return false
        return false
      }
    },
    [revokeViewerUrl, token],
  )

  const openJobInViewer = async (jobId: string) => {
    setSelectedJobId(jobId)
    setSelectedViewerImageUrl(null)
    revokeViewerUrl(selectedViewerImageObjectUrlRef)
    setFullModelLoaded(false)
    setStatus('Loading model')
    setActiveView('viewer')
  }

  useEffect(() => {
    if (activeView !== 'viewer' || !selectedJobId || !token) return
    let cancelled = false

    const loadSelectedModel = async () => {
      setStatus('Loading model')
      try {
        const selectedJob = jobs.find((job) => job.job_id === selectedJobId)

        if (selectedJob?.has_image) {
          try {
            const imageBlob = await api.imageBlob(selectedJobId, token)
            if (!cancelled) {
              const imageUrl = URL.createObjectURL(imageBlob)
              revokeViewerUrl(selectedViewerImageObjectUrlRef)
              selectedViewerImageObjectUrlRef.current = imageUrl
              setSelectedViewerImageUrl(imageUrl)
            }
          } catch {
            // Keep loading the GLB even if the SDXL preview is unavailable.
          }
        }

        const blob = await api.glbBlob(selectedJobId, token)
        if (cancelled) return
        setFullModelLoaded(false)
        const loaded = await loadModelBlob(
          blob,
          '3D model loaded',
          fullViewerRef,
          fullViewerObjectUrlRef,
        )
        if (!cancelled && loaded) setFullModelLoaded(true)
      } catch (error) {
        if (!cancelled) setStatus(error instanceof Error ? error.message : 'Model could not load')
      }
    }

    loadSelectedModel()

    return () => {
      cancelled = true
    }
  }, [activeView, jobs, loadModelBlob, revokeViewerUrl, selectedJobId, token])

  const startPolling = useCallback(
    (jobId: string, activeToken: string) => {
      stopPoll()
      pollRef.current = setInterval(async () => {
        try {
          const nextStatus = await api.status(jobId, activeToken)
          setStatus(STATUS_LABELS[nextStatus.status] ?? nextStatus.status)
          await refreshJobs(activeToken)

          if (nextStatus.status === 'queued') {
            setGenerationStepIndex(0)
          } else if (nextStatus.status === 'sdxl_running') {
            setGenerationStepIndex(1)
          } else if (nextStatus.status === 'converting') {
            setGenerationStepIndex(2)
            await loadJobImage(jobId, activeToken)
          } else if (nextStatus.status === 'done') {
            stopPoll()
            setGenerationStepIndex(3)
            const imageLoaded =
              generatedImageObjectUrlRef.current !== null || (await loadJobImage(jobId, activeToken))
            if (imageLoaded) {
              setGenerationStepIndex(4)
            }
            const loaded = await loadJobModel(jobId, activeToken)
            if (loaded) {
              setGenerationStepIndex(5)
            }
            setGenerating(false)
          } else if (nextStatus.status === 'failed') {
            stopPoll()
            setStatus(`Failed: ${nextStatus.error ?? 'unknown error'}`)
            setGenerating(false)
          }
        } catch (error) {
          if (error instanceof api.ApiError && error.status === 401) {
            stopPoll()
            setGenerating(false)
            clearSession()
          }
        }
      }, 3000)
    },
    [clearSession, loadJobImage, loadJobModel, refreshJobs, stopPoll],
  )

  useEffect(() => {
    if (AUTH_DISABLED) {
      setToken(DEV_TOKEN)
      setUser(DEV_USER)
      void refreshJobs(DEV_TOKEN).finally(() => {
        setBooting(false)
      })
      return
    }

    const savedToken = localStorage.getItem(TOKEN_KEY)
    if (!savedToken) {
      setBooting(false)
      return
    }

    api
      .me(savedToken)
      .then((nextUser) => {
        setToken(savedToken)
        setUser(nextUser)
        return refreshJobs(savedToken)
      })
      .catch(() => {
        clearSession()
      })
      .finally(() => {
        setBooting(false)
      })
  }, [clearSession, refreshJobs])

  useEffect(() => {
    return () => {
      stopPoll()
      revokeImagePreviews()
      revokeViewerUrl(viewerObjectUrlRef)
      revokeViewerUrl(fullViewerObjectUrlRef)
      revokeViewerUrl(generatedImageObjectUrlRef)
      revokeViewerUrl(selectedViewerImageObjectUrlRef)
    }
  }, [revokeImagePreviews, revokeViewerUrl, stopPoll])

  useEffect(() => {
    if (activeView !== 'create' || !token || generating || modelLoaded) return

    const latestReadyJob = jobs.find((job) => job.status === 'done' && job.has_glb)
    if (!latestReadyJob || autoLoadedCreateJobRef.current === latestReadyJob.job_id) return

    let cancelled = false
    const jobId = latestReadyJob.job_id
    autoLoadedCreateJobRef.current = jobId

    const loadLatestIntoCreate = async () => {
      setActiveGenerationJobId(jobId)
      setGenerationStepIndex(3)

      if (latestReadyJob.has_image) {
        await loadJobImage(jobId, token)
        if (!cancelled) setGenerationStepIndex(4)
      }

      if (cancelled) return
      const loaded = await loadJobModel(jobId, token)
      if (!cancelled && loaded) {
        setGenerationStepIndex(5)
      } else if (!loaded) {
        autoLoadedCreateJobRef.current = null
      }
    }

    void loadLatestIntoCreate()

    return () => {
      cancelled = true
    }
  }, [activeView, generating, jobs, loadJobImage, loadJobModel, modelLoaded, token])

  useEffect(() => {
    const latestImageJob = jobs.find((job) => job.has_image)
    if (!token || !latestImageJob || generatedImageUrl) return
    void loadJobImage(latestImageJob.job_id, token)
  }, [generatedImageUrl, jobs, loadJobImage, token])

  useEffect(() => {
    const activeJob = activeGenerationJobId
      ? jobs.find((job) => job.job_id === activeGenerationJobId)
      : null

    if (!activeJob || modelLoaded) return

    if (activeJob.status === 'queued') {
      setGenerationStepIndex(0)
    } else if (activeJob.status === 'sdxl_running') {
      setGenerationStepIndex(1)
    } else if (activeJob.status === 'converting') {
      setGenerationStepIndex(2)
    } else if (activeJob.status === 'done') {
      setGenerationStepIndex(generatedImageUrl ? 4 : 3)
    }
  }, [activeGenerationJobId, generatedImageUrl, jobs, modelLoaded])

  const handleAuthSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAuthLoading(true)
    setAuthError('')

    try {
      const response =
        authMode === 'signup'
          ? await api.register({
              user_id: authForm.user_id,
              password: authForm.password,
              display_name: authForm.display_name || undefined,
            })
          : await api.login({
              user_id: authForm.user_id,
              password: authForm.password,
            })

      localStorage.setItem(TOKEN_KEY, response.access_token)
      setToken(response.access_token)
      setUser(response.user)
      setAuthForm({ user_id: '', password: '', display_name: '' })
      await refreshJobs(response.access_token)
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Authentication failed')
    } finally {
      setAuthLoading(false)
    }
  }


  const handleChangePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!token || passwordLoading) return
    setPasswordLoading(true)
    try {
      await api.changePassword(token, passwordForm)
      setPasswordForm({ current_password: '', new_password: '' })
      setStatus('Password updated')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Password update failed')
    } finally {
      setPasswordLoading(false)
    }
  }
  const handleLogout = async () => {
    if (AUTH_DISABLED) {
      setActiveView('create')
      setStatus('Auth disabled for local development')
      return
    }

    const activeToken = token
    if (activeToken) {
      try {
        await api.logout(activeToken)
      } catch {
        // Local cleanup still matters if the server is unreachable.
      }
    }
    clearSession()
  }

  const handleGenerate = async () => {
    const text = prompt.trim()
    if (!text || !token || generating) return

    stopPoll()
    setGenerating(true)
    setModelLoaded(false)
    autoLoadedCreateJobRef.current = null
    setGenerationStepIndex(0)
    viewerRef.current?.clearModel()
    revokeViewerUrl(viewerObjectUrlRef)
    setStatus('Sending')

    try {
      const response = await api.generate(text, token, qualityPreset)
      setActiveGenerationJobId(response.job_id)
      setGeneratedImageUrl(null)
      revokeViewerUrl(generatedImageObjectUrlRef)
      setStatus(`Queued (${QUALITY_LABELS[response.quality_preset]})`)
      await refreshJobs(token)
      startPolling(response.job_id, token)
    } catch (error) {
      setGenerating(false)
      setStatus(error instanceof Error ? error.message : 'Generation failed')
    }
  }

  const handleImageUpload = async (file: File | undefined) => {
    if (!file || !token || generating) return
    if (!file.type.startsWith('image/')) {
      setStatus('Upload a PNG, JPEG, or WebP image')
      return
    }

    stopPoll()
    setGenerating(true)
    setModelLoaded(false)
    autoLoadedCreateJobRef.current = null
    setGenerationStepIndex(2)
    viewerRef.current?.clearModel()
    revokeViewerUrl(viewerObjectUrlRef)
    revokeViewerUrl(generatedImageObjectUrlRef)

    const previewUrl = URL.createObjectURL(file)
    generatedImageObjectUrlRef.current = previewUrl
    setGeneratedImageUrl(previewUrl)
    setStatus('Uploading image')

    try {
      const response = await api.generateFromImage(
        file,
        prompt.trim() || file.name.replace(/\.[^.]+$/, '') || 'Uploaded reference image',
        token,
        qualityPreset,
      )
      setActiveGenerationJobId(response.job_id)
      setStatus(`Converting uploaded image (${QUALITY_LABELS[response.quality_preset]})`)
      await refreshJobs(token)
      startPolling(response.job_id, token)
    } catch (error) {
      setGenerating(false)
      setStatus(error instanceof Error ? error.message : 'Image upload failed')
    } finally {
      if (imageUploadInputRef.current) imageUploadInputRef.current.value = ''
    }
  }

  const handleLoadLatest = async () => {
    if (!token) return
    setStatus('Loading latest model')
    setGenerationStepIndex(4)
    try {
      const latestReadyJob = jobs.find((job) => job.status === 'done' && job.has_glb)
      if (latestReadyJob) {
        setActiveGenerationJobId(latestReadyJob.job_id)
        if (latestReadyJob.has_image) await loadJobImage(latestReadyJob.job_id, token)
      }
      const blob = latestReadyJob
        ? await api.glbBlob(latestReadyJob.job_id, token)
        : await api.latestGlbBlob(token)
      const loaded = await loadModelBlob(blob, 'Loaded latest model')
      if (loaded) {
        setModelLoaded(true)
        setGenerationStepIndex(5)
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'No model ready')
    }
  }

  const handleDownload = async (job: JobSummary) => {
    if (!token || !job.has_glb) return
    try {
      const blob = await api.glbBlob(job.job_id, token)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${job.job_id}.glb`
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Download failed')
    }
  }


  const refreshTrainingAdmin = useCallback(
    async (activeToken = token) => {
      if (!activeToken || user?.user_id !== 'admin') return
      setTrainingLoading(true)
      try {
        const [nextJobs, nextExamples, nextConfig] = await Promise.all([
          api.adminJobs(activeToken),
          api.trainingExamples(activeToken),
          api.trainingConfig(activeToken),
        ])
        setAdminJobs(nextJobs)
        setTrainingExamples(nextExamples)
        setTrainingConfig(nextConfig)
      } catch (error) {
        setStatus(error instanceof Error ? error.message : 'Training admin refresh failed')
      } finally {
        setTrainingLoading(false)
      }
    },
    [token, user?.user_id],
  )

  const markTrainingExample = async (job: JobSummary, failureLabel: TrainingFailureLabel) => {
    if (!token) return
    try {
      await api.createTrainingExample(token, {
        job_id: job.job_id,
        failure_label: failureLabel,
        include_in_sdxl_lora: failureLabel === 'bad_image' || failureLabel === 'good_reference',
        include_in_hunyuan: failureLabel !== 'bad_image',
        review_status: 'candidate',
      })
      await refreshTrainingAdmin(token)
      setStatus('Training example saved')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Training example failed')
    }
  }

  const handleTrainingExport = async () => {
    if (!token) return
    try {
      const blob = await api.adminTrainingExportBlob(token)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'training-examples.csv'
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Training export failed')
    }
  }
  const handleAdminExport = async () => {
    if (!token) return
    try {
      const blob = await api.adminExportBlob(token)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'prompt-to-3d-export.csv'
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Export failed')
    }
  }

  if (booting) {
    return (
      <div className="auth-page">
        <div className="auth-panel auth-loading">
          <span className="loader-dot" />
          <p>Opening studio...</p>
        </div>
      </div>
    )
  }

  if (!token || !user) {
    const isSignup = authMode === 'signup'
    return (
      <div className="auth-page">
        <section className={`auth-panel ${isSignup ? 'signup-panel' : ''}`}>
          <div className="auth-copy">
            <h1>{isSignup ? 'Get Started Now' : 'Welcome back!'}</h1>
            {!isSignup && <p>Enter your Credentials to access your account</p>}
          </div>
          <form className="auth-form" onSubmit={handleAuthSubmit}>
            <label>
              User ID
              <input
                autoComplete="username"
                value={authForm.user_id}
                onChange={(event) => setAuthForm({ ...authForm, user_id: event.target.value })}
                placeholder="Enter your User ID"
              />
            </label>
            {isSignup && (
              <label>
                Display name
                <input
                  value={authForm.display_name}
                  onChange={(event) =>
                    setAuthForm({ ...authForm, display_name: event.target.value })
                  }
                  placeholder="Enter your Display name"
                />
              </label>
            )}
            <label>
              <span className="password-label-row">
                Password
                {!isSignup && (
                  <button className="forgot-link" type="button">
                    forgot password
                  </button>
                )}
              </span>
              <input
                autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}
                type="password"
                value={authForm.password}
                onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })}
                placeholder="8+ characters"
              />
            </label>
            {authError && <p className="form-error">{authError}</p>}
            <button className="auth-submit" disabled={authLoading} type="submit">
              {authLoading ? 'Working...' : isSignup ? 'Create account' : 'Login'}
            </button>
          </form>
          <div className="auth-divider">
            <span />
            <small>Or</small>
            <span />
          </div>
          <p className="auth-switch">
            {isSignup ? 'Have an account?' : "Don’t have an account?"}
            <button
              onClick={() => setAuthMode(isSignup ? 'login' : 'signup')}
              type="button"
            >
              {isSignup ? 'Sign In' : 'Sign Up'}
            </button>
          </p>
        </section>
        <aside className="auth-visual" aria-label="Prompt to 3D product preview">
          <div className="auth-visual-art" aria-hidden="true" />
          <div className={`auth-visual-copy ${isSignup ? 'signup-visual-copy' : 'login-visual-copy'}`}>
            <img className="auth-visual-mark" src="/icon.png" alt="" aria-hidden="true" />
            {isSignup ? (
              <>
                <h2>
                  Transform Ideas
                  <br />
                  Into 3D Reality
                </h2>
                <p>Generate production-ready 3D models from simple text prompts in minutes.</p>
              </>
            ) : (
              <>
                <h2>
                  Create 3D Assets
                  <br />
                  at the Speed of Thought
                </h2>
                <p>Describe your vision and watch it become a fully explorable 3D model.</p>
              </>
            )}
          </div>
        </aside>
      </div>
    )
  }

  const latestGlbJob = jobs.find((job) => job.status === 'done' && job.has_glb)
  const visibleJobs = jobs.slice(0, visibleModelCount)
  const hasMoreModels = jobs.length > visibleModelCount
  const isModelsEmpty = !jobsLoading && visibleJobs.length === 0
  const modelPlaceholders = jobsLoading ? Math.max(0, 6 - visibleJobs.length) : 0
  const modelsFooterLabel = hasMoreModels ? 'LOAD MORE >' : jobsLoading ? 'LOADING...' : 'REFRESH'
  const selectedJob = jobs.find((job) => job.job_id === selectedJobId)
  const isNavActive = (view: AppView) => activeView === view || (activeView === 'viewer' && view === 'models')

  return (
    <div className={`studio-root ${activeView === 'create' ? 'generation-studio-root' : ''} ${activeView === 'models' ? 'models-studio-root' : ''} ${activeView === 'viewer' ? 'full-model-studio-root' : ''} ${activeView === 'profile' ? 'profile-studio-root' : ''}`}>
      {activeView === 'profile' && (
        <header className="generation-header profile-header">
          <button className="generation-logo" onClick={() => setActiveView('create')} type="button" aria-label="Prompt to 3D home">
            <img src="/generation-logo.svg" alt="3DMG" />
          </button>

          <nav className="generation-tabs profile-tabs" aria-label="Studio navigation">
            {(['create', 'models', 'profile'] as AppView[]).map((view) => (
              <button
                className={isNavActive(view) ? 'active' : ''}
                key={view}
                onClick={() => setActiveView(view)}
                type="button"
              >
                {view === 'create' ? 'Create' : view === 'models' ? 'My Models' : 'Profile'}
              </button>
            ))}
          </nav>

          <button className="generation-profile" onClick={() => setActiveView('profile')} type="button" aria-label={`Open profile for ${user.display_name}`}>
            <img src="/generation-avatar.png" alt="" aria-hidden="true" />
          </button>
        </header>
      )}

      {activeView === 'models' && (
        <main className="models-root">
          <header className="models-header">
            <button className="generation-logo" onClick={() => setActiveView('create')} type="button" aria-label="Prompt to 3D home">
              <img src="/generation-logo.svg" alt="3DMG" />
            </button>

            <nav className="generation-tabs models-tabs" aria-label="Studio navigation">
              {(['create', 'models', 'profile'] as AppView[]).map((view) => (
                <button
                  className={isNavActive(view) ? 'active' : ''}
                  key={view}
                  onClick={() => setActiveView(view)}
                  type="button"
                >
                  {view === 'create' ? 'Create' : view === 'models' ? 'My Models' : 'Profile'}
                </button>
              ))}
            </nav>

            <button className="generation-profile" onClick={() => setActiveView('profile')} type="button" aria-label={`Open profile for ${user.display_name}`}>
              <img src="/generation-avatar.png" alt="" aria-hidden="true" />
            </button>
          </header>

          <section className="models-hero" aria-label="My generated 3D models">
            <h1>My generated 3D models</h1>
            <button
              className="models-refresh-button"
              onClick={() => refreshJobs()}
              type="button"
              aria-label={jobsLoading ? 'Refreshing models' : 'Refresh models'}
              title="Refresh"
            >
              <RefreshIcon />
            </button>
          </section>

          <section className="models-gallery" aria-label="Generated model gallery">
            {visibleJobs.map((job) => (
              <article className="models-gallery-card" key={job.job_id}>
                <div className="models-card-preview">
                  {imageUrls[job.job_id] ? (
                    <img src={imageUrls[job.job_id]} alt={job.prompt || 'Generated model image'} />
                  ) : (
                    <span>{job.status === 'done' ? 'Image preview unavailable' : STATUS_LABELS[job.status]}</span>
                  )}
                </div>
                <div className="models-card-actions">
                  <button
                    disabled={!job.has_glb}
                    onClick={() => openJobInViewer(job.job_id)}
                    type="button"
                    aria-label={`View ${job.prompt || 'model'} in 3D`}
                    title="View in 3D"
                  >
                    <EyeIcon />
                  </button>
                  <button
                    disabled={!job.has_glb}
                    onClick={() => handleDownload(job)}
                    type="button"
                    aria-label={`Download ${job.prompt || 'model'} GLB`}
                    title="Download GLB"
                  >
                    <ArrowIcon />
                  </button>
                </div>
              </article>
            ))}

            {isModelsEmpty && (
              <div className="models-empty-state" role="status">
                <h2>No generated models yet</h2>
                <p>Finished 3D models will show here with mobile-ready view and download actions.</p>
                <button onClick={() => refreshJobs()} type="button">
                  Refresh models
                </button>
              </div>
            )}

            {Array.from({ length: modelPlaceholders }).map((_, index) => (
              <article className="models-gallery-card is-placeholder" key={`placeholder-${index}`}>
                <div className="models-card-preview" aria-hidden="true" />
              </article>
            ))}
          </section>

          {(jobs.length > 0 || jobsLoading) && (
            <button
              className="models-load-more"
              disabled={jobsLoading}
              onClick={() => {
                if (hasMoreModels) setVisibleModelCount((count) => count + 6)
                else refreshJobs()
              }}
              type="button"
            >
              {modelsFooterLabel}
            </button>
          )}
        </main>
      )}

      {activeView === 'viewer' && (
        <main className="full-model-root">
          <header className="models-header">
            <button className="generation-logo" onClick={() => setActiveView('create')} type="button" aria-label="Prompt to 3D home">
              <img src="/generation-logo.svg" alt="3DMG" />
            </button>

            <nav className="generation-tabs models-tabs" aria-label="Studio navigation">
              {(['create', 'models', 'profile'] as AppView[]).map((view) => (
                <button
                  className={isNavActive(view) ? 'active' : ''}
                  key={view}
                  onClick={() => setActiveView(view)}
                  type="button"
                >
                  {view === 'create' ? 'Create' : view === 'models' ? 'My Models' : 'Profile'}
                </button>
              ))}
            </nav>

            <button className="generation-profile" onClick={() => setActiveView('profile')} type="button" aria-label={`Open profile for ${user.display_name}`}>
              <img src="/generation-avatar.png" alt="" aria-hidden="true" />
            </button>
          </header>

          <h1 className="full-model-title">Generated Model</h1>

          <section className="full-model-workspace" aria-label={`Generated model viewer. ${status}. ${rotationLabel}`}>
            <div className={`full-model-main-viewer ${fullModelLoaded ? 'has-model' : ''}`}>
              <img className="generation-stage-art" src="/generation-stage.png" alt="" aria-hidden="true" />
              <div className={`generation-viewer-canvas ${fullModelLoaded ? 'is-loaded' : 'is-empty'}`}>
                <Suspense fallback={<div className="viewer-loader">Loading 3D viewer</div>}>
                  <ThreeViewer
                    ref={fullViewerRef}
                    onStatusChange={(message) => setStatus(message)}
                    onRotationChange={(message) => setRotationLabel(message)}
                    onModelLoaded={() => setFullModelLoaded(true)}
                  />
                </Suspense>
              </div>
              <button
                className="full-model-download"
                disabled={!selectedJob?.has_glb}
                onClick={() => selectedJob && handleDownload(selectedJob)}
                type="button"
                aria-label="Download selected GLB"
                title="Download GLB"
              >
                <ArrowIcon />
              </button>
            </div>

            <aside className="full-model-side-panel" aria-label="Selected model progress">
              <div className="full-model-side-preview">
                {selectedViewerImageUrl || (selectedJobId && imageUrls[selectedJobId]) ? (
                  <img
                    className="full-model-side-image"
                    src={selectedViewerImageUrl || (selectedJobId ? imageUrls[selectedJobId] : '')}
                    alt={selectedJob?.prompt || 'Generated SDXL preview'}
                  />
                ) : (
                  <img
                    className="full-model-side-placeholder"
                    src="/generation-side-preview.png"
                    alt=""
                    aria-hidden="true"
                  />
                )}
                <button
                  disabled={!selectedJob?.has_glb}
                  onClick={() => selectedJob && handleDownload(selectedJob)}
                  type="button"
                  aria-label="Download selected model"
                  title="Download GLB"
                >
                  <ArrowIcon />
                </button>
              </div>

              <ol className="generation-steps full-model-steps">
                {GENERATION_STEPS.map((step) => (
                  <li className="generation-step complete" key={step}>
                    <span aria-hidden="true" />
                    <p>{step}</p>
                  </li>
                ))}
              </ol>
            </aside>
          </section>
        </main>
      )}

      {activeView === 'create' && (
        <main className="generation-root">
          <header className="generation-header">
            <button className="generation-logo" onClick={() => setActiveView('create')} type="button" aria-label="Prompt to 3D home">
              <img src="/generation-logo.svg" alt="Prompt to 3D" />
            </button>

            <nav className="generation-tabs" aria-label="Studio navigation">
              {(['create', 'models', 'profile'] as AppView[]).map((view) => (
                <button
                  className={isNavActive(view) ? 'active' : ''}
                  key={view}
                  onClick={() => setActiveView(view)}
                  type="button"
                >
                  {view === 'create' ? 'Create' : view === 'models' ? 'My Models' : 'Profile'}
                </button>
              ))}
            </nav>

            <button className="generation-profile" onClick={() => setActiveView('profile')} type="button" aria-label={`Open profile for ${user.display_name}`}>
              <img src="/generation-avatar.png" alt="" aria-hidden="true" />
            </button>
          </header>

          <section className="generation-workspace" aria-label={`3D generation workspace. ${status}. ${rotationLabel}`}>
            <div className={`generation-main-viewer ${modelLoaded ? 'has-model' : ''}`}>
              <img className="generation-stage-art" src="/generation-stage.png" alt="" aria-hidden="true" />
              <div className={`generation-viewer-canvas ${modelLoaded ? 'is-loaded' : 'is-empty'}`}>
                <Suspense fallback={<div className="viewer-loader">Loading 3D viewer</div>}>
                  <ThreeViewer
                    ref={viewerRef}
                    onStatusChange={(message) => setStatus(message)}
                    onRotationChange={(message) => setRotationLabel(message)}
                    onModelLoaded={() => setModelLoaded(true)}
                  />
                </Suspense>
              </div>
              <div className="generation-viewer-actions">
                <button
                  className="generation-download-button"
                  disabled={!latestGlbJob}
                  onClick={() => latestGlbJob && handleDownload(latestGlbJob)}
                  type="button"
                  aria-label="Download GLB"
                  title="Download GLB"
                >
                  <ArrowIcon />
                </button>
              </div>
            </div>

            <aside className="generation-side-panel" aria-label="Generation progress">
              <div className="generation-side-preview">
                {generatedImageUrl ? (
                  <img
                    className="generation-side-preview-image"
                    src={generatedImageUrl}
                    alt={
                      activeGenerationJobId
                        ? `Generated SDXL preview for job ${activeGenerationJobId}`
                        : 'Generated SDXL preview'
                    }
                  />
                ) : (
                  <img
                    className="generation-side-preview-placeholder"
                    src="/generation-side-preview.png"
                    alt=""
                    aria-hidden="true"
                  />
                )}
                <button onClick={handleLoadLatest} type="button" aria-label="Load latest model in preview">
                  <ArrowIcon />
                </button>
              </div>

              <ol className="generation-steps">
                {GENERATION_STEPS.map((step, index) => (
                  <li
                    className={`generation-step ${index < generationStepIndex ? 'complete' : ''} ${index === generationStepIndex ? 'active' : ''}`}
                    key={step}
                  >
                    <span aria-hidden="true" />
                    <p>{step}</p>
                  </li>
                ))}
              </ol>
            </aside>
          </section>

          <section className="generation-prompt-box" aria-label="Prompt composer">
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') handleGenerate()
              }}
              placeholder="Describe the prompt here"
              rows={1}
            />
            <div className="generation-prompt-actions">
              <input
                ref={imageUploadInputRef}
                className="sr-only"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={(event) => handleImageUpload(event.target.files?.[0])}
                aria-label="Upload image for 3D generation"
              />
              <button
                className="generation-icon-button"
                disabled={generating}
                onClick={() => imageUploadInputRef.current?.click()}
                type="button"
                aria-label="Upload image and skip image generation"
                title="Upload image"
              >
                <span aria-hidden="true">+</span>
              </button>
              <div className="generation-quality" aria-label="Generation quality">
                {(['fast', 'balanced', 'quality'] as QualityPreset[]).map((preset) => (
                  <button
                    className={qualityPreset === preset ? 'active' : ''}
                    key={preset}
                    onClick={() => setQualityPreset(preset)}
                    type="button"
                  >
                    {QUALITY_LABELS[preset]}
                  </button>
                ))}
              </div>
              <button
                className="generation-send-button"
                disabled={generating || !prompt.trim()}
                onClick={handleGenerate}
                type="button"
                aria-label="Generate 3D model"
                title="Send"
              >
                <span className="sr-only">{generating ? 'Sending' : 'Send'}</span>
                <ArrowIcon direction="up" />
              </button>
            </div>
          </section>
        </main>
      )}
      {activeView === 'profile' && (
        <main className="profile-root">
          <section className="profile-hero" aria-label="My profile">
            <h1>My Profile</h1>
            <button
              className="profile-refresh-button"
              onClick={() => refreshJobs()}
              type="button"
              aria-label={jobsLoading ? 'Refreshing profile stats' : 'Refresh profile stats'}
              title="Refresh"
            >
              <RefreshIcon />
            </button>
          </section>

          <section className="profile-grid" aria-label="Profile overview">
            <article className="profile-card">
              <img className="profile-avatar" src="/generation-avatar.png" alt="" aria-hidden="true" />
              <h2>{user.display_name}</h2>
              <p className="profile-handle">@{user.user_id}</p>

              <form className="password-change-form" onSubmit={handleChangePassword}>
                <label>
                  Current password
                  <input
                    autoComplete="current-password"
                    type="password"
                    value={passwordForm.current_password}
                    onChange={(event) =>
                      setPasswordForm({ ...passwordForm, current_password: event.target.value })
                    }
                    placeholder="Current password"
                  />
                </label>
                <label>
                  New password
                  <input
                    autoComplete="new-password"
                    type="password"
                    value={passwordForm.new_password}
                    onChange={(event) =>
                      setPasswordForm({ ...passwordForm, new_password: event.target.value })
                    }
                    placeholder="12+ chars with mixed types"
                  />
                </label>
                <button
                  className="profile-action-button"
                  disabled={passwordLoading || !passwordForm.current_password || !passwordForm.new_password}
                  type="submit"
                >
                  {passwordLoading ? 'Updating...' : 'Change password'}
                </button>
              </form>

              <div className="profile-card-actions">
                {user.user_id === 'admin' && (
                  <button className="profile-secondary-button" onClick={handleAdminExport} type="button">
                    Export data sheet
                  </button>
                )}
                <button className="profile-secondary-button" onClick={handleLogout} type="button">
                  Log out
                </button>
              </div>
            </article>

            <section className="stats-card" aria-label="Generation statistics">
              <div>
                <p>Total generations</p>
                <span>{stats.total}</span>
              </div>
              <div>
                <p>Completed models</p>
                <span>{stats.completed}</span>
              </div>
              <div>
                <p>Failed jobs</p>
                <span>{stats.failed}</span>
              </div>
            </section>
          </section>

          {user.user_id === 'admin' && (
            <section className="training-card profile-admin-card">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Fine-tuning dataset</p>
                  <h2>Products / props review</h2>
                </div>
                <button className="profile-secondary-button" onClick={() => refreshTrainingAdmin()} type="button">
                  {trainingLoading ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>
              <div className="training-status-grid">
                <span>Examples: {trainingExamples.length}</span>
                <span>SDXL LoRA: {trainingConfig?.sdxl_lora_enabled ? 'Enabled' : 'Disabled'}</span>
                <span>Hunyuan tuned: {trainingConfig?.hunyuan_finetuned_enabled ? 'Enabled' : 'Disabled'}</span>
              </div>
              <div className="training-actions">
                <button className="profile-secondary-button" onClick={handleTrainingExport} type="button">
                  Export training CSV
                </button>
              </div>
              <div className="training-review-list">
                {adminJobs.slice(0, 8).map((job) => (
                  <article key={job.job_id}>
                    <div>
                      <span className={`status-chip status-${job.status}`}>{STATUS_LABELS[job.status]}</span>
                      <p>{job.prompt}</p>
                    </div>
                    <div className="training-label-buttons">
                      {(['bad_image', 'bad_shape', 'missing_parts', 'preview_failed', 'good_reference'] as TrainingFailureLabel[]).map((label) => (
                        <button key={label} onClick={() => markTrainingExample(job, label)} type="button">
                          {TRAINING_LABELS[label]}
                        </button>
                      ))}
                    </div>
                  </article>
                ))}
                {!adminJobs.length && <p className="muted">Refresh to load jobs for review.</p>}
              </div>
            </section>
          )}
        </main>
      )}
    </div>
  )
}
