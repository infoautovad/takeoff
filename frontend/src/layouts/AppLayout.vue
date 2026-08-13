<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { listNotifications, markAllRead, markRead, unreadCount, type NotificationItem } from '@/api/notifications'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const navItems = computed(() => {
  const items = [
    { title: 'Dashboard', icon: 'mdi-view-dashboard-outline', to: '/dashboard' },
    { title: 'Projects', icon: 'mdi-folder-multiple-outline', to: '/projects' },
    { title: 'Analytics', icon: 'mdi-chart-bar', to: '/analytics' },
    { title: 'Search', icon: 'mdi-magnify', to: '/search' },
  ]
  if (auth.user?.role === 'admin') {
    items.push({ title: 'Admin', icon: 'mdi-shield-account-outline', to: '/admin' })
  }
  return items
})

const pageTitle = computed(() => {
  const map: Record<string, string> = {
    dashboard: 'Dashboard',
    projects: 'Projects',
    'project-detail': 'Project',
    analytics: 'Analytics',
    search: 'Search',
    admin: 'Admin',
    'document-viewer': 'Document Viewer',
  }
  return map[String(route.name)] || 'AutoVAD'
})

const pageKicker = computed(() => {
  const map: Record<string, string> = {
    dashboard: '01 / WORKSPACE',
    projects: '02 / PROJECTS',
    'project-detail': '02 / PROJECT DETAIL',
    analytics: '03 / ANALYTICS',
    search: '04 / SEARCH',
    admin: '05 / ADMIN',
    'document-viewer': '06 / VIEWER',
  }
  return map[String(route.name)] || 'AUTOVAD / APP'
})

const unread = ref(0)
const notes = ref<NotificationItem[]>([])
const menu = ref(false)

async function refreshNotifications() {
  try {
    unread.value = await unreadCount()
    notes.value = await listNotifications()
  } catch {
    unread.value = 0
  }
}

onMounted(refreshNotifications)

async function openNote(n: NotificationItem) {
  if (!n.is_read) await markRead(n.id)
  await refreshNotifications()
  if (n.project_id) router.push(`/projects/${n.project_id}`)
  menu.value = false
}

async function clearAll() {
  await markAllRead()
  await refreshNotifications()
}

function logout() {
  auth.logout()
  router.push({ name: 'landing' })
}
</script>

<template>
  <v-navigation-drawer permanent width="248" class="app-nav" :border="0">
    <router-link to="/" class="brand-block" aria-label="AutoVAD home">
      <div class="brand-mark" aria-hidden="true">
        <i /><i /><i />
      </div>
      <div>
        <div class="brand-name">Auto<span>VAD</span></div>
        <div class="brand-sub">Civil intelligence</div>
      </div>
    </router-link>

    <div class="nav-kicker">Navigate</div>
    <v-list nav density="compact" class="nav-list px-2">
      <v-list-item
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :prepend-icon="item.icon"
        :title="item.title"
        rounded="0"
        color="primary"
      />
    </v-list>

    <template #append>
      <div class="pa-3">
        <div class="user-card mb-3">
          <div class="user-label">Signed in</div>
          <div class="user-name">{{ auth.user?.full_name }}</div>
          <div class="user-email">{{ auth.user?.email }}</div>
          <div class="user-role">{{ auth.user?.role }}</div>
        </div>
        <v-btn block color="primary" prepend-icon="mdi-logout" @click="logout">Sign out</v-btn>
      </div>
    </template>
  </v-navigation-drawer>

  <v-app-bar flat class="app-topbar px-4" height="62">
    <div class="topbar-copy">
      <div class="page-kicker mb-0">{{ pageKicker }}</div>
      <v-app-bar-title class="brand-font topbar-title">{{ pageTitle }}</v-app-bar-title>
    </div>
    <v-spacer />
    <v-chip size="small" color="primary" variant="outlined" class="mr-3 d-none d-sm-inline-flex">
      Live workspace
    </v-chip>
    <v-menu v-model="menu" :close-on-content-click="false">
      <template #activator="{ props }">
        <v-btn v-bind="props" icon variant="text" class="notify-btn">
          <v-badge :content="unread" :model-value="unread > 0" color="primary">
            <v-icon>mdi-bell-outline</v-icon>
          </v-badge>
        </v-btn>
      </template>
      <v-card min-width="320" max-width="380" class="notify-card">
        <v-card-title class="d-flex justify-space-between align-center text-subtitle-2">
          Notifications
          <v-btn size="small" variant="text" color="primary" @click="clearAll">Mark all read</v-btn>
        </v-card-title>
        <v-divider />
        <v-list density="compact" max-height="360" style="overflow: auto">
          <v-list-item v-if="!notes.length" title="No notifications yet" />
          <v-list-item
            v-for="n in notes"
            :key="n.id"
            :title="n.title"
            :subtitle="n.message"
            :class="{ unread: !n.is_read }"
            @click="openNote(n)"
          />
        </v-list>
      </v-card>
    </v-menu>
  </v-app-bar>

  <v-main class="app-main cm-grid-bg">
    <div class="pa-6">
      <router-view />
    </div>
  </v-main>
