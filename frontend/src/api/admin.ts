import api from './client'

export async function fetchAdminOverview() {
  const { data } = await api.get('/admin/overview')
  return data
}

export async function listAdminUsers() {
  const { data } = await api.get('/admin/users')
  return data as Array<{
    id: number
    email: string
    full_name: string
    role: string
    is_active: boolean
    is_blocked: boolean
    created_at: string
  }>
}

export async function updateAdminUser(userId: number, payload: { role?: string; is_blocked?: boolean; is_active?: boolean }) {
  const { data } = await api.patch(`/admin/users/${userId}`, payload)
  return data
}
