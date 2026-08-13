import api from './client'

export async function listSor(projectId: number) {
  const { data } = await api.get(`/cost/projects/${projectId}/sor`)
  return data as Array<{ id: number; item_code: string | null; description: string; unit: string; rate: number }>
}

export async function uploadSor(projectId: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post(`/cost/projects/${projectId}/sor/upload`, form)
  return data
}

export async function createEstimate(projectId: number, boqId: number) {
  const { data } = await api.post(`/cost/projects/${projectId}/estimate/${boqId}`)
  return data as {
    id: number
    title: string
    currency: string
    total_amount: number
    breakdown: { items?: Array<Record<string, unknown>>; category_totals?: Record<string, number> }
  }
}

export async function listEstimates(projectId: number) {
  const { data } = await api.get(`/cost/projects/${projectId}/estimates`)
  return data
}
