<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchAdminOverview, listAdminUsers, updateAdminUser } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const loading = ref(true)
const error = ref<string | null>(null)
const overview = ref<Record<string, any> | null>(null)
const users = ref<Awaited<ReturnType<typeof listAdminUsers>>>([])

async function load() {
  loading.value = true
  error.value = null
  try {
    overview.value = await fetchAdminOverview()
    users.value = await listAdminUsers()
  } catch {
    error.value = 'Admin access required. Register/login with role admin.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function toggleBlock(user: { id: number; is_blocked: boolean }) {
  await updateAdminUser(user.id, { is_blocked: !user.is_blocked })
  await load()
}

async function setRole(userId: number, role: string) {
  await updateAdminUser(userId, { role })
  await load()
}
</script>

<template>
  <div class="page-shell">
    <div class="page-kicker">System control</div>
    <h1 class="brand-font text-h4 mb-1">Admin dashboard</h1>
    <p class="muted mb-6">Users, processing jobs, storage, and system health.</p>

    <v-alert v-if="error" type="warning" variant="tonal" class="mb-4">
      {{ error }} Current role: {{ auth.user?.role }}
    </v-alert>

    <div v-if="loading" class="text-center py-12"><v-progress-circular indeterminate color="primary" /></div>

    <template v-else-if="overview">
      <v-row class="mb-2">
        <v-col v-for="card in [
          ['Users', overview.total_users],
          ['Active users', overview.active_users],
          ['Projects', overview.total_projects],
          ['Documents', overview.documents_uploaded],
          ['BOQs', overview.boqs_generated],
          ['Completed jobs', overview.completed_jobs],
          ['Failed jobs', overview.failed_jobs],
          ['Storage MB', overview.storage_usage_mb],
        ]" :key="card[0]" cols="12" sm="6" md="3">
          <div class="surface-panel pa-4">
            <div class="text-caption muted">{{ card[0] }}</div>
            <div class="stat-value">{{ card[1] }}</div>
          </div>
        </v-col>
      </v-row>

      <v-row>
        <v-col cols="12" md="5">
          <div class="surface-panel pa-5 mb-4">
            <h2 class="brand-font text-h6 mb-3">System</h2>
            <div class="mb-2">Health: <strong>{{ overview.system_health }}</strong></div>
            <div class="mb-2">AI mode: <strong>{{ overview.ai_mode }}</strong></div>
            <div class="mb-2">Database: <strong>{{ overview.database }}</strong></div>
            <div class="mb-2">Queue: <strong>{{ overview.pdf_processing_queue }}</strong></div>
            <div>Activity (24h): <strong>{{ overview.activity_last_24h }}</strong></div>
          </div>
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-3">Error logs</h2>
            <div v-if="!overview.error_logs?.length" class="muted">No failed jobs</div>
            <div v-for="e in overview.error_logs" :key="e.document_id" class="mb-3">
              <div class="font-weight-medium">{{ e.filename }}</div>
              <div class="text-caption muted">{{ e.error }}</div>
            </div>
          </div>
        </v-col>
        <v-col cols="12" md="7">
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-3">Manage users</h2>
            <v-table density="comfortable">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in users" :key="u.id">
                  <td>
                    <div class="font-weight-medium">{{ u.full_name }}</div>
                    <div class="text-caption muted">{{ u.email }}</div>
                  </td>
                  <td>
                    <v-select
                      :model-value="u.role"
                      :items="['admin','project_manager','design_engineer','quantity_surveyor','reviewer','client']"
                      density="compact"
                      hide-details
                      style="max-width: 180px"
                      @update:model-value="(v:string) => setRole(u.id, v)"
                    />
                  </td>
                  <td>
                    <v-chip size="x-small" :color="u.is_blocked ? 'error' : 'success'" variant="tonal">
                      {{ u.is_blocked ? 'blocked' : 'active' }}
                    </v-chip>
                  </td>
                  <td>
                    <v-btn size="small" variant="text" @click="toggleBlock(u)">
                      {{ u.is_blocked ? 'Unblock' : 'Block' }}
                    </v-btn>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </v-col>
      </v-row>
    </template>
  </div>
</template>
