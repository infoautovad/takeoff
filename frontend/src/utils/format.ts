export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Display quantities with exactly 2 decimal places (e.g. 2.46). */
export function formatQty(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(n)) return String(value)
  return n.toFixed(2)
}

export function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function statusColor(status: string): string {
  const map: Record<string, string> = {
    draft: 'secondary',
    active: 'success',
    in_review: 'warning',
    approved: 'primary',
    archived: 'grey',
    uploaded: 'secondary',
    queued: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'error',
  }
  return map[status] || 'secondary'
}

/** AutoVAD BOQ line status: Verified (>=97) or Engineer Review. */
export const BOQ_CONFIDENCE_VERIFIED_THRESHOLD = 97

export function boqItemStatusLabel(item: {
  status?: string | null
  confidence?: number | string | null
}): string {
  const status = String(item.status || '').toLowerCase()
  if (status === 'verified' || status === 'approved') return 'Verified'
  if (status === 'needs_review' || status === 'draft' || status === 'rejected') {
    return 'Engineer Review'
  }
  const conf =
    item.confidence === null || item.confidence === undefined || item.confidence === ''
      ? null
      : Number(item.confidence)
  if (conf != null && !Number.isNaN(conf) && conf >= BOQ_CONFIDENCE_VERIFIED_THRESHOLD) {
    return 'Verified'
  }
  return 'Engineer Review'
}

export function boqItemStatusColor(item: {
  status?: string | null
  confidence?: number | string | null
}): string {
  return boqItemStatusLabel(item) === 'Verified' ? 'success' : 'error'
}

export function standardBidItemNumber(item: {
  bid_template_line_id?: number | null
  item_code?: string | null
}): string {
  if (item.bid_template_line_id && item.item_code) return item.item_code
  return ''
}

export function isUnmappedBoqItem(item: {
  bid_template_line_id?: number | null
  category?: string | null
}): boolean {
  if (item.bid_template_line_id) return false
  return String(item.category || '').toLowerCase() === 'unmapped takeoff'
}
