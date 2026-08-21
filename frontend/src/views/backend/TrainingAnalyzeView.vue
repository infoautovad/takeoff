<script setup lang="ts">
import axios from 'axios'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  analyzeTrainingCase,
  getTrainingCase,
  uploadTrainingSample,
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
const generating = ref(false)
const error = ref<string | null>(null)
const detail = ref<TrainingCaseDetail | null>(null)
const sampleFile = ref<File[] | File | null>(null)
const showEoqList = ref(false)

const analyzing = ref(false)
const analyzeModal = ref(false)
const analyzeCancelConfirm = ref(false)
const analyzeProgress = ref(0)
const analyzeStage = ref('Preparing…')
const analyzeTargetLabel = ref('sample plan')
const analyzeStatus = ref<'running' | 'success' | 'error' | 'cancelled'>('running')
const analyzeStatusMessage = ref('')
let analyzeAbort: AbortController | null = null
let analyzeProgressTimer: ReturnType<typeof setInterval> | null = null

const pdfAnalyzeStages = [
  { at: 8, label: 'Opening plan file…' },
  { at: 22, label: 'Extracting text & tables…' },
  { at: 38, label: 'Reading drawing sheets (vision)…' },
  { at: 52, label: 'Matching bid template lines…' },
  { at: 68, label: 'Running AI quantity takeoff…' },
  { at: 84, label: 'Scoring confidence…' },
  { at: 94, label: 'Finalizing results…' },
]
const cadAnalyzeStages = [
  { at: 8, label: 'Opening CAD file…' },
  { at: 22, label: 'Uploading to Autodesk APS…' },
  { at: 40, label: 'Translating DWG / extracting geometry…' },
  { at: 58, label: 'Reading layers, lines & blocks…' },
  { at: 74, label: 'Building quantity takeoff…' },
  { at: 88, label: 'Enriching CAD quantities…' },
  { at: 94, label: 'Finalizing CAD results…' },
]
const analyzeStages = ref(pdfAnalyzeStages)

const autovadItems = computed(() => detail.value?.autovad_items || [])

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

function isCadFilename(name?: string | null) {
  const n = (name || '').toLowerCase()
  return n.endsWith('.dwg') || n.endsWith('.dxf') || n.endsWith('.xml') || n.endsWith('.landxml')
}

