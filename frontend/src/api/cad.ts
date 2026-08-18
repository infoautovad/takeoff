import api from './client'
import { NO_HTTP_TIMEOUT } from './timeouts'

export async function cadCapabilities() {
  const { data } = await api.get('/cad/capabilities')
  return data as CadCapabilities
}

export interface DesignAutomationStatus {
  enabled: boolean
  configured: boolean
  nickname: string | null
  engine: string
  modes: { dwg_to_dxf_script: boolean; civil_takeoff_appbundle: boolean }
  appbundle_zip: string | null
  preferred: string
  setup_hint?: string
}

export interface CadCapabilities {
  module: string
  enabled: boolean
  autodesk_aps_configured: boolean
  design_automation?: DesignAutomationStatus
  openai: { configured: boolean; model: string; mode: string }
  cad_openai_enrichment: boolean
  ready: {
    dxf_landxml_local: boolean
    dwg_via_aps: boolean
    dwg_via_design_automation?: boolean
    openai_enrichment: boolean
  }
  supported_now: Record<string, string>
  setup_hints?: Record<string, string>
}

export async function setupDesignAutomation() {
  const { data } = await api.post('/cad/design-automation/setup', null, { timeout: NO_HTTP_TIMEOUT })
  return data as {
    nickname: string
    engine: string
    dxf_activity: string
    plugin_activity: string | null
    plugin_error: string | null
    status: DesignAutomationStatus
  }
}

export async function listCadModels(projectId: number) {
  const { data } = await api.get(`/cad/projects/${projectId}`)
  return data as CadModel[]
}

export async function processCadDocument(documentId: number) {
  const { data } = await api.post(`/cad/documents/${documentId}/process`, null, {
    timeout: NO_HTTP_TIMEOUT,
  })
  return data as CadModel
}

export async function processAllCad(projectId: number) {
  const { data } = await api.post(`/cad/projects/${projectId}/process-all`, null, {
    timeout: NO_HTTP_TIMEOUT,
  })
  return data as CadModel[]
}

export interface CadModel {
  id: number
  project_id: number
  document_id: number
  source_format: string
  status: string
  engine: string
  units: string | null
  summary: string | null
  layers: Array<{ name?: string }>
  entities: Record<string, unknown>
  blocks: Array<Record<string, unknown>>
  dimensions: Array<Record<string, unknown>>
  texts: Array<Record<string, unknown>>
  tables: Array<Record<string, unknown>>
  stats: Record<string, unknown>
  quantities: Array<{
    id: number
    description: string
    category: string | null
    unit: string
    quantity: number
    layer: string | null
    entity_type: string | null
    calculation_method: string | null
    source_reference: string | null
    confidence: number | null
  }>
  error_message: string | null
  created_at: string
}
