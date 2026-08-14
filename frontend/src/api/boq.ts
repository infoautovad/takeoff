import api from './client'
import type { BOQ } from '@/types'

export async function listBoqs(projectId: number): Promise<BOQ[]> {
  const { data } = await api.get<BOQ[]>(`/boq/projects/${projectId}`)
  return data
}

export async function generateBoq(
  projectId: number,
  options?: { documentIds?: number[] },
): Promise<BOQ> {
  const body =
    options?.documentIds && options.documentIds.length
      ? { document_ids: options.documentIds }
      : {}
  const { data } = await api.post<BOQ>(`/boq/projects/${projectId}/generate`, body, {
    timeout: 120000,
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

export async function downloadBoqExcel(boqId: number, filename: string): Promise<void> {
  await downloadBlob(`/boq/${boqId}/export/excel`, filename)
}

export async function downloadBoqCsv(boqId: number, filename: string): Promise<void> {
  await downloadBlob(`/boq/${boqId}/export/csv`, filename)
}

export async function updateBoqApproval(boqId: number, action: 'submit' | 'approve' | 'reject', note?: string) {
  const { data } = await api.post(`/boq/${boqId}/approval`, { action, note })
  return data as import('@/types').BOQ
}

export async function updateBoqItem(
  itemId: number,
  payload: {
    status?: string
    quantity?: number
    description?: string
    unit?: string
    item_code?: string | null
    notes?: string
  },
): Promise<import('@/types').BOQItem> {
  const { data } = await api.patch<import('@/types').BOQItem>(`/boq/items/${itemId}`, payload)
  return data
}
