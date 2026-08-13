import api from './client'
import type { Project, ProjectPayload } from '@/types'

export async function listProjects(params?: { q?: string; status_filter?: string }): Promise<Project[]> {
  const { data } = await api.get<Project[]>('/projects', { params })
  return data
}

export async function getProject(id: number): Promise<Project> {
  const { data } = await api.get<Project>(`/projects/${id}`)
  return data
}

export async function createProject(payload: ProjectPayload): Promise<Project> {
  const { data } = await api.post<Project>('/projects', payload)
  return data
}

export async function updateProject(id: number, payload: Partial<ProjectPayload>): Promise<Project> {
  const { data } = await api.patch<Project>(`/projects/${id}`, payload)
  return data
}

export async function archiveProject(id: number, hardDelete = false): Promise<void> {
  await api.delete(`/projects/${id}`, { params: { hard_delete: hardDelete } })
}

export async function listMembers(projectId: number) {
  const { data } = await api.get(`/projects/${projectId}/members`)
  return data as Array<{ id: number; user_id: number; email: string; full_name: string; role: string }>
}

export async function shareProject(projectId: number, email: string, role = 'engineer') {
  const { data } = await api.post(`/projects/${projectId}/share`, { email, role })
  return data
}
