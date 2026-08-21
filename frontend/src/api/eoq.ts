import api from './client'
import { NO_HTTP_TIMEOUT } from './timeouts'
import type { EOQ } from '@/types'

export async function listEoqs(projectId: number): Promise<EOQ[]> {
  const { data } = await api.get<EOQ[]>(`/eoq/projects/${projectId}`)
  return data
}

export async function generateEoq(
  projectId: number,
  options?: { documentIds?: number[] },
): Promise<EOQ> {
  const body =
    options?.documentIds && options.documentIds.length
      ? { document_ids: options.documentIds }
      : {}
  const { data } = await api.post<EOQ>(`/eoq/projects/${projectId}/generate`, body, {
    timeout: NO_HTTP_TIMEOUT,
  })
  return data
}

async function downloadBlob(path: string, filename: string) {
  const { data } = await api.get(path, { responseType: 'blob' })
  const url = window.URL.createObjectURL(data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  window.URL.revokeObjectURL(url)
}

export async function downloadEoqExcel(eoqId: number, filename: string): Promise<void> {
  await downloadBlob(`/eoq/${eoqId}/export/excel`, filename)
}

export async function downloadEoqCsv(eoqId: number, filename: string): Promise<void> {
  await downloadBlob(`/eoq/${eoqId}/export/csv`, filename)
}

export async function updateEoqApproval(eoqId: number, action: 'submit' | 'approve' | 'reject', note?: string) {
  const { data } = await api.post(`/eoq/${eoqId}/approval`, { action, note })
  return data as import('@/types').EOQ
}

export async function updateEoqItem(
  itemId: number,
  payload: {
    status?: string
    quantity?: number
    description?: string
    unit?: string
    item_code?: string | null
    notes?: string
  },
): Promise<import('@/types').EOQItem> {
  const { data } = await api.patch<import('@/types').EOQItem>(`/eoq/items/${itemId}`, payload)
  return data
}
