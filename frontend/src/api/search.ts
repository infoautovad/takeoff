import api from './client'

export async function globalSearch(q: string) {
  const { data } = await api.get('/search', { params: { q } })
  return data as {
    query: string
    projects: Array<{ id: number; name: string; status: string; location: string | null }>
    documents: Array<{ id: number; project_id: number; filename: string; status: string }>
    boq_items: Array<{ id: number; boq_id: number; description: string; quantity: number; unit: string; category: string | null }>
  }
}
