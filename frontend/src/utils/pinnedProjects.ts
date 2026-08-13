const STORAGE_PREFIX = 'autovad.pinnedProjects.'

function storageKey(userId: number | string) {
  return `${STORAGE_PREFIX}${userId}`
}

export function loadPinnedProjectIds(userId: number | string | null | undefined): number[] {
  if (userId == null) return []
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((id) => Number(id)).filter((id) => Number.isFinite(id))
  } catch {
    return []
  }
}

export function savePinnedProjectIds(userId: number | string | null | undefined, ids: number[]) {
  if (userId == null) return
  const unique = [...new Set(ids)].slice(0, 20)
  localStorage.setItem(storageKey(userId), JSON.stringify(unique))
}

export function togglePinnedProjectId(
  userId: number | string | null | undefined,
  projectId: number,
): number[] {
  const current = loadPinnedProjectIds(userId)
  const next = current.includes(projectId)
    ? current.filter((id) => id !== projectId)
    : [projectId, ...current]
  savePinnedProjectIds(userId, next)
  return next
}
