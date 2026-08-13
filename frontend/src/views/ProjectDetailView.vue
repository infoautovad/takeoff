<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { useRoute, useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import { downloadDocument } from '@/api/documents'
import { analyzeDocument, analyzeProject, askChat, intelligenceStatus, listAnalyses, listChat, type IntelligenceStatus } from '@/api/ai'
import { downloadBoqCsv, downloadBoqExcel, generateBoq, listBoqs, updateBoqApproval } from '@/api/boq'
import { createEstimate, listEstimates, listSor, uploadSor } from '@/api/cost'
import { compareBoqs, compareDrawings, listComparisons } from '@/api/compare'
import { generateReports, listReports } from '@/api/reports'
import { listMembers, shareProject } from '@/api/projects'
import {
  cadCapabilities,
  listCadModels,
  processAllCad,
  processCadDocument,
  setupDesignAutomation,
  type CadCapabilities,
  type CadModel,
} from '@/api/cad'
import {
  activateBidTemplate,
  deleteBidTemplate,
  listBidTemplates,
  mapBoqToBid,
  uploadBidTemplate,
  type BidMapResult,
  type BidTemplate,
} from '@/api/bid'
import type { AnalysisResult, BOQ, ChatMessage } from '@/types'
import {
  boqItemStatusColor,
  boqItemStatusLabel,
  formatBytes,
  formatDate,
  formatQty,
  standardBidItemNumber,
  statusColor,
} from '@/utils/format'

const route = useRoute()
const router = useRouter()
const store = useProjectsStore()
const projectId = computed(() => Number(route.params.id))
const tab = ref((route.query.tab as string) || 'documents')

const uploading = ref(false)
const uploadError = ref<string | null>(null)
const revisionLabel = ref('')
const notes = ref('')
const selectedFiles = ref<File[]>([])
const editDialog = ref(false)
const editName = ref('')
const editDescription = ref('')
const editStatus = ref('active')
const saving = ref(false)
const analyzing = ref(false)
const analyzeError = ref<string | null>(null)
const analyzeModal = ref(false)
const analyzeCancelConfirm = ref(false)
const analyzeProgress = ref(0)
const analyzeStage = ref('Preparing…')
const analyzeTargetLabel = ref('documents')
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
const analyses = ref<AnalysisResult[]>([])
const boqs = ref<BOQ[]>([])
const activeBoq = ref<BOQ | null>(null)
const boqLoading = ref(false)
const boqSourceDocId = ref<number | null>(null)
const boqError = ref<string | null>(null)
const boqScopeDocIds = ref<number[]>([])
const chatMessages = ref<ChatMessage[]>([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatError = ref<string | null>(null)
const chatBox = ref<HTMLElement | null>(null)

const sorItems = ref<Array<{ id: number; description: string; unit: string; rate: number; item_code: string | null }>>([])
const estimates = ref<any[]>([])
const costLoading = ref(false)
const costError = ref<string | null>(null)
const sorFile = ref<File[] | File | null>(null)

const leftBoqId = ref<number | null>(null)
const rightBoqId = ref<number | null>(null)
const leftDocId = ref<number | null>(null)
const rightDocId = ref<number | null>(null)
const comparisons = ref<any[]>([])
const compareLoading = ref(false)
const compareError = ref<string | null>(null)

const reports = ref<any[]>([])
const reportLoading = ref(false)

const members = ref<any[]>([])
const shareEmail = ref('')
const shareRole = ref('engineer')
const shareError = ref<string | null>(null)

const cadModels = ref<CadModel[]>([])
const cadLoading = ref(false)
const cadSetupLoading = ref(false)
const cadError = ref<string | null>(null)
const cadSetupMessage = ref<string | null>(null)
const intelStatus = ref<IntelligenceStatus | null>(null)
const cadCaps = ref<CadCapabilities | null>(null)

const bidTemplates = ref<BidTemplate[]>([])
const bidFile = ref<File[] | File | null>(null)
const bidLoading = ref(false)
const bidError = ref<string | null>(null)
const bidMapResult = ref<BidMapResult | null>(null)

const statuses = [
  { title: 'Draft', value: 'draft' },
  { title: 'Active', value: 'active' },
  { title: 'In Review', value: 'in_review' },
  { title: 'Approved', value: 'approved' },
  { title: 'Archived', value: 'archived' },
]
const suggestedQuestions = [
  'Analyze all files',
  'Generate BOQ',
  'Update my BOQ Excel',
  'Process CAD',
  'Project status',
  'What items are in the BOQ?',
  'How much GSB is required?',
]

async function load() {
  await store.fetchProject(projectId.value)
  await Promise.all([
    loadAnalyses(),
    loadBoqs(),
    loadChat(),
    loadCost(),
    loadComparisons(),
    loadReports(),
    loadMembers(),
    loadCad(),
    loadIntelligence(),
    loadBidTemplates(),
  ])
}
async function loadCad() {
  cadModels.value = await listCadModels(projectId.value)
}
async function loadIntelligence() {
  try {
    const [status, caps] = await Promise.all([intelligenceStatus(), cadCapabilities()])
    intelStatus.value = status
    cadCaps.value = caps
  } catch {
    intelStatus.value = null
    cadCaps.value = null
  }
}
async function loadBidTemplates() {
  bidTemplates.value = await listBidTemplates(projectId.value)
}

async function uploadBidFile() {
  const file = Array.isArray(bidFile.value) ? bidFile.value[0] : bidFile.value
  if (!file) return
  bidLoading.value = true
  bidError.value = null
  try {
    await uploadBidTemplate(projectId.value, file)
    bidFile.value = null
    await loadBidTemplates()
  } catch (err) {
    bidError.value = extractDetail(err, 'Bid template upload failed')
  } finally {
    bidLoading.value = false
  }
}

async function activateBid(id: number) {
  bidLoading.value = true
  try {
    await activateBidTemplate(projectId.value, id)
    await loadBidTemplates()
  } catch (err) {
    bidError.value = extractDetail(err, 'Could not activate template')
  } finally {
    bidLoading.value = false
  }
}

async function removeBid(id: number) {
  bidLoading.value = true
  try {
    await deleteBidTemplate(projectId.value, id)
    await loadBidTemplates()
  } catch (err) {
    bidError.value = extractDetail(err, 'Could not delete template')
  } finally {
    bidLoading.value = false
  }
}

async function runBidMap() {
  if (!activeBoq.value) {
    bidError.value = 'Generate a BOQ first, then re-map it to the active bid template.'
    return
  }
  if (!bidTemplates.length) {
    bidError.value = 'Upload and activate a bid template first.'
    return
  }
  bidLoading.value = true
  bidError.value = null
  try {
    bidMapResult.value = await mapBoqToBid(projectId.value, activeBoq.value.id)
    await loadBoqs()
    tab.value = 'boq'
  } catch (err) {
    bidError.value = extractDetail(err, 'Re-map to template failed')
  } finally {
    bidLoading.value = false
  }
}

async function loadAnalyses() { analyses.value = await listAnalyses(projectId.value) }
async function loadBoqs() {
  boqs.value = await listBoqs(projectId.value)
  activeBoq.value = boqs.value[0] || null
  if (boqs.value.length >= 2) {
    leftBoqId.value = boqs.value[1]?.id ?? null
    rightBoqId.value = boqs.value[0]?.id ?? null
  }
}
async function loadChat() {
  chatMessages.value = await listChat(projectId.value)
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}
async function loadCost() {
  sorItems.value = await listSor(projectId.value)
  estimates.value = await listEstimates(projectId.value)
}
async function loadComparisons() { comparisons.value = await listComparisons(projectId.value) }
async function loadReports() { reports.value = await listReports(projectId.value) }
async function loadMembers() { members.value = await listMembers(projectId.value) }

onMounted(load)
watch(projectId, load)
watch(tab, (v) => router.replace({ query: { ...route.query, tab: v } }))

function onFileChange(files: File[] | File | null) {
  selectedFiles.value = !files ? [] : Array.isArray(files) ? files : [files]
}
function extractDetail(err: unknown, fallback: string) {
  if (typeof err === 'object' && err && 'response' in err) {
    const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
    if (detail) return detail
  }
  const code = (err as { code?: string })?.code
  if (code === 'ECONNABORTED' || /timeout/i.test(String((err as { message?: string })?.message || ''))) {
    return fallback
  }
  return fallback
}
function analysisFor(docId: number) { return analyses.value.find((a) => a.document_id === docId) }

function isCadDocument(doc?: { document_type?: string; original_filename?: string } | null) {
  if (!doc) return false
  const t = (doc.document_type || '').toLowerCase()
  if (['dxf', 'dwg', 'landxml', 'civil3d'].includes(t)) return true
  return /\.(dxf|dwg|xml|landxml|json)$/i.test(doc.original_filename || '')
}

const pdfAnalyzeTips =
  'Tips: Prefer a cleaner PDF/A or “Print to PDF” from CAD with fonts/images embedded. Analyze renders plan sheets for OpenAI vision (drawings + text/tables). MuPDF console warnings alone are not always a hard failure.'
const cadAnalyzeTips =
  'Tips: DWG uses Autodesk APS (not PDF vision). Ensure AUTODESK_CLIENT_ID/SECRET are set, or export DWG → DXF for local parsing. Large DWGs can take several minutes.'

function withFileTips(message: string, cad: boolean) {
  return `${message} ${cad ? cadAnalyzeTips : pdfAnalyzeTips}`
}

async function uploadFiles() {
  if (!selectedFiles.value.length) { uploadError.value = 'Choose at least one file'; return }
  uploading.value = true
  uploadError.value = null
  try {
    for (const file of selectedFiles.value) {
      await store.upload(projectId.value, file, revisionLabel.value || undefined, notes.value || undefined)
    }
    selectedFiles.value = []
    revisionLabel.value = ''
    notes.value = ''
  } catch (err) { uploadError.value = extractDetail(err, 'Upload failed') }
  finally { uploading.value = false }
}
function openEdit() {
  if (!store.currentProject) return
  editName.value = store.currentProject.name
  editDescription.value = store.currentProject.description || ''
  editStatus.value = store.currentProject.status
  editDialog.value = true
}
async function saveEdit() {
  saving.value = true
  try {
    await store.update(projectId.value, {
      name: editName.value.trim(),
      description: editDescription.value,
      status: editStatus.value as any,
    })
    editDialog.value = false
  } finally { saving.value = false }
}
async function archiveProject() {
  if (!confirm('Archive this project?')) return
  await store.archive(projectId.value)
  router.push('/projects')
}

async function deleteProject() {
  const name = store.currentProject?.name || 'this project'
  if (
    !confirm(
      `Permanently delete "${name}"?\n\nThis removes the project, documents, BOQs, and related data. This cannot be undone.`,
    )
  ) {
    return
  }
  try {
    await store.remove(projectId.value)
    router.push('/projects')
  } catch (err) {
    analyzeError.value = extractDetail(err, 'Could not delete project')
  }
}
async function removeDoc(id: number) {
  if (!confirm('Delete this document?')) return
  await store.removeDocument(id)
  await loadAnalyses()
}
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
    const next = Math.min(94, analyzeProgress.value + (analyzeProgress.value < 40 ? 1.4 : analyzeProgress.value < 70 ? 0.7 : 0.35))
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
    analyzeStatusMessage.value = message || 'Takeoff signals are ready. You can generate a BOQ next.'
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
  analyzeStatusMessage.value = 'Analysis was cancelled. Partial server work may still finish in the background — re-run Analyze if needed.'
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
  return axios.isCancel(err) || (err as { code?: string; name?: string })?.code === 'ERR_CANCELED'
    || (err as { name?: string })?.name === 'CanceledError'
}

async function runAnalyzeAll() {
  if (analyzing.value) return
  analyzing.value = true
  analyzeError.value = null
  analyzeAbort = new AbortController()
  const hasCad = store.documents.some((d) => isCadDocument(d))
  const hasPdf = store.documents.some((d) => !isCadDocument(d))
  startAnalyzeProgress(`${store.documents.length || 'all'} project file(s)`, hasCad && !hasPdf)
  try {
    const results = await analyzeProject(projectId.value, { signal: analyzeAbort.signal })
    const failed = results.filter((r) => r.status === 'failed')
    await store.fetchProject(projectId.value)
    await loadAnalyses()
    await loadCad()
    if (failed.length) {
      const failedDoc = store.documents.find((d) => d.id === failed[0]?.document_id)
      const msg = failed[0]?.error || `Analysis failed for ${failed.length} file(s).`
      analyzeError.value = withFileTips(msg, isCadDocument(failedDoc))
      finishAnalyzeProgress(false, msg)
    } else {
      finishAnalyzeProgress(true, `Analyzed ${results.length} file(s) successfully.`)
    }
  } catch (err) {
    if (isAnalyzeCanceled(err)) return
    const msg = extractDetail(
      err,
      hasCad
        ? 'CAD/DWG processing timed out or failed. Autodesk APS can take several minutes — try again, or export DWG → DXF.'
        : 'Analysis failed (large PDFs can take a few minutes — try again if it timed out).',
    )
    analyzeError.value = withFileTips(msg, hasCad)
    finishAnalyzeProgress(false, msg)
  } finally {
    analyzing.value = false
  }
}

async function runAnalyzeOne(documentId: number) {
  if (analyzing.value) return
  const doc = store.documents.find((d) => d.id === documentId)
  const cad = isCadDocument(doc)
  analyzing.value = true
  analyzeError.value = null
  analyzeAbort = new AbortController()
  startAnalyzeProgress(doc?.original_filename || `Document #${documentId}`, cad)
  try {
    const result = await analyzeDocument(documentId, { signal: analyzeAbort.signal })
    await store.fetchProject(projectId.value)
    await loadAnalyses()
    if (cad) await loadCad()
    if (result.status === 'failed') {
      const msg = result.error || (cad ? 'CAD processing failed.' : 'Analysis failed.')
      analyzeError.value = withFileTips(msg, cad)
      finishAnalyzeProgress(false, msg)
    } else {
      const count = result.analysis?.findings?.items?.length ?? 0
      const cadNote = cad ? ' (CAD / APS takeoff)' : ''
      finishAnalyzeProgress(true, `Found ${count} quantity item(s) from this file${cadNote}.`)
    }
  } catch (err) {
    if (isAnalyzeCanceled(err)) return
    const msg = extractDetail(
      err,
      cad
        ? 'CAD/DWG processing timed out or failed. Autodesk APS can take several minutes — try again, or export DWG → DXF.'
        : 'Analysis failed (large PDFs can take a few minutes — try again if it timed out).',
    )
    analyzeError.value = withFileTips(msg, cad)
    finishAnalyzeProgress(false, msg)
  } finally {
    analyzing.value = false
  }
}

onUnmounted(() => {
  clearAnalyzeProgressTimer()
  analyzeAbort?.abort()
})
async function runGenerateBoq(documentIds?: number[]) {
  boqLoading.value = true
  boqSourceDocId.value = documentIds?.length === 1 ? documentIds[0]! : null
  boqError.value = null
  try {
    const boq = await generateBoq(
      projectId.value,
      documentIds?.length ? { documentIds } : undefined,
    )
    await loadBoqs()
    activeBoq.value = boq
    tab.value = 'boq'
  } catch (err) {
    boqError.value = extractDetail(err, 'BOQ generation failed')
  } finally {
    boqLoading.value = false
    boqSourceDocId.value = null
  }
}

async function runGenerateBoqForDoc(documentId: number) {
  await runGenerateBoq([documentId])
}

async function runGenerateBoqScoped() {
  if (!boqScopeDocIds.value.length) {
    boqError.value = 'Select one or more files, or use Generate (all files).'
    return
  }
  await runGenerateBoq([...boqScopeDocIds.value])
}

function toggleBoqScope(docId: number) {
  const idx = boqScopeDocIds.value.indexOf(docId)
  if (idx >= 0) boqScopeDocIds.value.splice(idx, 1)
  else boqScopeDocIds.value.push(docId)
}
async function exportExcel() {
  if (!activeBoq.value) return
  await downloadBoqExcel(activeBoq.value.id, `AutoVAD_BOQ_v${activeBoq.value.version}.xlsx`)
}
async function exportCsv() {
  if (!activeBoq.value) return
  await downloadBoqCsv(activeBoq.value.id, `AutoVAD_BOQ_v${activeBoq.value.version}.csv`)
}
async function approval(action: 'submit' | 'approve' | 'reject') {
  if (!activeBoq.value) return
  activeBoq.value = await updateBoqApproval(activeBoq.value.id, action)
  await loadBoqs()
  await store.fetchProject(projectId.value)
}
function openSource(item: { source_document_id: number | null; source_page: number | null }) {
  if (!item.source_document_id) return
  router.push({
    name: 'document-viewer',
    params: { documentId: item.source_document_id },
    query: { page: String(item.source_page || 1) },
  })
}
async function sendChat(question?: string) {
  const q = (question ?? chatInput.value).trim()
  if (!q) return
  chatLoading.value = true
  chatError.value = null
  chatInput.value = ''
  try {
    await askChat(projectId.value, q)
    await Promise.all([loadChat(), loadAnalyses(), loadBoqs(), loadCad(), loadCost(), loadBidTemplates()])
    await store.fetchProject(projectId.value)
  } catch (err) {
    chatError.value = extractDetail(err, 'Chat failed')
  } finally {
    chatLoading.value = false
  }
}

function chatDownloads(msg: ChatMessage) {
  return (msg.sources || []).filter((s) => s.type === 'download')
}

async function downloadFromChat(src: Record<string, unknown>) {
  const href = String(src.href || '')
  const filename = String(src.filename || 'download.bin')
  if (!href) return
  // Reuse authenticated API client via existing BOQ helpers when possible
  if (href.includes('/export/excel')) {
    const boqId = Number(href.split('/boq/')[1]?.split('/')[0])
    if (boqId) {
      await downloadBoqExcel(boqId, filename)
      return
    }
  }
  if (href.includes('/export/csv')) {
    const boqId = Number(href.split('/boq/')[1]?.split('/')[0])
    if (boqId) {
      await downloadBoqCsv(boqId, filename)
      return
    }
  }
}
async function uploadSorFile() {
  const file = Array.isArray(sorFile.value) ? sorFile.value[0] : sorFile.value
  if (!file) { costError.value = 'Choose SOR CSV/Excel file'; return }
  costLoading.value = true
  costError.value = null
  try {
    await uploadSor(projectId.value, file)
    sorFile.value = null
    await loadCost()
  } catch (err) { costError.value = extractDetail(err, 'SOR upload failed') }
  finally { costLoading.value = false }
}
async function runEstimate() {
  if (!activeBoq.value) { costError.value = 'Generate a BOQ first'; return }
  costLoading.value = true
  costError.value = null
  try {
    await createEstimate(projectId.value, activeBoq.value.id)
    await loadCost()
    await loadBoqs()
  } catch (err) { costError.value = extractDetail(err, 'Cost estimate failed') }
  finally { costLoading.value = false }
}
async function runBoqCompare() {
  if (!leftBoqId.value || !rightBoqId.value) return
  compareLoading.value = true
  compareError.value = null
  try {
    await compareBoqs(projectId.value, leftBoqId.value, rightBoqId.value)
    await loadComparisons()
  } catch (err) { compareError.value = extractDetail(err, 'BOQ compare failed') }
  finally { compareLoading.value = false }
}
async function runDrawingCompare() {
  if (!leftDocId.value || !rightDocId.value) return
  compareLoading.value = true
  compareError.value = null
  try {
    await compareDrawings(projectId.value, leftDocId.value, rightDocId.value)
    await loadComparisons()
  } catch (err) { compareError.value = extractDetail(err, 'Drawing compare failed') }
  finally { compareLoading.value = false }
}
async function runReports() {
  reportLoading.value = true
  try { reports.value = await generateReports(projectId.value) }
  finally { reportLoading.value = false }
}
async function share() {
  shareError.value = null
  try {
    await shareProject(projectId.value, shareEmail.value.trim(), shareRole.value)
    shareEmail.value = ''
    await loadMembers()
  } catch (err) { shareError.value = extractDetail(err, 'Share failed') }
}

async function runCadAll() {
  cadLoading.value = true
  cadError.value = null
  try {
    cadModels.value = await processAllCad(projectId.value)
    await store.fetchProject(projectId.value)
    await loadAnalyses()
  } catch (err) {
    cadError.value = extractDetail(err, 'CAD processing failed')
  } finally {
    cadLoading.value = false
  }
}

async function runDesignAutomationSetup() {
  cadSetupLoading.value = true
  cadError.value = null
  cadSetupMessage.value = null
  try {
    const result = await setupDesignAutomation()
    await loadIntelligence()
    cadCaps.value = await cadCapabilities()
    cadSetupMessage.value =
      `Design Automation ready · nickname ${result.nickname} · engine ${result.engine} · ` +
      `DXF activity ${result.dxf_activity}` +
      (result.plugin_activity ? ` · plugin ${result.plugin_activity}` : ' · plugin AppBundle not installed (DXF mode OK)')
  } catch (err) {
    cadError.value = extractDetail(err, 'Design Automation setup failed')
  } finally {
    cadSetupLoading.value = false
  }
}

async function runCadOne(documentId: number) {
  cadLoading.value = true
  cadError.value = null
  try {
    await processCadDocument(documentId)
    await loadCad()
    await store.fetchProject(projectId.value)
  } catch (err) {
    cadError.value = extractDetail(err, 'CAD processing failed')
  } finally {
    cadLoading.value = false
  }
}

const cadDocuments = computed(() =>
  store.documents.filter((d) => ['dxf', 'dwg', 'landxml', 'civil3d'].includes(d.document_type) || /\.(dxf|dwg|xml|landxml|json)$/i.test(d.original_filename)),
)
</script>

<template>
  <div class="page-shell">
    <div v-if="store.loading && !store.currentProject" class="text-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>
    <template v-else-if="store.currentProject">
      <div class="d-flex flex-wrap align-start justify-space-between mb-4 ga-3">
        <div>
          <v-btn variant="text" color="primary" prepend-icon="mdi-arrow-left" class="mb-2 px-0" @click="router.push('/projects')">Back to projects</v-btn>
          <div class="page-kicker">Project workspace</div>
          <div class="d-flex align-center ga-3 mb-2">
            <h1 class="brand-font text-h4 mb-0">{{ store.currentProject.name }}</h1>
            <v-chip size="small" class="status-chip" :color="statusColor(store.currentProject.status)" variant="tonal">
              {{ store.currentProject.status.replace('_', ' ') }}
            </v-chip>
          </div>
          <p class="muted mb-0">{{ store.currentProject.description || 'No description provided.' }}</p>
        </div>
        <div class="d-flex flex-wrap ga-2">
          <v-btn color="primary" :loading="analyzing" prepend-icon="mdi-brain" @click="runAnalyzeAll">Analyze</v-btn>
          <v-btn color="secondary" variant="tonal" :loading="boqLoading" @click="runGenerateBoq()">Generate BOQ</v-btn>
          <v-btn variant="tonal" @click="openEdit">Edit</v-btn>
          <v-btn variant="outlined" color="warning" @click="archiveProject">Archive</v-btn>
          <v-btn variant="outlined" color="error" prepend-icon="mdi-delete-outline" @click="deleteProject">
            Delete
          </v-btn>
        </div>
      </div>

      <v-alert v-if="analyzeError || boqError" type="error" variant="tonal" class="mb-4" closable @click:close="analyzeError = null; boqError = null">
        {{ analyzeError || boqError }}
      </v-alert>

      <v-tabs v-model="tab" color="primary" class="mb-4" show-arrows>
        <v-tab value="documents">Documents</v-tab>
        <v-tab value="cad">CAD / Civil 3D</v-tab>
        <v-tab value="boq">BOQ</v-tab>
        <v-tab value="bid">Bid templates</v-tab>
        <v-tab value="cost">Cost</v-tab>
        <v-tab value="compare">Compare</v-tab>
        <v-tab value="reports">Reports</v-tab>
        <v-tab value="team">Team</v-tab>
        <v-tab value="chat">AI Chat</v-tab>
      </v-tabs>

      <v-tabs-window v-model="tab">
        <v-tabs-window-item value="documents">
          <v-row>
            <v-col cols="12" lg="5">
              <div class="surface-panel pa-5">
                <h2 class="brand-font text-h6 mb-3">Upload documents</h2>
                <v-alert v-if="uploadError" type="error" variant="tonal" class="mb-3">{{ uploadError }}</v-alert>
                <v-file-input :model-value="selectedFiles" multiple show-size prepend-icon="" prepend-inner-icon="mdi-paperclip" accept=".pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.tif,.tiff,.zip,.dxf,.dwg,.xml,.landxml,.json" class="mb-2" @update:model-value="onFileChange" />
                <p class="text-caption muted mb-2">
                  PDF/Excel/CSV for document AI. DXF/DWG/LandXML/JSON for CAD &amp; Civil 3D Intelligence Engine.
                </p>
                <details class="plan-tips mb-3">
                  <summary>Plan file tips (optional)</summary>
                  <ul class="doc-tips mt-2 mb-0">
                    <li>PDF: Analyze uses text/tables + OpenAI vision on plan sheets.</li>
                    <li>DWG: use Process CAD / Analyze on that file — Autodesk APS (not PDF vision). Or export DWG → DXF for local parse.</li>
                    <li>Per-file BOQ: use the BOQ button on a file, or select files on the BOQ tab.</li>
                    <li>If a run fails, check the red error and each file’s status — MuPDF console warnings alone are not always a hard failure.</li>
                  </ul>
                </details>
                <v-text-field v-model="revisionLabel" label="Revision label" class="mb-2" />
                <v-textarea v-model="notes" label="Notes" rows="2" class="mb-3" />
                <v-btn color="primary" block :loading="uploading" @click="uploadFiles">Upload</v-btn>
              </div>
            </v-col>
            <v-col cols="12" lg="7">
              <div class="surface-panel pa-5">
                <h2 class="brand-font text-h6 mb-4">Files</h2>
                <div v-for="doc in store.documents" :key="doc.id" class="doc-row mb-3 pa-3">
                  <div class="d-flex flex-wrap justify-space-between ga-2">
                    <div>
                      <div class="font-weight-medium">{{ doc.original_filename }}</div>
                      <div class="text-caption muted">
                        {{ formatDate(doc.created_at) }} · {{ formatBytes(doc.file_size) }}
                        · {{ isCadDocument(doc) ? 'CAD (APS/DXF)' : 'Document AI' }}
                      </div>
                      <v-chip size="x-small" class="mt-2 status-chip" :color="statusColor(doc.processing_status)" variant="tonal">{{ doc.processing_status }}</v-chip>
                      <div v-if="doc.processing_status === 'failed' && doc.error_message" class="text-caption text-error mt-2">
                        {{ doc.error_message }}
                      </div>
                    </div>
                    <div class="d-flex flex-wrap ga-1">
                      <v-btn size="small" variant="tonal" :loading="analyzing" @click="runAnalyzeOne(doc.id)">
                        {{ isCadDocument(doc) ? 'Process CAD' : 'Analyze' }}
                      </v-btn>
                      <v-btn
                        size="small"
                        color="secondary"
                        variant="tonal"
                        :loading="boqLoading && boqSourceDocId === doc.id"
                        :disabled="doc.processing_status === 'processing' || doc.processing_status === 'pending'"
                        @click="runGenerateBoqForDoc(doc.id)"
                      >
                        BOQ
                      </v-btn>
                      <v-btn size="small" variant="text" @click="router.push(`/viewer/${doc.id}`)">Open source</v-btn>
                      <v-btn icon="mdi-download" size="small" variant="text" @click="downloadDocument(doc.id, doc.original_filename)" />
                      <v-btn icon="mdi-delete-outline" size="small" variant="text" color="error" @click="removeDoc(doc.id)" />
                    </div>
                  </div>
                  <div v-if="analysisFor(doc.id)" class="analysis-box mt-3 pa-3">
                    <div class="text-caption mb-1">{{ analysisFor(doc.id)?.engine }} · {{ analysisFor(doc.id)?.findings?.items?.length || 0 }} items</div>
                    <div class="text-body-2">{{ analysisFor(doc.id)?.summary }}</div>
                  </div>
                </div>
              </div>
            </v-col>
          </v-row>
        </v-tabs-window-item>

        <v-tabs-window-item value="cad">
          <div class="surface-panel pa-5">
            <div class="d-flex flex-wrap justify-space-between align-start ga-3 mb-4">
              <div>
                <h2 class="brand-font text-h6 mb-1">CAD & Civil 3D Intelligence Engine</h2>
                <p class="muted text-body-2 mb-0">
                  DWG runs through Autodesk <strong>Design Automation</strong> (cloud AutoCAD) when enabled,
                  with Model Derivative as fallback. DXF / LandXML parse locally → quantity takeoff → BOQ.
                </p>
              </div>
              <div class="d-flex flex-wrap ga-2">
                <v-btn
                  variant="tonal"
                  color="secondary"
                  :loading="cadSetupLoading"
                  prepend-icon="mdi-cloud-cog-outline"
                  @click="runDesignAutomationSetup"
                >
                  Setup Design Automation
                </v-btn>
                <v-btn color="primary" :loading="cadLoading" prepend-icon="mdi-vector-polyline" @click="runCadAll">
                  Process CAD files
                </v-btn>
              </div>
            </div>

            <v-alert
              :type="intelStatus?.design_automation?.configured || intelStatus?.autodesk_aps?.configured ? 'success' : 'info'"
              variant="tonal"
              class="mb-4"
            >
              <div class="d-flex flex-wrap ga-2 mb-2">
                <v-chip size="small" :color="intelStatus?.openai?.configured ? 'success' : 'warning'" variant="tonal">
                  OpenAI: {{ intelStatus?.openai?.configured ? `on (${intelStatus.openai.model})` : 'heuristic fallback' }}
                </v-chip>
                <v-chip
                  size="small"
                  :color="intelStatus?.design_automation?.configured ? 'success' : 'warning'"
                  variant="tonal"
                >
                  Design Automation:
                  {{
                    intelStatus?.design_automation?.configured
                      ? `on (${intelStatus.design_automation.preferred || 'dwg_to_dxf'})`
                      : 'off'
                  }}
                </v-chip>
                <v-chip size="small" :color="intelStatus?.autodesk_aps?.configured ? 'success' : 'warning'" variant="tonal">
                  APS Model Derivative: {{ intelStatus?.autodesk_aps?.configured ? 'fallback ready' : 'not configured' }}
                </v-chip>
                <v-chip size="small" color="primary" variant="tonal">DXF / LandXML: local</v-chip>
              </div>
              <div class="text-body-2">
                <template v-if="!intelStatus?.autodesk_aps?.configured">
                  DWG needs <code>AUTODESK_CLIENT_ID</code> + <code>AUTODESK_CLIENT_SECRET</code> in <code>backend/.env</code>,
                  with <strong>Design Automation API</strong> enabled on the APS app — or export DWG → DXF.
                </template>
                <template v-else>
                  DWG processing order: <strong>Design Automation</strong> (cloud AutoCAD DWG→DXF or plugin)
                  → Model Derivative fallback → quantity takeoff{{ intelStatus?.openai?.configured ? ' + OpenAI' : '' }}.
                  Click <strong>Setup Design Automation</strong> once to register cloud activities.
                </template>
              </div>
            </v-alert>
            <v-alert v-if="cadSetupMessage" type="success" variant="tonal" class="mb-4" closable @click:close="cadSetupMessage = null">
              {{ cadSetupMessage }}
            </v-alert>
            <v-alert v-if="cadError" type="error" variant="tonal" class="mb-4">{{ cadError }}</v-alert>

            <h3 class="text-subtitle-2 mb-2">CAD documents in this project</h3>
            <div v-if="!cadDocuments.length" class="muted mb-4">No CAD files yet. Upload .dxf / .dwg / .xml / .landxml / Civil JSON in Documents.</div>
            <div v-for="doc in cadDocuments" :key="doc.id" class="doc-row pa-3 mb-2 d-flex justify-space-between align-center">
              <div>
                <div class="font-weight-medium">{{ doc.original_filename }}</div>
                <div class="text-caption muted text-capitalize">{{ doc.document_type }} · {{ doc.processing_status }}</div>
              </div>
              <div class="d-flex ga-1">
                <v-btn size="small" variant="tonal" :loading="cadLoading" @click="runCadOne(doc.id)">Process</v-btn>
                <v-btn
                  size="small"
                  color="secondary"
                  variant="tonal"
                  :loading="boqLoading && boqSourceDocId === doc.id"
                  @click="runGenerateBoqForDoc(doc.id)"
                >
                  BOQ
                </v-btn>
              </div>
            </div>

            <h3 class="text-subtitle-2 mt-6 mb-2">Extraction results</h3>
            <div v-if="!cadModels.length" class="muted py-6 text-center">No CAD models processed yet.</div>
            <div v-for="m in cadModels" :key="m.id" class="analysis-box pa-4 mb-3">
              <div class="d-flex flex-wrap justify-space-between ga-2 mb-2">
                <div class="font-weight-medium">{{ m.source_format.toUpperCase() }} · {{ m.engine }}</div>
                <v-chip
                  size="small"
                  variant="tonal"
                  :color="m.status === 'quantified' || m.status === 'extracted' ? 'success' : m.status === 'needs_autodesk' || m.status === 'failed' ? 'warning' : 'primary'"
                >{{ m.status }}</v-chip>
              </div>
              <v-alert
                v-if="m.status === 'needs_autodesk'"
                type="warning"
                variant="tonal"
                density="compact"
                class="mb-2"
              >
                Native DWG requires Autodesk APS credentials. Set them in backend/.env and re-process, or upload a DXF export.
              </v-alert>
              <v-alert v-if="m.error_message" type="error" variant="tonal" density="compact" class="mb-2">{{ m.error_message }}</v-alert>
              <div class="text-body-2 mb-2">{{ m.summary }}</div>
              <div class="text-caption muted mb-2">
                Layers: {{ m.layers?.length || 0 }} ·
                Blocks: {{ m.blocks?.length || 0 }} ·
                Dimensions: {{ m.dimensions?.length || 0 }} ·
                Quantities: {{ m.quantities?.length || 0 }}
                <span v-if="m.units"> · Units: {{ m.units }}</span>
              </div>
              <v-table v-if="m.quantities?.length" density="compact">
                <thead>
                  <tr><th>Description</th><th>Layer</th><th>Unit</th><th>Qty</th><th>Confidence</th><th>Method</th></tr>
                </thead>
                <tbody>
                  <tr v-for="q in m.quantities" :key="q.id">
                    <td>{{ q.description }}</td>
                    <td>{{ q.layer || '—' }}</td>
                    <td>{{ q.unit }}</td>
                    <td>{{ formatQty(q.quantity) }}</td>
                    <td>{{ q.confidence != null ? `${q.confidence}%` : '—' }}</td>
                    <td class="text-caption">{{ q.calculation_method }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="boq">
          <div class="surface-panel pa-5">
            <div class="d-flex flex-wrap justify-space-between ga-3 mb-4">
              <div>
                <h2 class="brand-font text-h6 mb-1">Bill of Quantities</h2>
                <p class="muted text-body-2 mb-0">
                  Generate from all analyzed files, or select specific files below for a per-file BOQ.
                  With a bid template, only needed bid items are matched — not the full list.
                </p>
              </div>
              <div class="d-flex flex-wrap ga-2">
                <v-btn variant="tonal" :loading="boqLoading && !boqScopeDocIds.length" @click="runGenerateBoq()">Generate all</v-btn>
                <v-btn
                  color="secondary"
                  variant="tonal"
                  :loading="boqLoading && !!boqScopeDocIds.length"
                  :disabled="!boqScopeDocIds.length"
                  @click="runGenerateBoqScoped"
                >
                  Generate selected
                </v-btn>
                <v-btn
                  color="secondary"
                  variant="tonal"
                  :disabled="!activeBoq || !bidTemplates.length"
                  :loading="bidLoading"
                  title="Re-match an existing BOQ to the active bid template without regenerating"
                  @click="runBidMap"
                >
                  Re-map to template
                </v-btn>
                <v-btn color="primary" :disabled="!activeBoq" @click="exportExcel">Excel</v-btn>
                <v-btn variant="tonal" :disabled="!activeBoq" @click="exportCsv">CSV</v-btn>
                <v-btn variant="tonal" :disabled="!activeBoq" @click="approval('submit')">Submit review</v-btn>
                <v-btn color="success" variant="tonal" :disabled="!activeBoq" @click="approval('approve')">Approve</v-btn>
                <v-btn color="error" variant="tonal" :disabled="!activeBoq" @click="approval('reject')">Reject</v-btn>
              </div>
            </div>
            <div v-if="store.documents.length" class="doc-row mb-4 pa-3">
              <div class="text-caption muted mb-2">Select files for a separate BOQ (optional)</div>
              <div class="d-flex flex-wrap ga-2">
                <v-chip
                  v-for="doc in store.documents"
                  :key="`boq-scope-${doc.id}`"
                  filter
                  variant="outlined"
                  :color="boqScopeDocIds.includes(doc.id) ? 'secondary' : undefined"
                  @click="toggleBoqScope(doc.id)"
                >
                  {{ doc.original_filename }}
                  <span class="text-caption ms-1">({{ analysisFor(doc.id)?.findings?.items?.length || 0 }} items)</span>
                </v-chip>
              </div>
            </div>
            <div v-if="!activeBoq" class="muted text-center py-10">Analyze documents / process CAD, then generate BOQ.</div>
            <template v-else>
              <div class="d-flex flex-wrap ga-2 mb-3">
                <v-chip size="small" variant="tonal">{{ activeBoq.title }}</v-chip>
                <v-chip size="small" variant="tonal">{{ activeBoq.status }}</v-chip>
                <v-chip v-if="bidMapResult" size="small" color="success" variant="tonal">
                  Bid mapped {{ bidMapResult.matched }}/{{ bidMapResult.total }}
                </v-chip>
              </div>
              <v-table density="comfortable" class="boq-table">
                <thead>
                  <tr>
                    <th>Item No</th>
                    <th>Standard Bid Item Number</th>
                    <th>Item Description</th>
                    <th>Unit</th>
                    <th>Quantity</th>
                    <th>AI Confidence</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in activeBoq.items" :key="item.id">
                    <td>{{ item.item_number }}</td>
                    <td class="text-caption font-weight-medium">
                      {{ standardBidItemNumber(item) || '—' }}
                    </td>
                    <td>
                      <div class="font-weight-medium">{{ item.description }}</div>
                    </td>
                    <td class="text-uppercase">{{ (item.unit || 'UNIT').toUpperCase() }}</td>
                    <td>{{ formatQty(item.quantity) }}</td>
                    <td>{{ item.confidence != null ? `${Number(item.confidence).toFixed(2)}%` : '—' }}</td>
                    <td>
                      <v-chip
                        size="small"
                        variant="tonal"
                        :color="boqItemStatusColor(item)"
                      >
                        {{ boqItemStatusLabel(item) }}
                      </v-chip>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </template>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="bid">
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-1">Bid templates</h2>
            <p class="muted mb-4">
              Upload your agency bid list (PDF / Excel / CSV). AutoVAD reads it, then when you analyze design plans
              and <strong>Generate BOQ</strong>, only bid items evidenced in those plans are included (matched by
              code / description / unit). Without a template, AutoVAD uses its default CSI takeoff.
              <strong> Re-map to template</strong> only re-matches an existing BOQ — prefer Generate after Analyze.
            </p>
            <v-alert v-if="bidError" type="error" variant="tonal" class="mb-3">{{ bidError }}</v-alert>
            <v-file-input
              v-model="bidFile"
              label="Bid template (PDF / Excel / CSV)"
              accept=".pdf,.xlsx,.xls,.csv"
              prepend-icon=""
              prepend-inner-icon="mdi-file-table-outline"
              class="mb-3"
            />
            <div class="d-flex flex-wrap ga-2 mb-4">
              <v-btn color="primary" :loading="bidLoading" @click="uploadBidFile">Upload bid list</v-btn>
              <v-btn variant="tonal" :disabled="!activeBoq || !bidTemplates.length" :loading="bidLoading" @click="runBidMap">
                Re-map active BOQ
              </v-btn>
            </div>

            <div v-if="!bidTemplates.length" class="muted text-center py-8">No bid templates yet.</div>
            <div v-for="t in bidTemplates" :key="t.id" class="doc-row pa-3 mb-3">
              <div class="d-flex flex-wrap justify-space-between ga-2 mb-2">
                <div>
                  <div class="font-weight-medium">{{ t.name }}</div>
                  <div class="text-caption muted">{{ t.source_filename }} · {{ t.lines.length }} lines</div>
                </div>
                <div class="d-flex ga-2 align-center">
                  <v-chip size="small" :color="t.is_active ? 'success' : 'default'" variant="tonal">
                    {{ t.is_active ? 'Active' : 'Inactive' }}
                  </v-chip>
                  <v-btn size="small" variant="tonal" :disabled="t.is_active" @click="activateBid(t.id)">Activate</v-btn>
                  <v-btn size="small" variant="text" color="error" @click="removeBid(t.id)">Delete</v-btn>
                </div>
              </div>
              <v-table v-if="t.lines.length" density="compact">
                <thead>
                  <tr><th>Line</th><th>CSI</th><th>Code</th><th>Description</th><th>Unit</th><th>Rate</th></tr>
                </thead>
                <tbody>
                  <tr v-for="ln in t.lines.slice(0, 12)" :key="ln.id">
                    <td>{{ ln.line_number }}</td>
                    <td>{{ ln.csi_code || '—' }}</td>
                    <td>{{ ln.item_code || '—' }}</td>
                    <td>{{ ln.description }}</td>
                    <td>{{ ln.unit }}</td>
                    <td>{{ ln.default_rate ?? '—' }}</td>
                  </tr>
                </tbody>
              </v-table>
              <div v-if="t.lines.length > 12" class="text-caption muted mt-1">Showing first 12 of {{ t.lines.length }} lines</div>
            </div>

            <div v-if="bidMapResult" class="analysis-box pa-3 mt-4">
              Mapped {{ bidMapResult.matched }} / {{ bidMapResult.total }} BOQ items to “{{ bidMapResult.template_name }}”.
              Unmatched: {{ bidMapResult.unmatched }}.
            </div>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="cost">
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-2">Cost estimator</h2>
            <p class="muted mb-4">Upload Schedule of Rates (SOR), then match against BOQ quantities.</p>
            <v-alert v-if="costError" type="error" variant="tonal" class="mb-3">{{ costError }}</v-alert>
            <v-file-input v-model="sorFile" label="SOR CSV/Excel" accept=".csv,.xlsx,.xls" prepend-icon="" prepend-inner-icon="mdi-currency-usd" class="mb-3" />
            <div class="d-flex ga-2 mb-4">
              <v-btn color="secondary" variant="tonal" :loading="costLoading" @click="uploadSorFile">Upload SOR</v-btn>
              <v-btn color="primary" :loading="costLoading" @click="runEstimate">Estimate cost</v-btn>
            </div>
            <div class="text-body-2 mb-2">SOR items: {{ sorItems.length }}</div>
            <div v-if="estimates[0]" class="mb-4">
              <div class="stat-value mb-1">${{ Number(estimates[0].total_amount).toLocaleString() }}</div>
              <div class="muted">{{ estimates[0].title }}</div>
            </div>
            <v-table v-if="estimates[0]?.breakdown?.items" density="compact">
              <thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Matched</th></tr></thead>
              <tbody>
                <tr v-for="(row, idx) in estimates[0].breakdown.items" :key="idx">
                  <td>{{ row.description }}</td>
                  <td>{{ formatQty(row.quantity) }} {{ row.unit }}</td>
                  <td>{{ row.rate ?? '—' }}</td>
                  <td>{{ row.amount ?? '—' }}</td>
                  <td>{{ row.matched ? 'Yes' : 'No' }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="compare">
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-4">Comparisons</h2>
            <v-alert v-if="compareError" type="error" variant="tonal" class="mb-3">{{ compareError }}</v-alert>
            <v-row>
              <v-col cols="12" md="6">
                <h3 class="text-subtitle-2 mb-2">BOQ vs BOQ</h3>
                <v-select v-model="leftBoqId" :items="boqs" item-title="title" item-value="id" label="Left BOQ" class="mb-2" />
                <v-select v-model="rightBoqId" :items="boqs" item-title="title" item-value="id" label="Right BOQ" class="mb-2" />
                <v-btn color="primary" :loading="compareLoading" @click="runBoqCompare">Compare BOQs</v-btn>
              </v-col>
              <v-col cols="12" md="6">
                <h3 class="text-subtitle-2 mb-2">Drawing revision compare</h3>
                <v-select v-model="leftDocId" :items="store.documents" item-title="original_filename" item-value="id" label="Revision A" class="mb-2" />
                <v-select v-model="rightDocId" :items="store.documents" item-title="original_filename" item-value="id" label="Revision B" class="mb-2" />
                <v-btn color="secondary" variant="tonal" :loading="compareLoading" @click="runDrawingCompare">Compare drawings</v-btn>
              </v-col>
            </v-row>
            <div v-for="c in comparisons" :key="c.id" class="analysis-box mt-4 pa-3">
              <div class="font-weight-medium">{{ c.comparison_type.toUpperCase() }} · {{ c.left_label }} vs {{ c.right_label }}</div>
              <div class="text-body-2 mt-1">{{ c.summary }}</div>
            </div>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="reports">
          <div class="surface-panel pa-5">
            <div class="d-flex justify-space-between align-center mb-4">
              <h2 class="brand-font text-h6 mb-0">Reports</h2>
              <v-btn color="primary" :loading="reportLoading" @click="runReports">Generate reports</v-btn>
            </div>
            <div v-if="!reports.length" class="muted py-8 text-center">No reports yet.</div>
            <div v-for="r in reports" :key="r.id" class="doc-row pa-3 mb-3">
              <div class="font-weight-medium">{{ r.title }}</div>
              <div class="text-body-2 muted">{{ r.summary }}</div>
              <div class="text-caption mt-1">{{ r.report_type }} · {{ formatDate(r.created_at) }}</div>
            </div>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="team">
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-3">Team sharing</h2>
            <v-alert v-if="shareError" type="error" variant="tonal" class="mb-3">{{ shareError }}</v-alert>
            <v-row dense>
              <v-col cols="12" md="6"><v-text-field v-model="shareEmail" label="User email (must be registered)" /></v-col>
              <v-col cols="12" md="3">
                <v-select v-model="shareRole" :items="['manager','engineer','reviewer','viewer']" label="Role" />
              </v-col>
              <v-col cols="12" md="3" class="d-flex align-center">
                <v-btn color="primary" block @click="share">Share</v-btn>
              </v-col>
            </v-row>
            <v-table class="mt-4" density="comfortable">
              <thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead>
              <tbody>
                <tr v-for="m in members" :key="m.id">
                  <td>{{ m.full_name }}</td>
                  <td>{{ m.email }}</td>
                  <td>{{ m.role }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="chat">
          <div class="surface-panel pa-5">
            <h2 class="brand-font text-h6 mb-1">AI Engineering Chat</h2>
            <p class="muted text-body-2 mb-3">
              Ask questions or give commands — I can analyze files, generate BOQ, export Excel, process CAD, map bid templates, and estimate cost.
            </p>
            <div class="d-flex flex-wrap ga-2 mb-3">
              <v-chip v-for="q in suggestedQuestions" :key="q" size="small" variant="outlined" @click="sendChat(q)">{{ q }}</v-chip>
            </div>
            <v-alert v-if="chatError" type="error" variant="tonal" class="mb-3">{{ chatError }}</v-alert>
            <div ref="chatBox" class="chat-box mb-3">
              <div v-for="msg in chatMessages" :key="msg.id" class="chat-bubble mb-3" :class="msg.role">
                <div class="text-caption font-weight-medium mb-1">{{ msg.role === 'user' ? 'You' : 'AutoVAD' }}</div>
                <div class="text-body-2" style="white-space: pre-wrap">{{ msg.content }}</div>
                <div v-if="chatDownloads(msg).length" class="d-flex flex-wrap ga-2 mt-2">
                  <v-btn
                    v-for="(src, idx) in chatDownloads(msg)"
                    :key="idx"
                    size="small"
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-download"
                    @click="downloadFromChat(src)"
                  >
                    {{ src.label || 'Download' }}
                  </v-btn>
                </div>
              </div>
            </div>
            <v-textarea
              v-model="chatInput"
              rows="2"
              label="Ask a question or command"
              class="mb-3"
              @keydown.enter.exact.prevent="sendChat()"
            />
            <v-btn color="primary" :loading="chatLoading" @click="sendChat()">Send</v-btn>
          </div>
        </v-tabs-window-item>
      </v-tabs-window>
    </template>

    <v-dialog v-model="editDialog" max-width="560">
      <v-card class="pa-2">
        <v-card-title class="brand-font">Edit project</v-card-title>
        <v-card-text>
          <v-text-field v-model="editName" label="Name" class="mb-2" />
          <v-textarea v-model="editDescription" label="Description" rows="3" class="mb-2" />
          <v-select v-model="editStatus" :items="statuses" label="Status" />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="editDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="saveEdit">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog
      :model-value="analyzeModal"
      max-width="520"
      persistent
      scrim="rgba(3, 8, 6, 0.78)"
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
              @click="closeAnalyzeModal(); tab = 'boq'"
            >
              Go to BOQ
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
  from { transform: translateX(-120%); }
  to { transform: translateX(280%); }
}

@keyframes analyze-blink {
  50% { opacity: 0.45; }
}

.plan-tips {
  border: 1px solid var(--panel-border, #24322c);
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.02);
}

.plan-tips summary {
  cursor: pointer;
  font-size: 0.78rem;
  color: rgba(234, 240, 235, 0.55);
  font-family: var(--font-mono, ui-monospace, monospace);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  list-style: none;
}

.plan-tips summary::-webkit-details-marker {
  display: none;
}

.doc-tips {
  margin: 0;
  padding-left: 1.1rem;
  color: rgba(234, 240, 235, 0.78);
  font-size: 0.85rem;
  line-height: 1.55;
}

.doc-tips li + li {
  margin-top: 4px;
}

.doc-row,
.analysis-box {
  border: 1px solid var(--panel-border);
  border-radius: 0;
  background: #0d1814;
  color: var(--text);
}

.analysis-box {
  background: rgba(217, 255, 67, 0.04);
  border-color: rgba(217, 255, 67, 0.22);
}

.chat-box {
  max-height: 420px;
  overflow: auto;
  border: 1px solid var(--panel-border);
  border-radius: 0;
  padding: 16px;
  background: #0a1411;
}

.chat-bubble {
  max-width: 85%;
  padding: 12px 14px;
  border-radius: 0;
  color: var(--text);
}

.chat-bubble.user {
  margin-left: auto;
  background: #1d3028;
  border: 1px solid #2a3a33;
}

.chat-bubble.assistant {
  background: #101f1a;
  border: 1px solid rgba(217, 255, 67, 0.28);
}

.chat-bubble :deep(code),
.chat-bubble :deep(pre) {
  font-family: var(--font-mono);
  color: #c9d3cd;
  background: #0a1411;
}
</style>
