import api from './client'

export async function listReports(projectId: number) {
  const { data } = await api.get(`/reports/projects/${projectId}`)
  return data
}

export async function generateReports(projectId: number) {
  const { data } = await api.post(`/reports/projects/${projectId}/generate`)
  return data
}
