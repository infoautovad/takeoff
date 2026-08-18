import api from './client'
import { NO_HTTP_TIMEOUT } from './timeouts'
import type { AnalysisResult, ChatMessage, ProcessResult } from '@/types'

export async function analyzeDocument(
  documentId: number,
  options?: { signal?: AbortSignal },
): Promise<ProcessResult> {
  const { data } = await api.post<ProcessResult>(`/ai/documents/${documentId}/analyze`, null, {
    timeout: NO_HTTP_TIMEOUT,
    signal: options?.signal,
  })
  return data
}

export async function analyzeProject(
  projectId: number,
  options?: { signal?: AbortSignal },
): Promise<ProcessResult[]> {
  const { data } = await api.post<ProcessResult[]>(`/ai/projects/${projectId}/analyze`, null, {
    timeout: NO_HTTP_TIMEOUT,
    signal: options?.signal,
  })
  return data
}

export async function listAnalyses(projectId: number): Promise<AnalysisResult[]> {
  const { data } = await api.get<AnalysisResult[]>(`/ai/projects/${projectId}/analyses`)
  return data
}

export async function listChat(projectId: number): Promise<ChatMessage[]> {
  const { data } = await api.get<ChatMessage[]>(`/ai/projects/${projectId}/chat`)
  return data
}

export async function askChat(projectId: number, question: string): Promise<ChatMessage> {
  const { data } = await api.post<ChatMessage>(
    `/ai/projects/${projectId}/chat`,
    { question },
    { timeout: NO_HTTP_TIMEOUT },
  )
  return data
}

export async function intelligenceStatus(): Promise<IntelligenceStatus> {
  const { data } = await api.get<IntelligenceStatus>('/ai/status')
  return data
}

export interface IntelligenceStatus {
  openai: { configured: boolean; model: string; mode: string }
  autodesk_aps: { configured: boolean; bucket: string; client_id_set: boolean }
  design_automation?: {
    enabled: boolean
    configured: boolean
    preferred?: string
    modes?: { dwg_to_dxf_script: boolean; civil_takeoff_appbundle: boolean }
    setup_hint?: string
  }
  cad_engine_enabled: boolean
  cad_openai_enrichment: boolean
  modes: Record<string, string>
  setup_hints: { openai: string; autodesk_aps: string; design_automation?: string }
}
