<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listNotifications, markAllRead, markRead, type NotificationItem } from '@/api/notifications'
import { formatDate } from '@/utils/format'

const router = useRouter()
const notes = ref<NotificationItem[]>([])
const loading = ref(true)

async function refresh() {
  loading.value = true
  try {
    notes.value = await listNotifications()
  } catch {
    notes.value = []
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

async function openNote(n: NotificationItem) {
  if (!n.is_read) await markRead(n.id)
  await refresh()
  if (n.project_id) router.push(`/projects/${n.project_id}`)
}

async function clearAll() {
  await markAllRead()
  await refresh()
}
</script>

<template>
  <div class="account-page">
    <div class="page-kicker">ACCOUNT</div>
    <div class="head-row">
      <div>
        <h1 class="brand-font page-title">Notifications</h1>
        <p class="page-lede">Project alerts, takeoff status, and review reminders.</p>
      </div>
      <button type="button" class="ghost" :disabled="!notes.length" @click="clearAll">Mark all read</button>
    </div>

    <div v-if="loading" class="empty">Loading notifications…</div>
    <div v-else-if="!notes.length" class="empty">No notifications yet.</div>
    <div v-else class="list">
      <button
        v-for="n in notes"
        :key="n.id"
        type="button"
        class="note"
        :class="{ unread: !n.is_read }"
        @click="openNote(n)"
      >
        <div class="note-top">
          <strong>{{ n.title }}</strong>
          <time>{{ formatDate(n.created_at) }}</time>
        </div>
        <p>{{ n.message }}</p>
      </button>
    </div>
  </div>
</template>

<style scoped>
.account-page {
  max-width: 820px;
}

.head-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.page-title {
  font-size: clamp(1.8rem, 3vw, 2.4rem);
  font-weight: 800;
  letter-spacing: -0.04em;
  margin: 6px 0 10px;
}

.page-lede {
  color: #8a9690;
  margin: 0 0 22px;
}

.ghost {
  border: 1px solid #31433b;
  background: transparent;
  color: #cdd6d0;
  padding: 10px 12px;
  font: 9px var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
}

.ghost:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.empty {
  border: 1px dashed #2a3a33;
  padding: 36px 20px;
  text-align: center;
  color: #748078;
  font-family: var(--font-mono);
  font-size: 11px;
}

.list {
  display: grid;
  gap: 8px;
}

.note {
  width: 100%;
  text-align: left;
  border: 1px solid #24322c;
  background: #0d1814;
  padding: 16px 18px;
  color: inherit;
  cursor: pointer;
}

.note:hover {
  border-color: #355045;
}

.note.unread {
  border-color: rgba(217, 255, 67, 0.28);
  background: rgba(217, 255, 67, 0.04);
}

.note-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.note-top strong {
  font-size: 0.92rem;
}

.note-top time {
  font-family: var(--font-mono);
  font-size: 9px;
  color: #68756e;
  white-space: nowrap;
}

.note p {
  margin: 0;
  color: #8a9690;
  font-size: 0.85rem;
  line-height: 1.5;
}
</style>
