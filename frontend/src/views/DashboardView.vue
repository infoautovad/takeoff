<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDashboardStats } from '@/api/dashboard'
import type { DashboardStats, Project } from '@/types'
import { formatDate, statusColor } from '@/utils/format'
import { loadPinnedProjectIds, togglePinnedProjectId } from '@/utils/pinnedProjects'
import { useAuthStore } from '@/stores/auth'
import { useProjectsStore } from '@/stores/projects'

const auth = useAuthStore()
const projectsStore = useProjectsStore()
const router = useRouter()
const loading = ref(true)
const stats = ref<DashboardStats | null>(null)
const hoveredStat = ref<string | null>(null)
const pinnedIds = ref<number[]>([])

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
})

const firstName = computed(() => auth.user?.full_name?.split(' ')[0] || 'Engineer')

const readiness = computed(() => {
  if (!stats.value) return 0
  const s = stats.value
  let score = 0
  if (s.total_projects > 0) score += 20
  if (s.documents_uploaded > 0) score += 25
  if (s.boqs_generated > 0) score += 30
  if (s.active_projects > 0) score += 15
  if (!(s.needs_attention?.length)) score += 10
  return Math.min(100, score)
})

const readinessLabel = computed(() => {
  const r = readiness.value
  if (r >= 80) return 'Workspace primed'
  if (r >= 50) return 'Takeoff in progress'
  if (r > 0) return 'Getting started'
  return 'Create your first project'
})

const pinnedProjects = computed(() => {
  const map = new Map(projectsStore.projects.map((p) => [p.id, p]))
  return pinnedIds.value.map((id) => map.get(id)).filter(Boolean) as Project[]
})

const recentProjects = computed(() => {
  const pinned = new Set(pinnedIds.value)
  return projectsStore.projects.filter((p) => !pinned.has(p.id)).slice(0, 4)
})

const attentionItems = computed(() => stats.value?.needs_attention || [])
const week = computed(
  () =>
    stats.value?.week || {
      documents_uploaded: 0,
      boqs_generated: 0,
      projects_touched: 0,
      failed_uploads: 0,
    },
)

const cards = computed(() => [
  {
    key: 'total_projects' as const,
    label: 'Total projects',
    icon: 'mdi-folder-multiple-outline',
    hint: 'Open project library',
    to: '/projects',
    accent: 'acid',
  },
  {
    key: 'active_projects' as const,
    label: 'Active projects',
    icon: 'mdi-briefcase-check-outline',
    hint: 'Jobs currently in motion',
    to: '/projects',
    accent: 'mint',
  },
  {
    key: 'documents_uploaded' as const,
    label: 'Documents',
    icon: 'mdi-file-document-outline',
    hint: 'Plans, CAD & schedules',
    to: '/projects',
    accent: 'acid',
  },
  {
    key: 'boqs_generated' as const,
    label: 'Estimates Of Quantities generated',
    icon: 'mdi-table-large',
    hint: 'Review quantity outputs',
    to: '/projects',
    accent: 'mint',
  },
  {
    key: 'pending_reviews' as const,
    label: 'Pending reviews',
    icon: 'mdi-clipboard-check-outline',
    hint: 'Items waiting on you',
    to: '/projects',
    accent: 'warn',
  },
])

const quickActions = [
  {
    title: 'New project',
    desc: 'Start a USA civil takeoff workspace',
    icon: 'mdi-plus-box-outline',
    to: '/projects',
    primary: true,
  },
  {
    title: 'Open projects',
    desc: 'Browse and continue existing jobs',
    icon: 'mdi-folder-open-outline',
    to: '/projects',
  },
  {
    title: 'Analytics',
    desc: 'Quantities, earthwork & cost signals',
    icon: 'mdi-chart-timeline-variant',
    to: '/analytics',
  },
  {
    title: 'Search',
    desc: 'Find drawings, Estimate Of Quantities items, materials',
    icon: 'mdi-magnify',
    to: '/search',
  },
]

