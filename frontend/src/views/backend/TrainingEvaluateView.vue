<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  evaluateTrainingCase,
  getTrainingCase,
  type TrainingCaseDetail,
  type TrainingRun,
} from '@/api/training'
import TrainingStageNav from '@/components/backend/TrainingStageNav.vue'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => Number(route.params.id))

const loading = ref(true)
const evaluating = ref(false)
const error = ref<string | null>(null)
const detail = ref<TrainingCaseDetail | null>(null)
const selectedRun = ref<TrainingRun | null>(null)
const tableTab = ref<'audit' | 'matched' | 'near' | 'misses' | 'qty' | 'extras'>('audit')
const showGuidance = ref(false)

const guidance = computed(() => selectedRun.value?.report?.training_guidance || '')
const metrics = computed(() => selectedRun.value?.report?.metrics || null)
const diffs = computed(() => selectedRun.value?.report?.diffs || null)

const visual = computed(() => {
  const d = diffs.value as Record<string, unknown> | null
  const m = metrics.value as Record<string, unknown> | null
  return (d?.visual as Record<string, unknown>) || (m?.visual as Record<string, unknown>) || null
})

/** Build matched table rows from visual payload OR legacy hits (older reports). */
function rowsFromHits(hits: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(hits)) return []
  return hits.map((h) => {
    const hit = h as Record<string, unknown>
    const exp = (hit.expected as Record<string, unknown>) || {}
    const act = (hit.actual as Record<string, unknown>) || {}
    const qtyOk = Boolean(hit.qty_ok)
    return {
      status: qtyOk ? 'matched' : 'qty_error',
      category: exp.category || act.category || '—',
      item_code: exp.item_code || act.item_code,
      original_description: exp.description || '—',
      original_unit: exp.unit || '—',
      original_qty: exp.quantity,
      autovad_description: act.description || hit.actual_description || '—',
      autovad_unit: act.unit || '—',
      autovad_qty: act.quantity,
      qty_ok: qtyOk,
      qty_delta: hit.qty_delta,
      similarity: null,
      match_method: hit.method,
      reason: qtyOk
        ? 'Matched description/unit; quantities within tolerance'
        : `Matched item but quantity differs — original ${exp.quantity} vs AutoVAD ${act.quantity} (Δ ${hit.qty_delta})`,
    }
  })
}

const matchedRows = computed(() => {
  const fromVisual = visual.value?.matched as Array<Record<string, unknown>> | undefined
  if (Array.isArray(fromVisual) && fromVisual.length) return fromVisual
  const fromDiffs = diffs.value?.matched as Array<Record<string, unknown>> | undefined
  if (Array.isArray(fromDiffs) && fromDiffs.length) return fromDiffs
  // Legacy reports: hits lived only under diffs/metrics
  const hits = (diffs.value?.hits as unknown) || (metrics.value?.hits as unknown) || []
  return rowsFromHits(hits)
})

const nearMissRows = computed(() => {
  const fromVisual = visual.value?.near_misses as Array<Record<string, unknown>> | undefined
  if (Array.isArray(fromVisual) && fromVisual.length) return fromVisual
  const fromDiffs = diffs.value?.near_misses as Array<Record<string, unknown>> | undefined
  return Array.isArray(fromDiffs) ? fromDiffs : []
})

const missRows = computed(() => {
  const fromVisual = visual.value?.misses as Array<Record<string, unknown>> | undefined
  if (Array.isArray(fromVisual) && fromVisual.length) return fromVisual
  const fromDiffs = diffs.value?.misses as Array<Record<string, unknown>> | undefined
  return Array.isArray(fromDiffs) ? fromDiffs : []
})

const qtyRows = computed(() => {
  const fromVisual = visual.value?.qty_errors as Array<Record<string, unknown>> | undefined
  if (Array.isArray(fromVisual) && fromVisual.length) return fromVisual
  const fromDiffs = diffs.value?.qty_errors as Array<Record<string, unknown>> | undefined
  if (Array.isArray(fromDiffs) && fromDiffs.length) return fromDiffs
  // Derive from matched hits where qty failed
  return matchedRows.value.filter((r) => r.status === 'qty_error')
})

