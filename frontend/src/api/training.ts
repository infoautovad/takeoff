import api from './client'
import { NO_HTTP_TIMEOUT } from './timeouts'

export interface TrainingCaseSummary {
  id: number
  name: string
  description: string | null
  status: string
  sample_filename: string | null
  sample_file_size: number
  has_sample: boolean
  has_autovad_eoq?: boolean
  autovad_item_count?: number
  actual_engine?: string | null
  actual_notes?: string | null
  analyzed_at?: string | null
  has_expected: boolean
  expected_filename?: string | null
  expected_item_count: number
  can_evaluate?: boolean
  bid_catalog_count: number
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface TrainingReport {
  id: number
  metrics: Record<string, unknown> | null
  diffs: Record<string, unknown> | null
  training_guidance: string | null
  recall: string | null
  precision_proxy: string | null
  ai_generated: boolean
  created_at: string | null
}

export interface TrainingRun {
  id: number
  case_id: number
  status: string
  engine: string | null
  actual_item_count: number
  actual_items: Array<Record<string, unknown>>
  analysis_notes: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string | null
  report: TrainingReport | null
}

export interface TrainingCaseDetail extends TrainingCaseSummary {
  runs: TrainingRun[]
  expected: { items?: Array<Record<string, unknown>> } | null
  bid_catalog: Array<Record<string, unknown>> | null
  autovad_items?: Array<Record<string, unknown>>
}

export async function trainingOverview() {
  const { data } = await api.get('/training/overview')
  return data as {
    cases: number
    ready_cases: number
    runs: number
    completed_runs: number
    purpose: string
  }
}

export async function listTrainingCases(): Promise<TrainingCaseSummary[]> {
  const { data } = await api.get<TrainingCaseSummary[]>('/training/cases')
  return data
}

export async function createTrainingCase(payload: {
  name: string
  description?: string
  notes?: string
}): Promise<TrainingCaseSummary> {
  const { data } = await api.post<TrainingCaseSummary>('/training/cases', payload)
  return data
}

export async function getTrainingCase(id: number): Promise<TrainingCaseDetail> {
  const { data } = await api.get<TrainingCaseDetail>(`/training/cases/${id}`)
  return data
}

export async function deleteTrainingCase(id: number): Promise<void> {
  await api.delete(`/training/cases/${id}`)
}

export async function uploadTrainingSample(
  caseId: number,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<TrainingCaseDetail> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<TrainingCaseDetail>(`/training/cases/${caseId}/sample`, form, {
    timeout: NO_HTTP_TIMEOUT,
    maxBodyLength: Infinity,
    maxContentLength: Infinity,
    onUploadProgress: (event) => {
      if (!onProgress) return
      if (typeof event.progress === 'number') {
        onProgress(Math.min(99, Math.round(event.progress * 100)))
        return
      }
      if (event.total) {
        onProgress(Math.min(99, Math.round((event.loaded / event.total) * 100)))
      }
    },
  })
  onProgress?.(100)
  return data
}

export async function uploadExpectedFile(
  caseId: number,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<TrainingCaseDetail> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<TrainingCaseDetail>(`/training/cases/${caseId}/expected`, form, {
    timeout: NO_HTTP_TIMEOUT,
    maxBodyLength: Infinity,
    maxContentLength: Infinity,
    onUploadProgress: (event) => {
      if (!onProgress) return
      if (typeof event.progress === 'number') {
        onProgress(Math.min(99, Math.round(event.progress * 100)))
        return
      }
      if (event.total) {
        onProgress(Math.min(99, Math.round((event.loaded / event.total) * 100)))
      }
    },
  })
  onProgress?.(100)
  return data
}

export async function analyzeTrainingCase(
  caseId: number,
  options?: { signal?: AbortSignal },
): Promise<TrainingCaseDetail> {
  const { data } = await api.post<TrainingCaseDetail>(`/training/cases/${caseId}/analyze`, null, {
    timeout: NO_HTTP_TIMEOUT,
    signal: options?.signal,
  })
  return data
}

export async function evaluateTrainingCase(caseId: number): Promise<TrainingRun> {
  const { data } = await api.post<TrainingRun>(`/training/cases/${caseId}/evaluate`, null, {
    timeout: NO_HTTP_TIMEOUT,
  })
  return data
}

export async function runTrainingCase(caseId: number): Promise<TrainingRun> {
  const { data } = await api.post<TrainingRun>(`/training/cases/${caseId}/run`, null, {
    timeout: NO_HTTP_TIMEOUT,
  })
  return data
}

export async function getTrainingRun(runId: number): Promise<TrainingRun> {
  const { data } = await api.get<TrainingRun>(`/training/runs/${runId}`)
  return data
}
