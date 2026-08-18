import api from './client'
import { NO_HTTP_TIMEOUT } from './timeouts'

export async function listReports(projectId: number) {
  const { data } = await api.get(`/reports/projects/${projectId}`)
  return data
}

export async function generateReports(projectId: number) {
  const { data } = await api.post(`/reports/projects/${projectId}/generate`, null, {
    timeout: NO_HTTP_TIMEOUT,
  })
  return data
}