const extraRows = computed(() => {
  const visualExtras = visual.value?.extras as Array<Record<string, unknown>> | undefined
  if (visualExtras?.length) return visualExtras
  return ((diffs.value?.extras as Array<Record<string, unknown>>) || []).map((e) => ({
    autovad_description: e.description,
    autovad_unit: e.unit,
    autovad_qty: e.quantity,
    category: e.category,
    reason: 'Extra AutoVAD line with no matching original EOQ item',
  }))
})

const lineAudit = computed(() => {
  const fromVisual = visual.value?.line_audit as Array<Record<string, unknown>> | undefined
  if (Array.isArray(fromVisual) && fromVisual.length) return fromVisual
  const fromDiffs = diffs.value?.line_audit as Array<Record<string, unknown>> | undefined
  if (Array.isArray(fromDiffs) && fromDiffs.length) return fromDiffs
  // Legacy: synthesize a basic audit from hits + misses
  const rows = [...matchedRows.value]
  for (const m of missRows.value) {
    rows.push({
      status: 'miss',
      category: m.category,
      item_code: m.item_code,
      original_description: m.description || m.original_description,
      original_unit: m.unit || m.original_unit,
      original_qty: m.quantity ?? m.original_qty,
      autovad_description: m.nearest_autovad || m.autovad_description,
      reason: m.reason || 'Missing from AutoVAD EOQ',
    })
  }
  return rows
})

const summary = computed(() => {
  const s = (visual.value?.summary as Record<string, unknown>) || {}
  const matchedCount = matchedRows.value.length
  return {
    expected: Number(s.expected ?? metrics.value?.expected_count ?? 0),
    autovad: Number(s.autovad ?? metrics.value?.actual_count ?? 0),
    matched: Number(s.matched ?? matchedCount),
    qty_errors: Number(s.qty_errors ?? qtyRows.value.length),
    near_misses: Number(s.near_misses ?? nearMissRows.value.length),
    misses: Number(s.misses ?? missRows.value.length),
    extras: Number(s.extras ?? extraRows.value.length),
    recall: Number(s.recall ?? selectedRun.value?.report?.recall ?? 0),
    precision: Number(s.precision_proxy ?? selectedRun.value?.report?.precision_proxy ?? 0),
  }
})

const byCategory = computed(() => {
  const rows = (visual.value?.by_category as Array<Record<string, unknown>>) || []
  if (rows.length) return rows
  const missesByCat = (metrics.value?.misses_by_category as Record<string, number>) || {}
  return Object.entries(missesByCat).map(([category, missed]) => ({
    category,
    expected: missed,
    matched: 0,
    qty_error: 0,
    missed,
    near_miss: 0,
    extras: 0,
  }))
})

const maxCatMiss = computed(() =>
  Math.max(1, ...byCategory.value.map((c) => Number(c.missed || 0))),
)
const maxCatExpected = computed(() =>
  Math.max(1, ...byCategory.value.map((c) => Number(c.expected || 0))),
)

const outcomeBars = computed(() => {
  const s = summary.value
  const total = Math.max(s.expected, 1)
  return [
    { key: 'Matched', value: s.matched, color: '#85ffd0', pct: (s.matched / total) * 100 },
    { key: 'Qty error', value: s.qty_errors, color: '#ffc36a', pct: (s.qty_errors / total) * 100 },
    { key: 'Near miss', value: s.near_misses, color: '#9ecbff', pct: (s.near_misses / total) * 100 },
    { key: 'Missed', value: s.misses, color: '#ff8b6b', pct: (s.misses / total) * 100 },
  ]
})

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

function statusColor(status: unknown) {
  const s = String(status || '')
  if (s === 'matched') return 'success'
  if (s === 'qty_error') return 'warning'
  if (s === 'near_miss' || s === 'miss_near') return 'info'
  if (s === 'miss') return 'error'
  if (s === 'extra') return 'secondary'
  return 'default'
}

function statusLabel(status: unknown) {
  const s = String(status || '')
  if (s === 'matched') return 'Matched'
  if (s === 'qty_error') return 'Qty error'
  if (s === 'near_miss' || s === 'miss_near') return 'Near miss'
  if (s === 'miss') return 'Missed'
  if (s === 'extra') return 'Extra'
  return s || '—'
}

