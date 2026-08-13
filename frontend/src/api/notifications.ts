import api from './client'

export interface NotificationItem {
  id: number
  user_id: number
  project_id: number | null
  title: string
  message: string
  category: string
  is_read: boolean
  created_at: string
}

export async function listNotifications(unreadOnly = false) {
  const { data } = await api.get<NotificationItem[]>('/notifications', { params: { unread_only: unreadOnly } })
  return data
}

export async function unreadCount() {
  const { data } = await api.get<{ count: number }>('/notifications/unread-count')
  return data.count
}

export async function markRead(id: number) {
  const { data } = await api.post<NotificationItem>(`/notifications/${id}/read`)
  return data
}

export async function markAllRead() {
  const { data } = await api.post<{ updated: number }>('/notifications/read-all')
  return data
}
