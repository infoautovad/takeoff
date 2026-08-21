<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createTrainingCase,
  listTrainingCases,
  trainingOverview,
  type TrainingCaseSummary,
} from '@/api/training'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(true)
const error = ref<string | null>(null)
const cases = ref<TrainingCaseSummary[]>([])
const overview = ref<Awaited<ReturnType<typeof trainingOverview>> | null>(null)
const creating = ref(false)
const newName = ref('')
const newDescription = ref('')

async function load() {
  loading.value = true
  error.value = null
  try {
    overview.value = await trainingOverview()
    cases.value = await listTrainingCases()
  } catch {
    error.value = 'Admin access required. Sign in with an admin account to use the Training Lab.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function createCase() {
  if (!newName.value.trim()) return
  creating.value = true
  error.value = null
  try {
    const created = await createTrainingCase({
      name: newName.value.trim(),
      description: newDescription.value.trim() || undefined,
    })
    newName.value = ''
    newDescription.value = ''
    await router.push(`/backend/cases/${created.id}/analyze`)
  } catch (err) {
    error.value = 'Could not create training case'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="page-shell backend-lab">
    <div class="page-kicker">Agent &amp; model lab</div>
    <h1 class="brand-font text-h4 mb-1">Training portal</h1>
    <p class="muted mb-6">
      Upload sample plans and original (gold) items. Run AutoVAD, then review a training report of
      misses, extras, and quantity errors — fuel for specializing agents later.
    </p>

    <v-alert v-if="error" type="warning" variant="tonal" class="mb-4">
      {{ error }} Current role: {{ auth.user?.role }}
    </v-alert>

    <div v-if="loading" class="text-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <template v-else-if="overview">
      <v-row class="mb-4">
        <v-col v-for="card in [
          ['Cases', overview.cases],
          ['Ready', overview.ready_cases],
          ['Runs', overview.runs],
          ['Completed', overview.completed_runs],
        ]" :key="card[0]" cols="6" md="3">
          <div class="surface-panel pa-4">
            <div class="text-caption muted">{{ card[0] }}</div>
            <div class="stat-value">{{ card[1] }}</div>
          </div>
        </v-col>
      </v-row>

      <v-row>
        <v-col cols="12" md="5">
          <div class="surface-panel pa-5 mb-4">
            <h2 class="brand-font text-h6 mb-3">New training case</h2>
            <v-text-field v-model="newName" label="Case name" class="mb-2" />
            <v-textarea v-model="newDescription" label="Description (optional)" rows="2" class="mb-3" />
            <v-btn color="primary" block :loading="creating" :disabled="!newName.trim()" @click="createCase">
              Create case
            </v-btn>
            <p class="text-caption muted mt-3 mb-0">
              Opens Stage 1 (Analyze) on its own page — then Original EOQ → Evaluate.
            </p>
          </div>
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-2">How this lab works</h2>
            <ol class="lab-steps muted mb-0">
              <li>Create a case</li>
              <li><strong>Stage 1:</strong> Upload plan PDF/DWG → Analyze → AutoVAD EOQ</li>
              <li><strong>Stage 2:</strong> Upload original EOQ (PDF/Excel/CSV/image)</li>
              <li><strong>Stage 3:</strong> Evaluate differences → training report</li>
            </ol>
          </div>
        </v-col>
        <v-col cols="12" md="7">
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-4">Cases</h2>
            <div v-if="!cases.length" class="muted text-center py-10">No training cases yet.</div>
            <div
              v-for="c in cases"
              :key="c.id"
              class="case-row pa-3 mb-3"
              role="button"
              tabindex="0"
              @click="router.push(`/backend/cases/${c.id}/analyze`)"
              @keydown.enter="router.push(`/backend/cases/${c.id}/analyze`)"
            >
              <div class="d-flex justify-space-between ga-2 flex-wrap">
                <div>
                  <div class="font-weight-medium">{{ c.name }}</div>
                  <div class="text-caption muted">
                    {{ c.sample_filename || 'No sample yet' }}
                    · {{ c.expected_item_count }} gold items
                    · {{ c.status }}
                  </div>
                </div>
                <v-chip size="small" :color="c.has_sample && c.has_expected ? 'success' : 'warning'" variant="tonal">
                  {{ c.has_sample && c.has_expected ? 'Ready' : 'Draft' }}
                </v-chip>
              </div>
            </div>
          </div>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<style scoped>
.lab-steps {
  padding-left: 1.1rem;
  line-height: 1.7;
  font-size: 0.9rem;
}
.case-row {
  border: 1px solid rgba(217, 255, 67, 0.12);
  border-radius: 10px;
  background: rgba(7, 16, 14, 0.35);
  cursor: pointer;
  transition: border-color 0.15s ease;
}
.case-row:hover {
  border-color: rgba(217, 255, 67, 0.45);
}
</style>