</template>

<style scoped>
.app-nav {
  background: #0b1512 !important;
  color: #eaf0eb;
  border-right: 1px solid #24322c !important;
}

.app-nav :deep(.v-list-item-title) {
  font-family: var(--font-mono);
  font-size: 11px !important;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #9aa69f;
}

.app-nav :deep(.v-list-item__prepend) {
  color: #718078;
}

.app-nav :deep(.v-list-item:hover) {
  background: #12221c !important;
}

.app-nav :deep(.v-list-item--active) {
  background: #0e1d18 !important;
  box-shadow: inset 2px 0 var(--acid);
}

.app-nav :deep(.v-list-item--active .v-list-item-title),
.app-nav :deep(.v-list-item--active .v-list-item__prepend) {
  color: var(--acid) !important;
}

.brand-block {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 22px 18px 18px;
  border-bottom: 1px solid #24322c;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  transition: background 0.15s ease;
}

.brand-block:hover {
  background: rgba(217, 255, 67, 0.04);
}

.brand-mark {
  width: 29px;
  height: 27px;
  display: flex;
  gap: 3px;
  align-items: flex-end;
  transform: skew(-12deg);
}

.brand-mark i {
  display: block;
  width: 7px;
  background: var(--acid);
}

.brand-mark i:nth-child(1) { height: 16px; }
.brand-mark i:nth-child(2) { height: 25px; }
.brand-mark i:nth-child(3) { height: 20px; }

.brand-name {
  font-weight: 900;
  letter-spacing: -0.03em;
  font-size: 18px;
  color: #fff;
  line-height: 1;
}

.brand-name span {
  color: var(--acid);
}

.brand-sub {
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #68756e;
}

.nav-kicker {
  padding: 18px 18px 8px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #5f6e66;
}

.user-card {
  border: 1px solid #2a3a33;
  background: #0d1814;
  padding: 12px;
}

.user-label {
  font-family: var(--font-mono);
  font-size: 8px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--acid);
  margin-bottom: 8px;
}

.user-name {
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}

.user-email,
.user-role {
  font-family: var(--font-mono);
  font-size: 10px;
  color: #748078;
  margin-top: 4px;
}

.app-topbar {
  background: #0b1512 !important;
  border-bottom: 1px solid #24322c !important;
  color: #eaf0eb;
}

.topbar-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
}

.topbar-title {
  font-size: 1.15rem !important;
  font-weight: 800 !important;
  letter-spacing: -0.04em !important;
  padding-inline: 0 !important;
  margin-inline: 0 !important;
}

.app-topbar :deep(.v-toolbar-title) {
  margin-inline-start: 0;
}

.notify-btn {
  color: #9aa69f !important;
}

.notify-card {
  background: #101f1a !important;
}

.unread {
  background: rgba(217, 255, 67, 0.06);
}

.app-main {
  min-height: 100%;
}
</style>
