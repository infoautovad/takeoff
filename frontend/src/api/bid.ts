import api from './client'
import { NO_HTTP_TIMEOUT } from './timeouts'

export interface BidTemplateLine {
  id: number
  line_number: string
  csi_code: string | null
  item_code: string | null
  description: string
  unit: string
  default_rate: number | null
  sort_order: number
}

export interface BidTemplate {
  id: number
  project_id: number
  name: string
  source_filename: string | null
  is_active: boolean
  notes: string | null
  created_by: number
  created_at: string
  lines: BidTemplateLine[]
}

export interface BidMapResult {
  template_id: number
  template_name: string
  boq_id: number
  matched: number
  unmatched: number
  total: number
  details: Array<Record<string, unknown>>
}

export async function listBidTemplates(projectId: number): Promise<BidTemplate[]> {
  const { data } = await api.get<BidTemplate[]>(`/bid/projects/${projectId}/templates`)
  return data
}

export async function uploadBidTemplate(projectId: number, file: File, name?: string): Promise<BidTemplate> {
  const form = new FormData()
  form.append('file', file)
  if (name) form.append('name', name)
  const { data } = await api.post<BidTemplate>(`/bid/projects/${projectId}/templates/upload`, form, {
    timeout: NO_HTTP_TIMEOUT,
    maxBodyLength: Infinity,
    maxContentLength: Infinity,
  })
  return data
}

export async function activateBidTemplate(projectId: number, templateId: number): Promise<BidTemplate> {
  const { data } = await api.post<BidTemplate>(`/bid/projects/${projectId}/templates/${templateId}/activate`)
  return data
}

export async function deleteBidTemplate(projectId: number, templateId: number): Promise<void> {
  await api.delete(`/bid/projects/${projectId}/templates/${templateId}`)
}

export async function mapBoqToBid(projectId: number, boqId: number, templateId?: number): Promise<BidMapResult> {
  const { data } = await api.post<BidMapResult>(`/bid/projects/${projectId}/boq/${boqId}/map`, null, {
    params: templateId ? { template_id: templateId } : undefined,
    timeout: NO_HTTP_TIMEOUT,
  })
  return data
}

export async function fetchCsiCatalog() {
  const { data } = await api.get('/bid/csi-catalog')
  return data as { division_focus: string; items: Array<{ csi_code: string; category: string; unit_hint: string; keywords: string }> }
}
