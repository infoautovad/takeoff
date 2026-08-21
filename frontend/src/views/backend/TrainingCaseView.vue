<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { deleteTrainingCase, getTrainingCase, type TrainingCaseDetail } from '@/api/training'
import TrainingStageNav from '@/components/backend/TrainingStageNav.vue'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => Number(route.params.id))

const loading = ref(true)
const error = ref<string | null>(null)
const detail = ref<TrainingCaseDetail | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    detail.value = await getTrainingCase(caseId.value)
  } catch {
    error.value = 'Could not load training case (admin only).'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function removeCase() {
  if (!confirm('Delete this training case and its runs?')) return
  await deleteTrainingCase(caseId.value)
  router.push('/backend')
}
</script>

<template>
  <div class="page-shell backend-lab">
    <div class="d-flex flex-wrap justify-space-between ga-2 mb-2">
      <div>
        <div class="page-kicker">Training case</div>
        <h1 class="brand-font text-h4 mb-1">{{ detail?.name || '…' }}</h1>
        <p class="muted mb-0">Open each stage on its own page — Analyze → Original EOQ → Evaluate.</p>
      </div>
      <div class="d-flex ga-2 align-start">
        <v-btn variant="tonal" @click="router.push('/backend')">All cases</v-btn>
        <v-btn variant="text" color="error" @click="removeCase">Delete</v-btn>
      </div>
    </div>

    <TrainingStageNav :detail="detail" />

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <div v-if="loading" class="text-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <template v-else-if="detail">
      <v-row>
        <v-col cols="12" md="4">
          <div
            class="surface-panel pa-5 stage-card"
            role="button"
            tabindex="0"
            @click="router.push(`/backend/cases/${caseId}/analyze`)"
            @keydown.enter="router.push(`/backend/cases/${caseId}/analyze`)"
          >
            <div class="page-kicker mb-1">Stage 1</div>
            <h2 class="brand-font text-h6 mb-2">Analyze plan</h2>
            <p class="text-caption muted mb-3">
              Upload PDF/DWG, Analyze with progress, then Generate Estimate Of Quantities.
            </p>
            <v-chip size="small" :color="detail.has_autovad_eoq ? 'success' : 'default'" variant="tonal">
              {{ detail.has_autovad_eoq ? `${detail.autovad_item_count} EOQ items` : 'Not started' }}
            </v-chip>
          </div>
        </v-col>
        <v-col cols="12" md="4">
          <div
            class="surface-panel pa-5 stage-card"
            :class="{ locked: !detail.has_autovad_eoq }"
            role="button"
            tabindex="0"
            @click="detail.has_autovad_eoq && router.push(`/backend/cases/${caseId}/original`)"
            @keydown.enter="detail.has_autovad_eoq && router.push(`/backend/cases/${caseId}/original`)"
          >
            <div class="page-kicker mb-1">Stage 2</div>
            <h2 class="brand-font text-h6 mb-2">Original EOQ</h2>
            <p class="text-caption muted mb-3">
              Upload the original Estimate Of Quantities for comparison.
            </p>
            <v-chip size="small" :color="detail.has_expected ? 'success' : 'default'" variant="tonal">
              {{ detail.has_expected ? `${detail.expected_item_count} gold items` : 'Locked until Stage 1' }}
            </v-chip>
          </div>
        </v-col>
        <v-col cols="12" md="4">
          <div
            class="surface-panel pa-5 stage-card"
            :class="{ locked: !detail.can_evaluate }"
            role="button"
            tabindex="0"
            @click="detail.can_evaluate && router.push(`/backend/cases/${caseId}/evaluate`)"
            @keydown.enter="detail.can_evaluate && router.push(`/backend/cases/${caseId}/evaluate`)"
          >
            <div class="page-kicker mb-1">Stage 3</div>
            <h2 class="brand-font text-h6 mb-2">Evaluate &amp; report</h2>
            <p class="text-caption muted mb-3">
              Compare AutoVAD vs original and generate the training report.
            </p>
            <v-chip size="small" :color="detail.runs?.some((r) => r.report) ? 'success' : 'default'" variant="tonal">
              {{ detail.runs?.some((r) => r.report) ? 'Report ready' : 'Locked until Stage 2' }}
            </v-chip>
          </div>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<style scoped>
.stage-card {
  cursor: pointer;
  transition: border-color 0.15s ease;
  border: 1px solid rgba(217, 255, 67, 0.12);
  min-height: 180px;
}
.stage-card:hover:not(.locked) {
  border-color: rgba(217, 255, 67, 0.45);
}
.stage-card.locked {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