const displayCounts = ref<Record<string, number>>({
  total_projects: 0,
  active_projects: 0,
  documents_uploaded: 0,
  boqs_generated: 0,
  pending_reviews: 0,
})

function animateCounts(target: DashboardStats) {
  const keys = [
    'total_projects',
    'active_projects',
    'documents_uploaded',
    'boqs_generated',
    'pending_reviews',
  ] as const
  const duration = 700
  const start = performance.now()
  const from = { ...displayCounts.value }

  function frame(now: number) {
    const t = Math.min(1, (now - start) / duration)
    const eased = 1 - (1 - t) ** 3
    for (const key of keys) {
      displayCounts.value[key] = Math.round(from[key] + (target[key] - from[key]) * eased)
    }
    if (t < 1) requestAnimationFrame(frame)
  }
  requestAnimationFrame(frame)
}

watch(stats, (value) => {
  if (value) animateCounts(value)
})

onMounted(async () => {
  pinnedIds.value = loadPinnedProjectIds(auth.user?.id)
  try {
    const [dash] = await Promise.all([
      fetchDashboardStats(),
      projectsStore.fetchProjects().catch(() => undefined),
    ])
    stats.value = dash
  } finally {
    loading.value = false
  }
})

function isPinned(id: number) {
  return pinnedIds.value.includes(id)
}

function togglePin(projectId: number, event?: Event) {
  event?.stopPropagation()
  pinnedIds.value = togglePinnedProjectId(auth.user?.id, projectId)
}

function openActivity(item: DashboardStats['recent_activity'][number]) {
  if (item.project_id) router.push(`/projects/${item.project_id}`)
}

function openAttention(item: NonNullable<DashboardStats['needs_attention']>[number]) {
  router.push(`/projects/${item.project_id}`)
}

function actionIcon(action: string) {
  const a = action.toLowerCase()
  if (a.includes('upload') || a.includes('document')) return 'mdi-file-upload-outline'
  if (a.includes('boq')) return 'mdi-table-large'
  if (a.includes('cad')) return 'mdi-vector-polyline'
  if (a.includes('analy')) return 'mdi-brain'
  if (a.includes('share')) return 'mdi-account-multiple-outline'
  if (a.includes('project')) return 'mdi-folder-outline'
  return 'mdi-flash-outline'
}

function severityIcon(kind: string) {
  if (kind === 'failed_upload') return 'mdi-alert-circle-outline'
  if (kind === 'empty_boq' || kind === 'missing_boq') return 'mdi-table-off'
  return 'mdi-clipboard-text-clock-outline'
}
</script>

