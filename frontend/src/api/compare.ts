import api from './client'

export async function compareBoqs(projectId: number, leftBoqId: number, rightBoqId: number) {
  const { data } = await api.post(`/compare/projects/${projectId}/boq`, {
    left_boq_id: leftBoqId,
    right_boq_id: rightBoqId,
  })
  return data
}

export async function compareDrawings(projectId: number, leftDocumentId: number, rightDocumentId: number) {
  const { data } = await api.post(`/compare/projects/${projectId}/drawings`, {
    left_document_id: leftDocumentId,
    right_document_id: rightDocumentId,
  })
  return data
}

export async function listComparisons(projectId: number) {
  const { data } = await api.get(`/compare/projects/${projectId}`)
  return data
}
