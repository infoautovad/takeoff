import api from './client'
import { NO_HTTP_TIMEOUT } from './timeouts'

export async function compareBoqs(projectId: number, leftBoqId: number, rightBoqId: number) {
  const { data } = await api.post(
    `/compare/projects/${projectId}/boq`,
    {
      left_boq_id: leftBoqId,
      right_boq_id: rightBoqId,
    },
    { timeout: NO_HTTP_TIMEOUT },
  )
  return data
}

export async function compareDrawings(projectId: number, leftDocumentId: number, rightDocumentId: number) {
  const { data } = await api.post(
    `/compare/projects/${projectId}/drawings`,
    {
      left_document_id: leftDocumentId,
      right_document_id: rightDocumentId,
    },
    { timeout: NO_HTTP_TIMEOUT },
  )
  return data
}

export async function listComparisons(projectId: number) {
  const { data } = await api.get(`/compare/projects/${projectId}`)
  return data
}
