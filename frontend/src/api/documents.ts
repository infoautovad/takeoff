import api from './client'
import type { DocumentItem } from '@/types'

export async function listDocuments(projectId: number): Promise<DocumentItem[]> {
  const { data } = await api.get<DocumentItem[]>(`/documents/project/${projectId}`)
  return data
}

export async function uploadDocument(
  projectId: number,
  file: File,
  revisionLabel?: string,
  notes?: string,
): Promise<DocumentItem> {
  const form = new FormData()
  form.append('file', file)
  if (revisionLabel) form.append('revision_label', revisionLabel)
  if (notes) form.append('notes', notes)
  const { data } = await api.post<DocumentItem>(`/documents/project/${projectId}/upload`, form)
  return data
}

export async function deleteDocument(documentId: number): Promise<void> {
  await api.delete(`/documents/${documentId}`)
}

export async function downloadDocument(documentId: number, filename: string): Promise<void> {
  const { data } = await api.get(`/documents/${documentId}/download`, {
    responseType: 'blob',
  })
  const url = window.URL.createObjectURL(data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  window.URL.revokeObjectURL(url)
}

export async function getViewerMeta(documentId: number) {
  const { data } = await api.get(`/documents/${documentId}/viewer`)
  return data as {
    id: number
    filename: string
    document_type: string
    page_count: number
    processing_status: string
    has_pdf_preview: boolean
    text_pages: Array<{ page: number; text: string }>
    summary: string | null
  }
}

export async function getPageImageUrl(documentId: number, page: number): Promise<string> {
  const { data } = await api.get(`/documents/${documentId}/pages/${page}/image`, { responseType: 'blob' })
  return window.URL.createObjectURL(data)
}
