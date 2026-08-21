<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useProjectsStore } from '@/stores/projects'
import { formatDate, statusColor } from '@/utils/format'
import { loadPinnedProjectIds, togglePinnedProjectId } from '@/utils/pinnedProjects'
import type { Project, ProjectPayload, ProjectStatus } from '@/types'

type SortKey = 'updated' | 'name' | 'documents'
type ViewMode = 'grid' | 'table'

const store = useProjectsStore()
const auth = useAuthStore()
const router = useRouter()

const search = ref('')
const statusFilter = ref<ProjectStatus | 'all'>('all')
const sortBy = ref<SortKey>('updated')
const viewMode = ref<ViewMode>('grid')
const showArchived = ref(false)
const pinnedIds = ref<number[]>([])
const dialog = ref(false)
const saving = ref(false)
const archivingId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const formError = ref<string | null>(null)
const actionError = ref<string | null>(null)

const form = ref<ProjectPayload>({
  name: '',
  description: '',
  location: '',
  client_name: '',
  country: 'USA',
  state: '',
  status: 'draft',
})

const usStates = [
  'Alabama',
  'Alaska',
  'Arizona',
  'Arkansas',
  'California',
  'Colorado',
  'Connecticut',
  'Delaware',
  'District of Columbia',
  'Florida',
  'Georgia',
  'Hawaii',
  'Idaho',
  'Illinois',
  'Indiana',
  'Iowa',
  'Kansas',
  'Kentucky',
  'Louisiana',
  'Maine',
  'Maryland',
  'Massachusetts',
  'Michigan',
  'Minnesota',
  'Mississippi',
  'Missouri',
  'Montana',
  'Nebraska',
  'Nevada',
  'New Hampshire',
  'New Jersey',
  'New Mexico',
  'New York',
  'North Carolina',
  'North Dakota',
  'Ohio',
  'Oklahoma',
  'Oregon',
  'Pennsylvania',
  'Rhode Island',
  'South Carolina',
  'South Dakota',
  'Tennessee',
  'Texas',
  'Utah',
  'Vermont',
  'Virginia',
  'Washington',
  'West Virginia',
  'Wisconsin',
  'Wyoming',
]

const statusOptions: Array<{ title: string; value: ProjectStatus | 'all' }> = [
  { title: 'All statuses', value: 'all' },
  { title: 'Draft', value: 'draft' },
  { title: 'Active', value: 'active' },
  { title: 'In review', value: 'in_review' },
  { title: 'Approved', value: 'approved' },
  { title: 'Archived', value: 'archived' },
]

const sortOptions: Array<{ title: string; value: SortKey }> = [
  { title: 'Recently updated', value: 'updated' },
  { title: 'Name A–Z', value: 'name' },
  { title: 'Document count', value: 'documents' },
]

const hasActiveFilters = computed(
  () =>
    Boolean(search.value.trim()) ||
    statusFilter.value !== 'all' ||
    showArchived.value ||
    sortBy.value !== 'updated',
)

