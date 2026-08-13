import api from './client'
import type { AnalyticsParams, AnalyticsSnapshot, DashboardStats } from '@/types'

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const { data } = await api.get<DashboardStats>('/dashboard/stats')
  return data
}

export async function fetchAnalytics(params?: AnalyticsParams): Promise<AnalyticsSnapshot> {
  const { data } = await api.get<AnalyticsSnapshot>('/dashboard/analytics', { params })
  return data
}