<template>
  <div class="page-shell dash">
    <section class="hero surface-panel">
      <div class="hero-copy">
        <div class="page-kicker mb-2">01 / Workspace</div>
        <h1 class="brand-font hero-title">
          {{ greeting }}, <span>{{ firstName }}</span>
        </h1>
        <p class="hero-lede muted mb-0">
          Your AutoVAD control deck — pin active bids, clear blockers, and keep takeoffs moving.
        </p>
      </div>
      <div class="hero-side">
        <div class="readiness">
          <div class="readiness-top">
            <span>Workspace readiness</span>
            <b>{{ readiness }}%</b>
          </div>
          <div class="readiness-track" aria-hidden="true">
            <i :style="{ width: `${readiness}%` }" />
          </div>
          <small>{{ readinessLabel }}</small>
        </div>
        <v-btn color="primary" size="large" prepend-icon="mdi-plus" class="hero-cta" @click="router.push('/projects')">
          New project
        </v-btn>
      </div>
      <div class="hero-orb" aria-hidden="true" />
    </section>

    <div v-if="loading" class="text-center py-16">
      <v-progress-circular indeterminate color="primary" size="40" />
      <div class="muted mt-3 text-caption">Loading workspace signals…</div>
    </div>

    <template v-else>
      <section class="stat-grid">
        <button
          v-for="(card, index) in cards"
          :key="card.key"
          type="button"
          class="stat-card"
          :class="[card.accent, { hot: hoveredStat === card.key }]"
          :style="{ animationDelay: `${index * 60}ms` }"
          @mouseenter="hoveredStat = card.key"
          @mouseleave="hoveredStat = null"
          @focus="hoveredStat = card.key"
          @blur="hoveredStat = null"
          @click="router.push(card.to)"
        >
          <div class="stat-card-head">
            <span>{{ card.label }}</span>
            <v-icon size="18">{{ card.icon }}</v-icon>
          </div>
          <div class="stat-value">{{ displayCounts[card.key] }}</div>
          <div class="stat-hint">{{ card.hint }} <span>→</span></div>
        </button>
      </section>

      <section class="week-strip surface-panel">
        <div class="week-label">
          <div class="page-kicker mb-1">This week</div>
          <strong>Last 7 days</strong>
        </div>
        <div class="week-metric">
          <b>{{ week.documents_uploaded }}</b>
          <span>Files uploaded</span>
        </div>
        <div class="week-metric">
          <b>{{ week.boqs_generated }}</b>
          <span>Estimates Of Quantities generated</span>
        </div>
        <div class="week-metric">
          <b>{{ week.projects_touched }}</b>
          <span>Projects touched</span>
        </div>
        <div class="week-metric" :class="{ alert: week.failed_uploads > 0 }">
          <b>{{ week.failed_uploads }}</b>
          <span>Failed uploads</span>
        </div>
      </section>

      <v-row class="mt-2" dense>
        <v-col cols="12" lg="7">
          <section class="surface-panel panel">
            <div class="panel-head">
              <div>
                <div class="page-kicker mb-1">Quick actions</div>
                <h2 class="brand-font panel-title">What do you want to do?</h2>
              </div>
            </div>
            <div class="action-grid">
              <button
                v-for="action in quickActions"
                :key="action.title"
                type="button"
                class="action-card"
                :class="{ primary: action.primary }"
                @click="router.push(action.to)"
              >
                <v-icon size="22">{{ action.icon }}</v-icon>
                <div>
                  <strong>{{ action.title }}</strong>
                  <small>{{ action.desc }}</small>
                </div>
              </button>
            </div>
          </section>

          <section v-if="pinnedProjects.length" class="surface-panel panel mt-4">
            <div class="panel-head">
              <div>
                <div class="page-kicker mb-1">Pinned</div>
                <h2 class="brand-font panel-title">Favorite projects</h2>
              </div>
            </div>
            <div class="project-list">
              <button
                v-for="project in pinnedProjects"
                :key="`pin-${project.id}`"
                type="button"
                class="project-row"
                @click="router.push(`/projects/${project.id}`)"
              >
                <div class="project-mark pinned" aria-hidden="true">{{ project.name.slice(0, 1).toUpperCase() }}</div>
                <div class="project-meta">
                  <strong>{{ project.name }}</strong>
                  <small>
                    {{ project.location || 'Location TBD' }}
                    <template v-if="project.state"> · {{ project.state }}</template>
                    · {{ project.document_count }} file{{ project.document_count === 1 ? '' : 's' }}
                  </small>
                </div>
                <v-chip size="x-small" class="status-chip" :color="statusColor(project.status)" variant="tonal">
                  {{ project.status.replace('_', ' ') }}
                </v-chip>
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  color="primary"
                  aria-label="Unpin project"
                  @click="togglePin(project.id, $event)"
                >
                  <v-icon size="18">mdi-pin</v-icon>
                </v-btn>
              </button>
            </div>
          </section>

          <section class="surface-panel panel mt-4">
            <div class="panel-head">
              <div>
                <div class="page-kicker mb-1">Recent projects</div>
                <h2 class="brand-font panel-title">Continue where you left off</h2>
              </div>
              <v-btn variant="text" color="primary" size="small" @click="router.push('/projects')">
                View all
              </v-btn>
            </div>

            <div v-if="!recentProjects.length && !pinnedProjects.length" class="empty-block">
              <v-icon size="28" color="primary" class="mb-2">mdi-folder-plus-outline</v-icon>
              <p class="mb-3">No projects yet. Create one and upload your first plan set.</p>
              <v-btn color="primary" prepend-icon="mdi-plus" @click="router.push('/projects')">
                Create project
              </v-btn>
            </div>

            <div v-else-if="!recentProjects.length" class="empty-block compact">
              <p class="mb-0">All recent projects are pinned above.</p>
            </div>

            <div v-else class="project-list">
              <button
                v-for="project in recentProjects"
                :key="project.id"
                type="button"
                class="project-row"
                @click="router.push(`/projects/${project.id}`)"
              >
                <div class="project-mark" aria-hidden="true">{{ project.name.slice(0, 1).toUpperCase() }}</div>
                <div class="project-meta">
                  <strong>{{ project.name }}</strong>
                  <small>
                    {{ project.location || 'Location TBD' }}
                    <template v-if="project.state"> · {{ project.state }}</template>
                    · {{ project.document_count }} file{{ project.document_count === 1 ? '' : 's' }}
                  </small>
                </div>
                <v-chip size="x-small" class="status-chip" :color="statusColor(project.status)" variant="tonal">
                  {{ project.status.replace('_', ' ') }}
                </v-chip>
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  :color="isPinned(project.id) ? 'primary' : undefined"
                  :aria-label="isPinned(project.id) ? 'Unpin project' : 'Pin project'"
                  @click="togglePin(project.id, $event)"
                >
                  <v-icon size="18">{{ isPinned(project.id) ? 'mdi-pin' : 'mdi-pin-outline' }}</v-icon>
                </v-btn>
                <v-icon size="18" class="row-arrow">mdi-chevron-right</v-icon>
              </button>
            </div>
          </section>
        </v-col>

        <v-col cols="12" lg="5">
          <section class="surface-panel panel attention-panel mb-4">
            <div class="panel-head">
              <div>
                <div class="page-kicker mb-1">Needs attention</div>
                <h2 class="brand-font panel-title">Clear blockers</h2>
              </div>
              <v-chip size="small" :color="attentionItems.length ? 'warning' : 'success'" variant="tonal">
                {{ attentionItems.length || 'Clear' }}
              </v-chip>
            </div>

            <div v-if="!attentionItems.length" class="empty-block compact">
              <p class="mb-0">No blockers right now. Failed files, empty Estimates Of Quantities, and reviews will show up here.</p>
            </div>

            <div v-else class="attention-list">
              <button
                v-for="(item, idx) in attentionItems"
                :key="`${item.kind}-${item.project_id}-${idx}`"
                type="button"
                class="attention-row"
                :class="item.severity"
                @click="openAttention(item)"
              >
                <div class="attention-icon">
                  <v-icon size="16">{{ severityIcon(item.kind) }}</v-icon>
                </div>
                <div class="attention-body">
                  <strong>{{ item.title }}</strong>
                  <small>{{ item.project_name }} · {{ item.detail }}</small>
                </div>
                <span class="attention-cta">{{ item.action_label }}</span>
              </button>
            </div>
          </section>

          <section class="surface-panel panel activity-panel">
            <div class="panel-head">
              <div>
                <div class="page-kicker mb-1">Live feed</div>
                <h2 class="brand-font panel-title">Recent activity</h2>
              </div>
              <v-chip size="small" color="primary" variant="outlined">Live</v-chip>
            </div>

            <div v-if="!stats?.recent_activity?.length" class="empty-block compact">
              <p class="mb-0">Activity will show here after you create projects, upload files, or generate Estimates Of Quantities.</p>
            </div>

            <div v-else class="activity-list">
              <button
                v-for="item in stats.recent_activity"
                :key="item.id"
                type="button"
                class="activity-row"
                :disabled="!item.project_id"
                @click="openActivity(item)"
              >
                <div class="activity-icon">
                  <v-icon size="16">{{ actionIcon(item.action) }}</v-icon>
                </div>
                <div class="activity-body">
                  <strong>{{ item.message }}</strong>
                  <small>{{ formatDate(item.created_at) }} · {{ item.action.replace(/_/g, ' ') }}</small>
                </div>
                <v-icon v-if="item.project_id" size="16" class="row-arrow">mdi-arrow-top-right</v-icon>
              </button>
            </div>
          </section>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<style scoped>