async function load() {
  loading.value = true
  error.value = null
  try {
    detail.value = await getTrainingCase(caseId.value)
    if (detail.value.has_autovad_eoq) showEoqList.value = true
  } catch {
    error.value = 'Could not load training case (admin only).'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function clearAnalyzeProgressTimer() {
  if (analyzeProgressTimer) {
    clearInterval(analyzeProgressTimer)
    analyzeProgressTimer = null
  }
}

function startAnalyzeProgress(label: string, cad = false) {
  analyzeStages.value = cad ? cadAnalyzeStages : pdfAnalyzeStages
  analyzeTargetLabel.value = label
  analyzeProgress.value = 3
  analyzeStage.value = cad ? 'Preparing CAD processing…' : 'Preparing analysis…'
  analyzeStatus.value = 'running'
  analyzeStatusMessage.value = ''
  analyzeCancelConfirm.value = false
  analyzeModal.value = true
  clearAnalyzeProgressTimer()
  analyzeProgressTimer = setInterval(() => {
    if (analyzeStatus.value !== 'running') return
    const next = Math.min(
      94,
      analyzeProgress.value + (analyzeProgress.value < 40 ? 1.4 : analyzeProgress.value < 70 ? 0.7 : 0.35),
    )
    analyzeProgress.value = Math.round(next * 10) / 10
    const stage = [...analyzeStages.value].reverse().find((s) => analyzeProgress.value >= s.at)
    if (stage) analyzeStage.value = stage.label
  }, 420)
}

function finishAnalyzeProgress(ok: boolean, message = '') {
  clearAnalyzeProgressTimer()
  if (ok) {
    analyzeProgress.value = 100
    analyzeStage.value = 'Analysis complete'
    analyzeStatus.value = 'success'
    analyzeStatusMessage.value =
      message || 'Takeoff ready. Click Generate Estimate Of Quantities to show the full list.'
  } else {
    analyzeStatus.value = 'error'
    analyzeStage.value = 'Analysis stopped'
    analyzeStatusMessage.value = message
  }
  analyzing.value = false
  analyzeAbort = null
}

function requestCancelAnalyze() {
  if (analyzeStatus.value !== 'running') {
    analyzeModal.value = false
    return
  }
  analyzeCancelConfirm.value = true
}

function dismissCancelWarning() {
  analyzeCancelConfirm.value = false
}

function confirmCancelAnalyze() {
  analyzeCancelConfirm.value = false
  if (analyzeAbort) {
    analyzeAbort.abort()
    analyzeAbort = null
  }
  clearAnalyzeProgressTimer()
  analyzeStatus.value = 'cancelled'
  analyzeStage.value = 'Cancelled by user'
  analyzeStatusMessage.value = 'Analysis was cancelled. Re-run Analyze if needed.'
  analyzing.value = false
}

function closeAnalyzeModal() {
  if (analyzeStatus.value === 'running') {
    requestCancelAnalyze()
    return
  }
  analyzeModal.value = false
  analyzeCancelConfirm.value = false
}

function onAnalyzeModalToggle(open: boolean) {
  if (!open) closeAnalyzeModal()
  else analyzeModal.value = true
}

function isAnalyzeCanceled(err: unknown) {
  return (
    axios.isCancel(err) ||
    (err as { code?: string; name?: string })?.code === 'ERR_CANCELED' ||
    (err as { name?: string })?.name === 'CanceledError'
  )
}

async function uploadSample() {
  const file = pickFile(sampleFile.value)
  if (!file) {
    error.value = 'Choose a sample PDF / DWG / DXF file'
    return
  }
  uploading.value = true
  uploadModal.value = true
  uploadProgress.value = 0
  uploadProgressLabel.value = `Uploading ${file.name}…`
  error.value = null
  try {
    detail.value = await uploadTrainingSample(caseId.value, file, (percent) => {
      uploadProgress.value = percent
      uploadProgressLabel.value =
        percent >= 100 ? 'Saving sample on server…' : `Uploading ${file.name}…`
    })
    uploadProgress.value = 100
    uploadProgressLabel.value = 'Upload complete'
    sampleFile.value = null
    showEoqList.value = false
    await nextTick()
    setTimeout(() => {
      uploadModal.value = false
    }, 600)
  } catch (err) {
    error.value = errDetail(err, 'Sample upload failed')
    uploadModal.value = false
  } finally {
    uploading.value = false
  }
}

async function runAnalyze() {
  if (!detail.value?.has_sample) {
    error.value = 'Upload a sample plan file first'
    return
  }
  if (analyzing.value) return
  analyzing.value = true
  error.value = null
  analyzeAbort = new AbortController()
  const label = detail.value.sample_filename || 'sample plan'
  startAnalyzeProgress(label, isCadFilename(label))
  await nextTick()
  try {
    detail.value = await analyzeTrainingCase(caseId.value, { signal: analyzeAbort.signal })
    const count = detail.value.autovad_item_count || detail.value.autovad_items?.length || 0
    finishAnalyzeProgress(true, `Found ${count} quantity item(s). Generate Estimate Of Quantities to view the full list.`)
  } catch (err) {
    if (isAnalyzeCanceled(err)) return
    const msg = errDetail(err, 'Analysis failed. Large files can take a long time — keep this tab open.')
    error.value = msg
    finishAnalyzeProgress(false, msg)
    await load()
  } finally {
    analyzing.value = false
  }
}

function runGenerateEoq() {
  if (!detail.value?.has_autovad_eoq) {
    error.value = 'Run Analyze first, then Generate Estimate Of Quantities.'
    return
  }
  generating.value = true
  error.value = null
  showEoqList.value = true
  generating.value = false
  requestAnimationFrame(() => {
    document.getElementById('training-eoq-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function goToEoqFromModal() {
  closeAnalyzeModal()
  runGenerateEoq()
}

onUnmounted(() => {
  clearAnalyzeProgressTimer()
  analyzeAbort?.abort()
})

function formatQty(q: unknown) {
  if (q == null || q === '') return '—'
  const n = Number(q)
  if (Number.isFinite(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 3 })
  return String(q)
}
</script>

<template>
  <div class="page-shell backend-lab">
    <div class="d-flex flex-wrap justify-space-between ga-2 mb-2">
      <div>
        <div class="page-kicker">Stage 1</div>
        <h1 class="brand-font text-h4 mb-1">Analyze plan</h1>
        <p class="muted mb-0">{{ detail?.name || '…' }} — same Analyze → Generate flow as user projects</p>
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
        <h2 class="brand-font text-h6 mb-2">Upload &amp; Analyze</h2>
        <p class="text-caption muted mb-3">
          Current sample: {{ detail.sample_filename || 'none' }}
          <span v-if="detail.actual_notes"> · {{ detail.actual_notes }}</span>
        </p>
        <v-file-input
          v-model="sampleFile"
          label="Sample plan PDF / DWG / DXF"
          accept=".pdf,.dxf,.xml,.landxml,.json,.dwg"
          prepend-icon=""
          prepend-inner-icon="mdi-file-cad"
          show-size
          :disabled="uploading || analyzing"
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
          <v-btn
            color="secondary"
            variant="tonal"
            :loading="uploading"
            :disabled="uploading || analyzing"
            @click="uploadSample"
          >
            {{ uploading ? `Uploading ${uploadProgress}%` : 'Upload sample' }}
          </v-btn>
          <v-btn
            color="primary"
            prepend-icon="mdi-brain"
            :loading="analyzing"
            :disabled="!detail.has_sample || analyzing"
            @click="runAnalyze"
          >
            Analyze
          </v-btn>
          <v-btn
            color="secondary"
            variant="tonal"
            :loading="generating"
            :disabled="!detail.has_autovad_eoq"
            @click="runGenerateEoq"
          >
            Generate Estimate Of Quantities
          </v-btn>
          <v-btn
            v-if="detail.has_autovad_eoq"
            variant="text"
            color="primary"
            :disabled="!detail.has_autovad_eoq"
            @click="router.push(`/backend/cases/${caseId}/original`)"
          >
            Next: Original EOQ →
          </v-btn>
        </div>
      </div>

      <div id="training-eoq-list" class="surface-panel pa-5">
        <div class="d-flex flex-wrap justify-space-between align-center ga-2 mb-3">
          <h2 class="brand-font text-h6 mb-0">Estimate Of Quantities</h2>
          <div class="d-flex flex-wrap ga-2" v-if="showEoqList && autovadItems.length">
            <v-chip size="small" variant="tonal">{{ autovadItems.length }} items</v-chip>
            <v-chip size="small" variant="tonal">{{ detail.actual_engine || 'autovad' }}</v-chip>
          </div>
        </div>

        <div v-if="!showEoqList" class="muted text-center py-10">
          Analyze the plan, then click <strong>Generate Estimate Of Quantities</strong> to show the full list here.
        </div>
        <div v-else-if="!autovadItems.length" class="muted text-center py-10">
          No quantity items yet. Re-run Analyze.
        </div>
        <v-table v-else density="comfortable" class="eoq-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Item Description</th>
              <th>Unit</th>
              <th>Approx. Quantity</th>
              <th>AI Confidence</th>
              <th>Category</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(it, idx) in autovadItems" :key="idx" class="eoq-row">
              <td class="text-center">{{ it.item_no ?? it.display_number ?? idx + 1 }}</td>
              <td>
                <div class="font-weight-medium">{{ it.description || '—' }}</div>
                <div v-if="it.calculation_method" class="text-caption muted">{{ it.calculation_method }}</div>
              </td>
              <td class="text-uppercase text-center">{{ String(it.unit || 'UNIT').toUpperCase() }}</td>
              <td class="text-right">{{ formatQty(it.quantity) }}</td>
              <td>{{ it.confidence != null ? `${Number(it.confidence).toFixed(2)}%` : '—' }}</td>
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
      <div class="analyze-modal running">
        <div class="analyze-modal-glow" aria-hidden="true" />
        <div class="analyze-modal-head">
          <div>
            <div class="page-kicker mb-1">Training lab</div>
            <h2 class="brand-font text-h5 mb-0">Uploading sample</h2>
          </div>
        </div>
        <p class="analyze-target muted">{{ uploadProgressLabel }}</p>
        <div class="analyze-meter">
          <div class="analyze-meter-top">
            <span>{{ uploadProgress >= 100 ? 'Finishing…' : 'Transfer in progress' }}</span>
            <b>{{ Math.round(uploadProgress) }}%</b>
          </div>
          <div class="analyze-track" aria-hidden="true">
            <i :style="{ width: `${uploadProgress}%` }" />
            <em v-if="uploadProgress < 100" class="analyze-pulse" />
          </div>
        </div>
      </div>
    </v-dialog>

    <v-dialog
      :model-value="analyzeModal"
      max-width="520"
      persistent
      scrim="rgba(3, 8, 6, 0.78)"
      content-class="training-analyze-dialog"
      @update:model-value="onAnalyzeModalToggle"
    >
      <div class="analyze-modal" :class="analyzeStatus">
        <div class="analyze-modal-glow" aria-hidden="true" />
        <div class="analyze-modal-head">
          <div>
            <div class="page-kicker mb-1">AutoVAD intelligence</div>
            <h2 class="brand-font text-h5 mb-0">Analyzing plans</h2>
          </div>
          <button
            v-if="analyzeStatus !== 'running'"
            type="button"
            class="analyze-close"
            aria-label="Close"
            @click="closeAnalyzeModal"
          >
            ✕
          </button>
        </div>

        <p class="analyze-target muted">
          Target · <strong>{{ analyzeTargetLabel }}</strong>
        </p>

        <div class="analyze-meter">
          <div class="analyze-meter-top">
            <span>{{ analyzeStage }}</span>
            <b>{{ Math.round(analyzeProgress) }}%</b>
          </div>
          <div class="analyze-track" aria-hidden="true">
            <i :style="{ width: `${analyzeProgress}%` }" />
            <em v-if="analyzeStatus === 'running'" class="analyze-pulse" />
          </div>
        </div>

        <ul class="analyze-steps">
          <li
            v-for="step in analyzeStages"
            :key="step.at"
            :class="{
              done: analyzeProgress >= step.at || analyzeStatus === 'success',
              active: analyzeStatus === 'running' && analyzeProgress >= step.at - 8 && analyzeProgress < step.at + 14,
            }"
          >
            <span />
            {{ step.label.replace('…', '') }}
          </li>
        </ul>

        <div v-if="analyzeStatusMessage" class="analyze-message" :class="analyzeStatus">
          {{ analyzeStatusMessage }}
        </div>

        <div v-if="analyzeCancelConfirm" class="analyze-warn">
          <div class="analyze-warn-title">Cancel analysis?</div>
          <p>
            Stopping now may leave an incomplete takeoff. You can run Analyze again later.
            Are you sure you want to cancel?
          </p>
          <div class="d-flex justify-end ga-2 flex-wrap">
            <v-btn variant="tonal" color="secondary" @click="dismissCancelWarning">Keep analyzing</v-btn>
            <v-btn color="error" @click="confirmCancelAnalyze">Yes, cancel</v-btn>
          </div>
        </div>

        <div v-else class="analyze-actions">
          <v-btn
            v-if="analyzeStatus === 'running'"
            variant="outlined"
            color="error"
            prepend-icon="mdi-stop-circle-outline"
            @click="requestCancelAnalyze"
          >
            Cancel analyze
          </v-btn>
          <template v-else>
            <v-btn variant="tonal" color="secondary" @click="closeAnalyzeModal">Close</v-btn>
            <v-btn
              v-if="analyzeStatus === 'success'"
              color="primary"
              @click="goToEoqFromModal"
            >
              Generate Estimate Of Quantities
            </v-btn>
            <v-btn
              v-else-if="analyzeStatus === 'error' || analyzeStatus === 'cancelled'"
              color="primary"
              @click="closeAnalyzeModal()"
            >
              Try again later
            </v-btn>
          </template>
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
.eoq-row td {
  vertical-align: top;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.analyze-modal {
  position: relative;
  overflow: hidden;
  background: linear-gradient(165deg, #12211c 0%, #0a1512 55%, #07110e 100%);
  border: 1px solid rgba(217, 255, 67, 0.28);
  color: #eaf0eb;
  padding: 26px 26px 22px;
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.55);
}

.analyze-modal-glow {
  position: absolute;
  width: 220px;
  height: 220px;
  right: -60px;
  top: -80px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(217, 255, 67, 0.18), transparent 68%);
  pointer-events: none;
}

.analyze-modal-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.analyze-close {
  border: 1px solid #31433b;
  background: #12201b;
  color: #9aa79f;
  width: 34px;
  height: 34px;
  cursor: pointer;
}

.analyze-close:hover {
  border-color: var(--acid, #d9ff43);
  color: var(--acid, #d9ff43);
}

.analyze-target {
  font-size: 0.86rem;
  margin-bottom: 18px;
}

.analyze-target strong {
  color: #eaf0eb;
  word-break: break-word;
}

.analyze-meter-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.72rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(234, 240, 235, 0.55);
}

.analyze-meter-top b {
  color: var(--acid, #d9ff43);
  font-size: 1.35rem;
  letter-spacing: -0.03em;
  font-family: inherit;
}

.analyze-track {
  position: relative;
  height: 8px;
  background: #1a2b24;
  overflow: hidden;
}

.analyze-track i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #85ffd0, #d9ff43);
  box-shadow: 0 0 14px rgba(217, 255, 67, 0.45);
  transition: width 0.35s ease;
}

.analyze-pulse {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 40%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.28), transparent);
  animation: analyze-sweep 1.4s linear infinite;
}

.analyze-steps {
  list-style: none;
  padding: 0;
  margin: 18px 0 0;
  display: grid;
  gap: 7px;
}

.analyze-steps li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.8rem;
  color: rgba(234, 240, 235, 0.38);
}

.analyze-steps li span {
  width: 8px;
  height: 8px;
  border: 1px solid #3a4d44;
  background: transparent;
  flex: 0 0 auto;
}

.analyze-steps li.done {
  color: rgba(234, 240, 235, 0.78);
}

.analyze-steps li.done span {
  background: #85ffd0;
  border-color: #85ffd0;
  box-shadow: 0 0 8px rgba(133, 255, 208, 0.45);
}

.analyze-steps li.active {
  color: var(--acid, #d9ff43);
}

.analyze-steps li.active span {
  border-color: var(--acid, #d9ff43);
  background: rgba(217, 255, 67, 0.35);
  animation: analyze-blink 1s ease infinite;
}

.analyze-message {
  margin-top: 16px;
  padding: 12px 14px;
  border: 1px solid #31433b;
  font-size: 0.86rem;
  line-height: 1.5;
  background: rgba(255, 255, 255, 0.02);
}

.analyze-message.success {
  border-color: rgba(133, 255, 208, 0.4);
  color: #b8f0d8;
}

.analyze-message.error,
.analyze-message.cancelled {
  border-color: rgba(255, 139, 107, 0.45);
  color: #ffc2b0;
}

.analyze-warn {
  margin-top: 16px;
  padding: 14px;
  border: 1px solid rgba(255, 195, 106, 0.45);
  background: rgba(255, 195, 106, 0.06);
}

.analyze-warn-title {
  font-weight: 700;
  color: #ffc36a;
  margin-bottom: 6px;
}

.analyze-warn p {
  margin: 0 0 14px;
  font-size: 0.86rem;
  color: rgba(234, 240, 235, 0.78);
  line-height: 1.5;
}

.analyze-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

@keyframes analyze-sweep {
  from {
    transform: translateX(-120%);
  }
  to {
    transform: translateX(320%);
  }
}

@keyframes analyze-blink {
  50% {
    opacity: 0.45;
  }
}
</style>