const filteredProjects = computed(() => {
  let list = [...store.projects]

  if (!showArchived.value && statusFilter.value !== 'archived') {
    list = list.filter((p) => p.status !== 'archived')
  }

  if (statusFilter.value !== 'all') {
    list = list.filter((p) => p.status === statusFilter.value)
  }

  const q = search.value.trim().toLowerCase()
  if (q) {
    list = list.filter((p) => {
      const hay = [p.name, p.description, p.location, p.client_name, p.state, p.country]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }

  list.sort((a, b) => {
    const aPinned = pinnedIds.value.includes(a.id) ? 1 : 0
    const bPinned = pinnedIds.value.includes(b.id) ? 1 : 0
    if (aPinned !== bPinned) return bPinned - aPinned

    if (sortBy.value === 'name') {
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
    }
    if (sortBy.value === 'documents') {
      return (b.document_count || 0) - (a.document_count || 0)
    }
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })

  return list
})

const emptyLibrary = computed(() => !store.loading && store.projects.length === 0)
const emptyFiltered = computed(
  () => !store.loading && store.projects.length > 0 && filteredProjects.value.length === 0,
)

onMounted(async () => {
  pinnedIds.value = loadPinnedProjectIds(auth.user?.id)
  await store.fetchProjects()
})

watch(
  () => auth.user?.id,
  (id) => {
    pinnedIds.value = loadPinnedProjectIds(id)
  },
)

async function runSearch() {
  actionError.value = null
  await store.fetchProjects(search.value.trim() || undefined)
}

function clearFilters() {
  search.value = ''
  statusFilter.value = 'all'
  sortBy.value = 'updated'
  showArchived.value = false
  void runSearch()
}

function openCreate() {
  formError.value = null
  form.value = {
    name: '',
    description: '',
    location: '',
    client_name: '',
    country: 'USA',
    state: '',
    status: 'draft',
  }
  dialog.value = true
}

async function createProject() {
  if (!form.value.name.trim()) {
    formError.value = 'Project name is required'
    return
  }
  saving.value = true
  formError.value = null
  try {
    const project = await store.create({
      ...form.value,
      name: form.value.name.trim(),
    })
    dialog.value = false
    router.push(`/projects/${project.id}`)
  } catch {
    formError.value = 'Could not create project'
  } finally {
    saving.value = false
  }
}

function openProject(project: Project) {
  router.push(`/projects/${project.id}`)
}

function isPinned(id: number) {
  return pinnedIds.value.includes(id)
}

function togglePin(project: Project, event?: Event) {
  event?.stopPropagation()
  pinnedIds.value = togglePinnedProjectId(auth.user?.id, project.id)
}

async function archiveProject(project: Project, event?: Event) {
  event?.stopPropagation()
  if (project.status === 'archived') return
  const ok = window.confirm(`Archive "${project.name}"? You can show archived projects later.`)
  if (!ok) return
  archivingId.value = project.id
  actionError.value = null
  try {
    await store.archive(project.id)
  } catch {
    actionError.value = 'Could not archive project'
  } finally {
    archivingId.value = null
  }
}

async function deleteProject(project: Project, event?: Event) {
  event?.stopPropagation()
  const ok = window.confirm(
    `Permanently delete "${project.name}"?\n\nThis removes the project, documents, Estimates Of Quantities, and related data. This cannot be undone.`,
  )
  if (!ok) return
  deletingId.value = project.id
  actionError.value = null
  try {
    await store.remove(project.id)
  } catch {
    actionError.value = 'Could not delete project'
  } finally {
    deletingId.value = null
  }
}

function statusLabel(status: string) {
  return status.replace('_', ' ')
}

function locationLine(project: Project) {
  const place = [project.location, project.state].filter(Boolean).join(' · ')
  if (!place) return 'Location TBD'
  return project.country ? `${place}, ${project.country}` : place
}
</script>

<template>
  <div class="page-shell">
    <div class="d-flex flex-wrap align-center justify-space-between mb-6 ga-3">
      <div>
        <div class="page-kicker">Project library</div>
        <h1 class="brand-font text-h4 mb-1">Projects</h1>
        <p class="muted mb-0">Organize road/civil document sets by project.</p>
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">Create project</v-btn>
    </div>

    <div class="surface-panel pa-4 mb-5">
      <v-row dense align="center">
        <v-col cols="12" md="4">
          <v-text-field
            v-model="search"
            label="Search projects"
            prepend-inner-icon="mdi-magnify"
            hide-details
            clearable
            density="comfortable"
            @keyup.enter="runSearch"
            @click:clear="runSearch"
          />
        </v-col>
        <v-col cols="12" sm="6" md="2">
          <v-select
            v-model="statusFilter"
            :items="statusOptions"
            label="Status"
            hide-details
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" sm="6" md="2">
          <v-select
            v-model="sortBy"
            :items="sortOptions"
            label="Sort"
            hide-details
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" sm="6" md="2" class="d-flex align-center">
          <v-switch
            v-model="showArchived"
            label="Show archived"
            color="secondary"
            hide-details
            density="compact"
            class="mt-0"
          />
        </v-col>
        <v-col cols="12" sm="6" md="2" class="d-flex justify-md-end ga-2">
          <v-btn-toggle v-model="viewMode" mandatory density="comfortable" color="secondary" class="view-toggle">
            <v-btn value="grid" icon="mdi-view-grid-outline" aria-label="Grid view" />
            <v-btn value="table" icon="mdi-view-list-outline" aria-label="Table view" />
          </v-btn-toggle>
          <v-btn color="secondary" variant="tonal" @click="runSearch">Search</v-btn>
        </v-col>
      </v-row>
      <div v-if="hasActiveFilters" class="d-flex align-center ga-2 mt-3">
        <span class="text-caption muted">
          Showing {{ filteredProjects.length }} of {{ store.projects.length }}
        </span>
        <v-btn size="small" variant="text" @click="clearFilters">Clear filters</v-btn>
      </div>
    </div>

    <v-alert v-if="actionError" type="error" variant="tonal" class="mb-4" closable @click:close="actionError = null">
      {{ actionError }}
    </v-alert>

    <v-row v-if="store.loading">
      <v-col cols="12" class="text-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </v-col>
    </v-row>

    <div v-else-if="emptyLibrary" class="surface-panel pa-10 text-center">
      <v-icon size="40" color="secondary" class="mb-3">mdi-folder-plus-outline</v-icon>
      <h2 class="brand-font text-h6 mb-2">No projects yet</h2>
      <p class="muted mb-4">Create your first project to start uploading USA road plans.</p>
      <v-btn color="primary" @click="openCreate">Create project</v-btn>
    </div>

    <div v-else-if="emptyFiltered" class="surface-panel pa-10 text-center">
      <v-icon size="40" color="secondary" class="mb-3">mdi-magnify-close</v-icon>
      <h2 class="brand-font text-h6 mb-2">No matching projects</h2>
      <p class="muted mb-4">Try a different search, status, or include archived projects.</p>
      <div class="d-flex justify-center ga-2 flex-wrap">
        <v-btn color="secondary" variant="tonal" @click="clearFilters">Clear filters</v-btn>
        <v-btn color="primary" @click="openCreate">Create project</v-btn>
      </div>
    </div>

    <template v-else>
      <v-row v-if="viewMode === 'grid'">
        <v-col v-for="project in filteredProjects" :key="project.id" cols="12" md="6" lg="4">
          <div class="surface-panel project-card pa-5 h-100" @click="openProject(project)">
            <div class="d-flex align-start justify-space-between mb-3 ga-2">
              <div class="d-flex align-center ga-2 min-w-0">
                <v-icon v-if="isPinned(project.id)" size="16" color="secondary" class="flex-shrink-0">
                  mdi-pin
                </v-icon>
                <h3 class="brand-font text-h6 mb-0 text-truncate">{{ project.name }}</h3>
              </div>
              <v-chip size="small" class="status-chip flex-shrink-0" :color="statusColor(project.status)" variant="tonal">
                {{ statusLabel(project.status) }}
              </v-chip>
            </div>

            <p class="muted text-body-2 mb-3 project-desc">
              {{ project.description || 'No description' }}
            </p>

            <div class="text-caption muted mb-1">
              <v-icon size="14" class="mr-1">mdi-account-outline</v-icon>
              {{ project.client_name || 'No client' }}
            </div>
            <div class="text-caption muted mb-1">
              <v-icon size="14" class="mr-1">mdi-map-marker-outline</v-icon>
              {{ locationLine(project) }}
            </div>
            <div class="text-caption muted mb-1">
              <v-icon size="14" class="mr-1">mdi-file-document-outline</v-icon>
              {{ project.document_count }} document{{ project.document_count === 1 ? '' : 's' }}
              <span class="mx-1">·</span>
              <v-icon size="14" class="mr-1">mdi-table</v-icon>
              {{ project.eoq_count ?? 0 }} {{ (project.eoq_count ?? 0) === 1 ? 'Estimate Of Quantities' : 'Estimates Of Quantities' }}
            </div>
            <div class="text-caption muted mb-4">Updated {{ formatDate(project.updated_at) }}</div>

            <div class="d-flex flex-wrap ga-2" @click.stop>
              <v-btn size="small" color="primary" variant="tonal" @click="openProject(project)">Open</v-btn>
              <v-btn
                size="small"
                variant="tonal"
                color="secondary"
                :prepend-icon="isPinned(project.id) ? 'mdi-pin-off' : 'mdi-pin-outline'"
                @click="togglePin(project, $event)"
              >
                {{ isPinned(project.id) ? 'Unpin' : 'Pin' }}
              </v-btn>
              <v-btn
                v-if="project.status !== 'archived'"
                size="small"
                variant="text"
                :loading="archivingId === project.id"
                @click="archiveProject(project, $event)"
              >
                Archive
              </v-btn>
              <v-btn
                size="small"
                variant="text"
                color="error"
                :loading="deletingId === project.id"
                @click="deleteProject(project, $event)"
              >
                Delete
              </v-btn>
            </div>
          </div>
        </v-col>
      </v-row>

      <div v-else class="surface-panel table-wrap">
        <v-table class="projects-table">
          <thead>
            <tr>
              <th>Project</th>
              <th>Status</th>
              <th>Client</th>
              <th>Location</th>
              <th>Docs</th>
              <th>Estimates Of Quantities</th>
              <th>Updated</th>
              <th class="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="project in filteredProjects"
              :key="project.id"
              class="table-row"
              @click="openProject(project)"
            >
              <td>
                <div class="d-flex align-center ga-2">
                  <v-icon v-if="isPinned(project.id)" size="14" color="secondary">mdi-pin</v-icon>
                  <span class="font-weight-medium">{{ project.name }}</span>
                </div>
              </td>
              <td>
                <v-chip size="x-small" class="status-chip" :color="statusColor(project.status)" variant="tonal">
                  {{ statusLabel(project.status) }}
                </v-chip>
              </td>
              <td class="muted">{{ project.client_name || '—' }}</td>
              <td class="muted">{{ locationLine(project) }}</td>
              <td>{{ project.document_count }}</td>
              <td>{{ project.eoq_count ?? 0 }}</td>
              <td class="muted">{{ formatDate(project.updated_at) }}</td>
              <td class="text-right" @click.stop>
                <v-btn size="small" variant="text" color="primary" @click="openProject(project)">Open</v-btn>
                <v-btn
                  size="small"
                  variant="text"
                  color="secondary"
                  :icon="isPinned(project.id) ? 'mdi-pin' : 'mdi-pin-outline'"
                  :aria-label="isPinned(project.id) ? 'Unpin' : 'Pin'"
                  @click="togglePin(project, $event)"
                />
                <v-btn
                  v-if="project.status !== 'archived'"
                  size="small"
                  variant="text"
                  :loading="archivingId === project.id"
                  @click="archiveProject(project, $event)"
                >
                  Archive
                </v-btn>
                <v-btn
                  size="small"
                  variant="text"
                  color="error"
                  :loading="deletingId === project.id"
                  @click="deleteProject(project, $event)"
                >
                  Delete
                </v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </template>

    <v-dialog v-model="dialog" max-width="640">
      <v-card class="pa-2">
        <v-card-title class="brand-font">Create project</v-card-title>
        <v-card-text>
          <v-alert v-if="formError" type="error" variant="tonal" class="mb-4">{{ formError }}</v-alert>
          <v-text-field v-model="form.name" label="Project name *" class="mb-2" />
          <v-textarea v-model="form.description" label="Description" rows="2" class="mb-2" />
          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field v-model="form.client_name" label="Client" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="form.location" label="Location / corridor" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="form.country"
                label="Country"
                readonly
                class="country-locked"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="form.state" :items="usStates" label="US State" clearable />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="createProject">Create</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.project-card {
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.project-card:hover {
  border-color: rgba(217, 255, 67, 0.45);
  transform: translateY(-2px);
  background: #12221c;
}

.project-desc {
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.view-toggle {
  background: rgba(255, 255, 255, 0.04);
}

.table-wrap {
  overflow-x: auto;
}

.projects-table {
  width: 100%;
}

.projects-table th {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.72rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(234, 240, 235, 0.55);
  white-space: nowrap;
}

.table-row {
  cursor: pointer;
  transition: background 0.15s ease;
}

.table-row:hover {
  background: rgba(217, 255, 67, 0.06);
}

.country-locked :deep(.v-field) {
  opacity: 1;
}

.country-locked :deep(.v-field__input),
.country-locked :deep(input) {
  color: #eaf0eb !important;
  -webkit-text-fill-color: #eaf0eb !important;
  opacity: 1 !important;
  font-weight: 700;
}
</style>