.dash {
  max-width: 1180px;
}

.hero {
  position: relative;
  overflow: hidden;
  display: grid;
  grid-template-columns: 1.4fr 0.9fr;
  gap: 28px;
  padding: 28px 28px 26px;
  margin-bottom: 22px;
  border-color: rgba(217, 255, 67, 0.22);
  background:
    radial-gradient(circle at 88% 18%, rgba(217, 255, 67, 0.1), transparent 34%),
    linear-gradient(145deg, #101f1a, #0b1512 70%);
}

.hero-title {
  font-size: clamp(1.8rem, 3vw, 2.45rem);
  font-weight: 900;
  letter-spacing: -0.05em;
  line-height: 1;
  margin: 0 0 12px;
  color: #fff;
}

.hero-title span {
  color: var(--acid);
}

.hero-lede {
  max-width: 540px;
  line-height: 1.6;
  font-size: 0.95rem;
}

.hero-side {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.readiness {
  border: 1px solid #2a3a33;
  background: rgba(7, 16, 14, 0.55);
  padding: 14px 16px;
}

.readiness-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #829087;
  margin-bottom: 10px;
}

.readiness-top b {
  color: var(--acid);
  font-size: 18px;
  letter-spacing: -0.04em;
}

.readiness-track {
  height: 3px;
  background: #28362f;
  margin-bottom: 10px;
  overflow: hidden;
}

.readiness-track i {
  display: block;
  height: 100%;
  background: var(--acid);
  box-shadow: 0 0 10px rgba(217, 255, 67, 0.55);
  transition: width 0.8s cubic-bezier(0.22, 1, 0.36, 1);
}

.readiness small {
  font-family: var(--font-mono);
  font-size: 10px;
  color: #9aa69f;
}

.hero-cta {
  align-self: flex-start;
}

.hero-orb {
  position: absolute;
  width: 220px;
  height: 220px;
  right: -40px;
  bottom: -80px;
  border: 1px solid rgba(133, 255, 208, 0.14);
  border-radius: 50%;
  pointer-events: none;
  animation: orbit 10s linear infinite;
}

.hero-orb::before {
  content: '';
  position: absolute;
  inset: 28px;
  border: 1px dashed rgba(217, 255, 67, 0.2);
  border-radius: 50%;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.stat-card {
  text-align: left;
  border: 1px solid var(--panel-border);
  background: var(--panel);
  color: inherit;
  padding: 16px;
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
  animation: rise 0.45s ease both;
  min-height: 132px;
  display: flex;
  flex-direction: column;
}

.stat-card:hover,
.stat-card.hot,
.stat-card:focus-visible {
  transform: translateY(-3px);
  border-color: rgba(217, 255, 67, 0.45);
  background: #12221c;
  box-shadow: 0 14px 30px rgba(0, 0, 0, 0.28);
  outline: none;
}

.stat-card.mint:hover,
.stat-card.mint.hot {
  border-color: rgba(133, 255, 208, 0.4);
}

.stat-card.warn:hover,
.stat-card.warn.hot {
  border-color: rgba(255, 195, 106, 0.45);
}

.stat-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #829087;
}

.stat-card .stat-value {
  font-size: 2rem;
  margin-bottom: auto;
}

.stat-hint {
  margin-top: 14px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #68756e;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.stat-card:hover .stat-hint,
.stat-card.hot .stat-hint {
  color: var(--acid);
}

.week-strip {
  display: grid;
  grid-template-columns: 1.1fr repeat(4, 1fr);
  gap: 12px;
  padding: 16px 18px;
  margin-bottom: 8px;
  align-items: center;
}

.week-label strong {
  display: block;
  color: #fff;
  font-size: 0.95rem;
}

.week-metric {
  border-left: 1px solid #2a3a33;
  padding-left: 14px;
}

.week-metric b {
  display: block;
  font-size: 1.35rem;
  letter-spacing: -0.04em;
  color: #fff;
  line-height: 1.1;
}

.week-metric span {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #748078;
}

.week-metric.alert b {
  color: #ffc36a;
}

.panel {
  padding: 22px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.panel-title {
  font-size: 1.15rem;
  font-weight: 800;
  margin: 0;
  color: #fff;
}

.action-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.action-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  text-align: left;
  border: 1px solid #2a3a33;
  background: #0d1814;
  color: inherit;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
}

.action-card:hover,
.action-card:focus-visible {
  border-color: rgba(217, 255, 67, 0.45);
  background: #12221c;
  transform: translateY(-2px);
  outline: none;
}

.action-card.primary {
  border-color: rgba(217, 255, 67, 0.35);
  background: linear-gradient(145deg, rgba(217, 255, 67, 0.08), #0d1814 65%);
}

.action-card strong {
  display: block;
  font-size: 0.92rem;
  margin-bottom: 4px;
}

.action-card small {
  display: block;
  color: #829087;
  line-height: 1.45;
  font-size: 0.78rem;
}

.action-card .v-icon {
  color: var(--acid);
  margin-top: 2px;
}

.project-list,
.activity-list,
.attention-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-row,
.activity-row,
.attention-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  text-align: left;
  border: 1px solid #24322c;
  background: #0d1814;
  color: inherit;
  padding: 12px;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}

.project-row:hover,
.activity-row:hover:not(:disabled),
.attention-row:hover,
.project-row:focus-visible,
.activity-row:focus-visible,
.attention-row:focus-visible {
  border-color: rgba(217, 255, 67, 0.4);
  background: #12221c;
  transform: translateX(2px);
  outline: none;
}

.activity-row:disabled {
  cursor: default;
  opacity: 0.85;
}

.attention-row.error {
  border-color: rgba(255, 139, 107, 0.35);
}

.attention-row.warning {
  border-color: rgba(255, 195, 106, 0.28);
}

.project-mark,
.activity-icon,
.attention-icon {
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 1px solid rgba(217, 255, 67, 0.28);
  background: rgba(217, 255, 67, 0.06);
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
}

.project-mark.pinned {
  box-shadow: 0 0 0 1px rgba(217, 255, 67, 0.2);
}

.attention-row.error .attention-icon {
  border-color: rgba(255, 139, 107, 0.45);
  color: #ff8b6b;
  background: rgba(255, 139, 107, 0.08);
}

.attention-row.warning .attention-icon {
  border-color: rgba(255, 195, 106, 0.4);
  color: #ffc36a;
  background: rgba(255, 195, 106, 0.08);
}

.project-meta,
.activity-body,
.attention-body {
  min-width: 0;
  flex: 1;
}

.project-meta strong,
.activity-body strong,
.attention-body strong {
  display: block;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 3px;
}

.project-meta small,
.activity-body small,
.attention-body small {
  display: block;
  color: #748078;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.03em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attention-cta {
  flex: 0 0 auto;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--acid);
}

.row-arrow {
  color: #68756e;
  flex: 0 0 auto;
}

.project-row:hover .row-arrow,
.activity-row:hover .row-arrow {
  color: var(--acid);
}

.empty-block {
  text-align: center;
  padding: 28px 16px;
  border: 1px dashed #31423b;
  color: #8e9b94;
}

.empty-block.compact {
  padding: 22px 14px;
}

@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes orbit {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 1100px) {
  .stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .week-strip {
    grid-template-columns: 1fr 1fr;
  }

  .week-metric {
    border-left: 0;
    padding-left: 0;
    border-top: 1px solid #2a3a33;
    padding-top: 10px;
  }
}

@media (max-width: 900px) {
  .hero {
    grid-template-columns: 1fr;
  }

  .hero-orb {
    display: none;
  }
}

@media (max-width: 700px) {
  .stat-grid,
  .action-grid {
    grid-template-columns: 1fr;
  }

  .hero,
  .panel,
  .week-strip {
    padding: 18px;
  }
}
</style>