async function load() {
  loading.value = true
  error.value = null
  try {
    detail.value = await getTrainingCase(caseId.value)
    if (!detail.value.can_evaluate && !detail.value.has_expected) {
      await router.replace(
        detail.value.has_autovad_eoq
          ? `/backend/cases/${caseId.value}/original`
          : `/backend/cases/${caseId.value}/analyze`,
      )
      return
    }
    selectedRun.value = detail.value.runs?.[0] || null
  } catch {
    error.value = 'Could not load training case (admin only).'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function runEvaluate() {
  if (!detail.value?.can_evaluate) {
    error.value = 'Need AutoVAD EOQ (Stage 1) and original EOQ (Stage 2) before evaluation'
    return
  }
  evaluating.value = true
  error.value = null
  try {
    const run = await evaluateTrainingCase(caseId.value)
    selectedRun.value = run
    detail.value = await getTrainingCase(caseId.value)
    if (run.status === 'failed') {
      error.value = run.error_message || 'Evaluation failed'
    } else {
      tableTab.value = 'audit'
    }
  } catch (err) {
    error.value = errDetail(err, 'Evaluation failed')
    await load()
  } finally {
    evaluating.value = false
  }
}
</script>

<template>
  <div class="page-shell backend-lab">
    <div class="d-flex flex-wrap justify-space-between ga-2 mb-2">
      <div>
        <div class="page-kicker">Stage 3</div>
        <h1 class="brand-font text-h4 mb-1">Evaluate &amp; report</h1>
        <p class="muted mb-0">
          {{ detail?.name || '…' }} — engineer compare: matches, near-misses, reasons, category analytics
        </p>
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
        <div class="d-flex flex-wrap justify-space-between align-center ga-3">
          <div>
            <h2 class="brand-font text-h6 mb-1">Run evaluation</h2>
            <p class="text-caption muted mb-0">
              AutoVAD {{ detail.autovad_item_count || 0 }} · original {{ detail.expected_item_count || 0 }}
            </p>
          </div>
          <v-btn
            color="primary"
            size="large"
            :loading="evaluating"
            :disabled="!detail.can_evaluate || evaluating"
            @click="runEvaluate"
          >
            {{ evaluating ? 'Evaluating…' : 'Run evaluation & generate report' }}
          </v-btn>
        </div>
      </div>

      <div v-if="!selectedRun?.report" class="surface-panel pa-5">
        <div class="muted text-center py-10">Run evaluation to generate the visual training report.</div>
      </div>

      <template v-else>
        <div class="d-flex ga-2 flex-wrap mb-3">
          <v-chip
            v-for="r in detail.runs"
            :key="r.id"
            size="small"
            :color="selectedRun?.id === r.id ? 'primary' : 'default'"
            variant="tonal"
            @click="selectedRun = r"
          >
            #{{ r.id }} {{ r.status }}
          </v-chip>
        </div>

        <!-- Score strip -->
        <v-row class="mb-2">
          <v-col v-for="card in [
            ['Recall', `${(summary.recall * 100).toFixed(1)}%`],
            ['Precision', `${(summary.precision * 100).toFixed(1)}%`],
            ['Matched', summary.matched],
            ['Near miss', summary.near_misses],
            ['Missed', summary.misses],
            ['Extras', summary.extras],
            ['Qty errors', summary.qty_errors],
          ]" :key="card[0]" cols="6" sm="4" md="3" lg>
            <div class="mini-stat">
              <div class="muted text-caption">{{ card[0] }}</div>
              <b>{{ card[1] }}</b>
            </div>
          </v-col>
        </v-row>

        <!-- Analytics -->
        <v-row class="mb-4">
          <v-col cols="12" md="5">
            <div class="surface-panel pa-5 h-100">
              <h2 class="brand-font text-h6 mb-1">Outcome mix</h2>
              <p class="text-caption muted mb-4">Share of original EOQ lines by result</p>
              <div v-for="bar in outcomeBars" :key="bar.key" class="outcome-row mb-3">
                <div class="d-flex justify-space-between text-caption mb-1">
                  <span>{{ bar.key }}</span>
                  <span>{{ bar.value }}</span>
                </div>
                <div class="bar-track">
                  <i :style="{ width: `${Math.min(100, bar.pct)}%`, background: bar.color }" />
                </div>
              </div>
              <div class="donut-wrap mt-4" aria-hidden="true">
                <svg viewBox="0 0 36 36" class="donut">
                  <circle class="donut-bg" cx="18" cy="18" r="15.9" />
                  <circle
                    class="donut-seg"
                    cx="18"
                    cy="18"
                    r="15.9"
                    :stroke-dasharray="`${Math.min(100, summary.recall * 100)} ${100 - Math.min(100, summary.recall * 100)}`"
                    stroke="#85ffd0"
                  />
                </svg>
                <div class="donut-label">
                  <div class="text-caption muted">Recall</div>
                  <b>{{ (summary.recall * 100).toFixed(0) }}%</b>
                </div>
              </div>
            </div>
          </v-col>
          <v-col cols="12" md="7">
            <div class="surface-panel pa-5 h-100">
              <h2 class="brand-font text-h6 mb-1">Misses by category</h2>
              <p class="text-caption muted mb-4">Where schedule coverage is weakest — fix these first</p>
              <div v-if="!byCategory.length" class="muted text-center py-8">No category breakdown.</div>
              <div v-for="cat in byCategory.slice(0, 12)" :key="String(cat.category)" class="cat-row mb-3">
                <div class="d-flex justify-space-between ga-2 text-caption mb-1">
                  <span class="cat-name">{{ cat.category }}</span>
                  <span class="muted">
                    miss {{ cat.missed }} / exp {{ cat.expected }}
                    <span v-if="Number(cat.near_miss)"> · near {{ cat.near_miss }}</span>
                  </span>
                </div>
                <div class="bar-track tall">
                  <i
                    class="exp"
                    :style="{ width: `${(Number(cat.expected) / maxCatExpected) * 100}%` }"
                  />
                  <em
                    class="miss"
                    :style="{ width: `${(Number(cat.missed) / maxCatMiss) * 100}%` }"
                  />
                </div>
              </div>
            </div>
          </v-col>
        </v-row>

        <!-- Tables -->
        <div class="surface-panel pa-5 mb-4">
          <div class="d-flex flex-wrap justify-space-between align-center ga-2 mb-3">
            <h2 class="brand-font text-h6 mb-0">Item comparison tables</h2>
            <v-btn-toggle v-model="tableTab" mandatory density="compact" variant="outlined" divided>
              <v-btn value="audit" size="small">Line audit</v-btn>
              <v-btn value="matched" size="small">Matched</v-btn>
              <v-btn value="near" size="small">Near miss</v-btn>
              <v-btn value="misses" size="small">Misses</v-btn>
              <v-btn value="qty" size="small">Qty errors</v-btn>
              <v-btn value="extras" size="small">Extras</v-btn>
            </v-btn-toggle>
          </div>

          <!-- Line audit -->
          <div v-show="tableTab === 'audit'">
            <p class="text-caption muted mb-3">
              Every original bid/EOQ line with AutoVAD counterpart and why it is or isn’t correct.
            </p>
            <div v-if="!lineAudit.length" class="muted text-center py-8">
              Re-run evaluation to build the line-by-line audit (older runs may lack this table).
            </div>
            <div v-else class="table-scroll">
              <v-table density="compact" class="report-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Category</th>
                    <th>Original item</th>
                    <th>Unit</th>
                    <th>Orig qty</th>
                    <th>AutoVAD item</th>
                    <th>AV qty</th>
                    <th>Sim%</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in lineAudit" :key="idx">
                    <td>
                      <v-chip size="x-small" :color="statusColor(row.status)" variant="tonal">
                        {{ statusLabel(row.status) }}
                      </v-chip>
                    </td>
                    <td class="text-caption">{{ row.category || '—' }}</td>
                    <td>
                      <div class="font-weight-medium">{{ row.original_description }}</div>
                      <div v-if="row.item_code" class="text-caption muted">{{ row.item_code }}</div>
                    </td>
                    <td>{{ row.original_unit || '—' }}</td>
                    <td class="text-right">{{ formatQty(row.original_qty) }}</td>
                    <td class="text-caption">{{ row.autovad_description || '—' }}</td>
                    <td class="text-right">{{ formatQty(row.autovad_qty) }}</td>
                    <td>{{ row.similarity != null ? row.similarity : '—' }}</td>
                    <td class="reason-cell">{{ row.reason || '—' }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>

          <!-- Matched -->
          <div v-show="tableTab === 'matched'">
            <p class="text-caption muted mb-3">Original EOQ lines that AutoVAD matched (qty OK or flagged).</p>
            <div v-if="!matchedRows.length" class="muted text-center py-8">
              No matched rows yet. Click <strong>Run evaluation</strong> again to refresh the report tables.
            </div>
            <div v-else class="table-scroll">
              <v-table density="compact" class="report-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Original</th>
                    <th>AutoVAD</th>
                    <th>Unit</th>
                    <th>Orig qty</th>
                    <th>AV qty</th>
                    <th>Δ</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in matchedRows" :key="idx">
                    <td>
                      <v-chip size="x-small" :color="statusColor(row.status)" variant="tonal">
                        {{ statusLabel(row.status) }}
                      </v-chip>
                    </td>
                    <td>{{ row.original_description }}</td>
                    <td class="text-caption">{{ row.autovad_description }}</td>
                    <td>{{ row.original_unit }}</td>
                    <td class="text-right">{{ formatQty(row.original_qty) }}</td>
                    <td class="text-right">{{ formatQty(row.autovad_qty) }}</td>
                    <td class="text-right">{{ formatQty(row.qty_delta) }}</td>
                    <td class="reason-cell">{{ row.reason }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>

          <!-- Near miss -->
          <div v-show="tableTab === 'near'">
            <p class="text-caption muted mb-3">
              Looks similar (wording/size/unit) but not accepted as a match — review naming & units.
            </p>
            <div v-if="!nearMissRows.length" class="muted text-center py-8">No near-miss rows.</div>
            <div v-else class="table-scroll">
              <v-table density="compact" class="report-table">
                <thead>
                  <tr>
                    <th>Original</th>
                    <th>Closest AutoVAD</th>
                    <th>Units</th>
                    <th>Sim%</th>
                    <th>Why not matched</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in nearMissRows" :key="idx">
                    <td>
                      <div class="font-weight-medium">{{ row.original_description }}</div>
                      <div class="text-caption muted">{{ row.category }} · qty {{ formatQty(row.original_qty) }}</div>
                    </td>
                    <td>
                      <div>{{ row.autovad_description }}</div>
                      <div class="text-caption muted">qty {{ formatQty(row.autovad_qty) }}</div>
                    </td>
                    <td class="text-caption">{{ row.original_unit }} vs {{ row.autovad_unit }}</td>
                    <td>{{ row.similarity }}</td>
                    <td class="reason-cell">{{ row.reason }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>

          <!-- Misses -->
          <div v-show="tableTab === 'misses'">
            <p class="text-caption muted mb-3">Original schedule items AutoVAD failed to find.</p>
            <div v-if="!missRows.length" class="muted text-center py-8">No misses.</div>
            <div v-else class="table-scroll">
              <v-table density="compact" class="report-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Original item</th>
                    <th>Unit</th>
                    <th>Qty</th>
                    <th>Nearest AutoVAD</th>
                    <th>Why incorrect / missing</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in missRows" :key="idx">
                    <td class="text-caption">{{ row.category || '—' }}</td>
                    <td class="font-weight-medium">{{ row.description || row.original_description }}</td>
                    <td>{{ row.unit || row.original_unit }}</td>
                    <td class="text-right">{{ formatQty(row.quantity ?? row.original_qty) }}</td>
                    <td class="text-caption">{{ row.nearest_autovad || row.autovad_description || '—' }}</td>
                    <td class="reason-cell">{{ row.reason || 'Missing from AutoVAD EOQ' }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>

          <!-- Qty -->
          <div v-show="tableTab === 'qty'">
            <p class="text-caption muted mb-3">Same pay item found, but quantity does not match the schedule.</p>
            <div v-if="!qtyRows.length" class="muted text-center py-8">No quantity errors.</div>
            <div v-else class="table-scroll">
              <v-table density="compact" class="report-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Category</th>
                    <th>Unit</th>
                    <th>Original</th>
                    <th>AutoVAD</th>
                    <th>Δ</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in qtyRows" :key="idx">
                    <td>
                      <div class="font-weight-medium">{{ row.description || row.original_description }}</div>
                      <div v-if="row.autovad_description" class="text-caption muted">{{ row.autovad_description }}</div>
                    </td>
                    <td class="text-caption">{{ row.category }}</td>
                    <td>{{ row.unit }}</td>
                    <td class="text-right">{{ formatQty(row.expected_qty ?? row.original_qty) }}</td>
                    <td class="text-right">{{ formatQty(row.actual_qty ?? row.autovad_qty) }}</td>
                    <td class="text-right">{{ formatQty(row.delta ?? row.qty_delta) }}</td>
                    <td class="reason-cell">{{ row.reason || 'Quantity outside tolerance vs schedule' }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>

          <!-- Extras -->
          <div v-show="tableTab === 'extras'">
            <p class="text-caption muted mb-3">AutoVAD lines not on the original EOQ (false positives / invents).</p>
            <div v-if="!extraRows.length" class="muted text-center py-8">No extras.</div>
            <div v-else class="table-scroll">
              <v-table density="compact" class="report-table">
                <thead>
                  <tr>
                    <th>AutoVAD item</th>
                    <th>Category</th>
                    <th>Unit</th>
                    <th>Qty</th>
                    <th>Why not correct</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in extraRows" :key="idx">
                    <td class="font-weight-medium">{{ row.autovad_description || row.description }}</td>
                    <td class="text-caption">{{ row.category || '—' }}</td>
                    <td>{{ row.autovad_unit || row.unit }}</td>
                    <td class="text-right">{{ formatQty(row.autovad_qty ?? row.quantity) }}</td>
                    <td class="reason-cell">{{ row.reason || 'Not on original EOQ' }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>
        </div>

        <div class="surface-panel pa-5">
          <div class="d-flex justify-space-between align-center mb-2">
            <h2 class="brand-font text-h6 mb-0">Training guidance</h2>
            <v-btn size="small" variant="tonal" @click="showGuidance = !showGuidance">
              {{ showGuidance ? 'Hide' : 'Show' }}
            </v-btn>
          </div>
          <pre v-if="showGuidance" class="guidance-box">{{ guidance || 'No guidance.' }}</pre>
          <p v-else class="text-caption muted mb-0">Collapsed — open to read the full coach write-up.</p>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.mini-stat {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.2);
  min-height: 72px;
}
.mini-stat b {
  font-size: 1.15rem;
}
.bar-track {
  position: relative;
  height: 8px;
  background: #1a2b24;
  overflow: hidden;
  border-radius: 2px;
}
.bar-track.tall {
  height: 12px;
}
.bar-track i,
.bar-track em {
  display: block;
  height: 100%;
  transition: width 0.35s ease;
}
.bar-track em.miss {
  position: absolute;
  left: 0;
  top: 0;
  background: linear-gradient(90deg, #ff8b6b, #ffc36a);
  opacity: 0.95;
}
.bar-track i.exp {
  background: rgba(217, 255, 67, 0.22);
}
.cat-name {
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.donut-wrap {
  position: relative;
  width: 120px;
  height: 120px;
  margin: 0 auto;
}
.donut {
  width: 120px;
  height: 120px;
  transform: rotate(-90deg);
}
.donut-bg {
  fill: none;
  stroke: #1a2b24;
  stroke-width: 3.2;
}
.donut-seg {
  fill: none;
  stroke-width: 3.2;
  stroke-linecap: round;
}
.donut-label {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  text-align: center;
}
.donut-label b {
  font-size: 1.35rem;
  color: #d9ff43;
}
.table-scroll {
  max-height: 520px;
  overflow: auto;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
}
.report-table :deep(th) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #0c1612;
  white-space: nowrap;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(234, 240, 235, 0.55);
}
.reason-cell {
  max-width: 280px;
  font-size: 0.78rem;
  color: rgba(234, 240, 235, 0.78);
  line-height: 1.35;
}
.guidance-box {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.82rem;
  line-height: 1.45;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid rgba(217, 255, 67, 0.18);
  background: rgba(0, 0, 0, 0.28);
  max-height: 420px;
  overflow: auto;
  margin: 0;
}
.h-100 {
  height: 100%;
}
</style>
