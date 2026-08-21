<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getTrainingCase,
  uploadExpectedFile,
  type TrainingCaseDetail,
} from '@/api/training'
import TrainingStageNav from '@/components/backend/TrainingStageNav.vue'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => Number(route.params.id))

const loading = ref(true)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadProgressLabel = ref('')
const uploadModal = ref(false)
const error = ref<string | null>(null)
const detail = ref<TrainingCaseDetail | null>(null)
const expectedFile = ref<File[] | File | null>(null)

const expectedItems = computed(() => detail.value?.expected?.items || [])

function pickFile(v: File[] | File | null): File | null {
  if (!v) return null
  return Array.isArray(v) ? v[0] || null : v
}

function errDetail(err: unknown, fallback: string) {
  if (typeof err === 'object' && err && 'response' in err) {
    const detailMsg = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
    if (detailMsg) return detailMsg
  }
  return fallback
}

function formatQty(q: unknown) {
  if (q == null || q === '') return '—'
  const n = Number(q)
  if (Number.isFinite(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 3 })
  return String(q)
}

async function load() {
  loading.value = true
  error.value = null
  try {
    detail.value = await getTrainingCase(caseId.value)
    if (!detail.value.has_autovad_eoq) {
      await router.replace(`/backend/cases/${caseId.value}/analyze`)
    }
  } catch {
    error.value = 'Could not load training case (admin only).'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function uploadExpected() {
  if (!detail.value?.has_autovad_eoq) {
    error.value = 'Complete Stage 1 Analyze first'
    return
  }
  const file = pickFile(expectedFile.value)
  if (!file) {
    error.value = 'Choose an original Estimate Of Quantities file (PDF / Excel / CSV / image)'
    return
  }
  uploading.value = true
  uploadModal.value = true
  uploadProgress.value = 0
  uploadProgressLabel.value = `Uploading ${file.name}…`
  error.value = null
  try {
    detail.value = await uploadExpectedFile(caseId.value, file, (percent) => {
      uploadProgress.value = percent
      if (percent >= 100) {
        uploadProgressLabel.value = 'Parsing original EOQ (may use vision)…'
      } else {
        uploadProgressLabel.value = `Uploading ${file.name}…`
      }
    })
    uploadProgress.value = 100
    uploadProgressLabel.value = 'Upload & parse complete'
    expectedFile.value = null
    await nextTick()
    setTimeout(() => {
      uploadModal.value = false
    }, 700)
  } catch (err) {
    error.value = errDetail(err, 'Could not parse original Estimate Of Quantities file')
    uploadModal.value = false
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="page-shell backend-lab">
    <div class="d-flex flex-wrap justify-space-between ga-2 mb-2">
      <div>
        <div class="page-kicker">Stage 2</div>
        <h1 class="brand-font text-h4 mb-1">Original EOQ</h1>
        <p class="muted mb-0">{{ detail?.name || '…' }} — upload gold Estimate Of Quantities for comparison</p>
      </div>
      <div class="d-flex ga-2 align-start">
        <v-btn variant="tonal" @click="router.push(`/backend/cases/${caseId}`)">Case hub</v-btn>
        <v-btn variant="tonal" @click="router.push('/backend')">All cases</v-btn>
      </div>
    </div>

    <TrainingStageNav :detail="detail" />

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4" closable @click:close="error = null">
      {{ error }}
    </v-alert>

    <div v-if="loading" class="text-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <template v-else-if="detail">
      <div class="surface-panel pa-5 mb-4">
        <h2 class="brand-font text-h6 mb-2">Upload original Estimate Of Quantities</h2>
        <p class="text-caption muted mb-3">
          PDF / Excel / CSV / image.
          <span v-if="detail.expected_filename"> Current: {{ detail.expected_filename }}</span>
        </p>
        <v-file-input
          v-model="expectedFile"
          label="Original EOQ file"
          accept=".pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,.json"
          prepend-icon=""
          prepend-inner-icon="mdi-file-table-outline"
          show-size
          :disabled="uploading"
          class="mb-3"
        />
        <div v-if="uploading" class="upload-progress mb-3">
          <div class="d-flex justify-space-between align-center text-caption mb-1">
            <span class="upload-progress__label">{{ uploadProgressLabel }}</span>
            <span class="upload-progress__pct font-weight-medium">{{ uploadProgress }}%</span>
          </div>
          <v-progress-linear
            :model-value="uploadProgress"
            color="primary"
            height="8"
            rounded
          />
        </div>
        <div class="d-flex flex-wrap ga-2">
          <v-btn color="primary" :loading="uploading" :disabled="uploading" @click="uploadExpected">
            {{ uploading ? `Uploading ${uploadProgress}%` : 'Upload & parse original EOQ' }}
          </v-btn>
          <v-btn
            v-if="detail.has_expected"
            variant="text"
            color="primary"
            @click="router.push(`/backend/cases/${caseId}/evaluate`)"
          >
            Next: Evaluate →
          </v-btn>
        </div>
      </div>

      <div class="surface-panel pa-5">
        <div class="d-flex flex-wrap justify-space-between align-center ga-2 mb-3">
          <h2 class="brand-font text-h6 mb-0">Original EOQ (parsed)</h2>
          <v-chip v-if="expectedItems.length" size="small" variant="tonal">
            {{ expectedItems.length }} items
          </v-chip>
        </div>
        <div v-if="!expectedItems.length" class="muted text-center py-10">
          Upload an original EOQ file to see the full gold list here.
        </div>
        <v-table v-else density="comfortable" class="eoq-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Item Description</th>
              <th>Unit</th>
              <th>Quantity</th>
              <th>Category</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(it, idx) in expectedItems" :key="idx">
              <td class="text-center">{{ it.item_no ?? it.display_number ?? idx + 1 }}</td>
              <td class="font-weight-medium">{{ it.description || '—' }}</td>
              <td class="text-uppercase text-center">{{ String(it.unit || 'UNIT').toUpperCase() }}</td>
              <td class="text-right">{{ formatQty(it.quantity) }}</td>
              <td class="text-caption">{{ it.category || it.group || '—' }}</td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </template>

    <v-dialog
      v-model="uploadModal"
      max-width="480"
      persistent
      scrim="rgba(3, 8, 6, 0.78)"
    >
      <div class="upload-modal">
        <div class="upload-modal-glow" aria-hidden="true" />
        <div class="page-kicker mb-1">Training lab</div>
        <h2 class="brand-font text-h5 mb-2">Uploading original EOQ</h2>
        <p class="muted text-body-2 mb-4">{{ uploadProgressLabel }}</p>
        <div class="upload-meter-top">
          <span>{{ uploadProgress >= 100 ? 'Parsing…' : 'Transfer in progress' }}</span>
          <b>{{ Math.round(uploadProgress) }}%</b>
        </div>
        <div class="upload-track" aria-hidden="true">
          <i :style="{ width: `${uploadProgress}%` }" />
        </div>
      </div>
    </v-dialog>
  </div>
</template>

<style scoped>
.upload-progress__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 75%;
}
.upload-progress__pct {
  flex-shrink: 0;
}
.eoq-table :deep(th) {
  white-space: nowrap;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(234, 240, 235, 0.55);
}
.upload-modal {
  position: relative;
  overflow: hidden;
  background: linear-gradient(165deg, #12211c 0%, #0a1512 55%, #07110e 100%);
  border: 1px solid rgba(217, 255, 67, 0.28);
  color: #eaf0eb;
  padding: 26px 26px 22px;
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.55);
}
.upload-modal-glow {
  position: absolute;
  width: 200px;
  height: 200px;
  right: -50px;
  top: -70px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(217, 255, 67, 0.18), transparent 68%);
  pointer-events: none;
}
.upload-meter-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
  font-family: ui-monospace, monospace;
  font-size: 0.72rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(234, 240, 235, 0.55);
}
.upload-meter-top b {
  color: #d9ff43;
  font-size: 1.35rem;
  letter-spacing: -0.03em;
}
.upload-track {
  position: relative;
  height: 8px;
  background: #1a2b24;
  overflow: hidden;
}
.upload-track i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #85ffd0, #d9ff43);
  box-shadow: 0 0 14px rgba(217, 255, 67, 0.45);
  transition: width 0.35s ease;
}
</style>
