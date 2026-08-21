<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchAnalytics } from '@/api/dashboard'
import { useProjectsStore } from '@/stores/projects'
import { formatDate, formatQty } from '@/utils/format'
import type { AnalyticsSnapshot, ProjectStatus } from '@/types'

type RangeKey = '7d' | '30d' | 'all'
type MaterialsView = 'chart' | 'table'
type SortKey = 'quantity' | 'name' | 'share'

const router = useRouter()
const projectsStore = useProjectsStore()

const loading = ref(true)
const data = ref<AnalyticsSnapshot | null>(null)
const error = ref<string | null>(null)

const projectFilter = ref<number | null>(null)
const statusFilter = ref<ProjectStatus | 'all'>('all')
const rangeFilter = ref<RangeKey>('all')
const materialsView = ref<MaterialsView>('chart')
const materialsSort = ref<SortKey>('quantity')
const compareEnabled = ref(false)
const compareA = ref<number | null>(null)
const compareB = ref<number | null>(null)
const hoveredMaterial = ref<string | null>(null)
const hoveredCost = ref<string | null>(null)
const hoveredKpi = ref<string | null>(null)

const displayCost = ref(0)
const displayCut = ref(0)
const displayFill = ref(0)
const displayEoqs = ref(0)

const rangeOptions = [
  { title: 'Last 7 days', value: '7d' as const },
  { title: 'Last 30 days', value: '30d' as const },
  { title: 'All time', value: 'all' as const },
]

const statusOptions: Array<{ title: string; value: ProjectStatus | 'all' }> = [
  { title: 'All statuses', value: 'all' },
  { title: 'Draft', value: 'draft' },
  { title: 'Active', value: 'active' },
  { title: 'In review', value: 'in_review' },
  { title: 'Approved', value: 'approved' },
  { title: 'Archived', value: 'archived' },
]

const projectOptions = computed(() => [
  { title: 'All projects', value: null as number | null },
  ...projectsStore.projects.map((p) => ({ title: p.name, value: p.id as number | null })),
])

const compareOptions = computed(() =>
  projectsStore.projects.map((p) => ({ title: p.name, value: p.id })),
)

const meta = computed(() => data.value?.meta)
const earthwork = computed(() => data.value?.earthwork)
const costs = computed(() => data.value?.costs)

const sortedMaterials = computed(() => {
  const list = [...(data.value?.materials || [])]
  if (materialsSort.value === 'name') {
    return list.sort((a, b) => a.name.localeCompare(b.name))
  }
  if (materialsSort.value === 'share') {
    return list.sort((a, b) => (b.share || 0) - (a.share || 0))
  }
  return list.sort((a, b) => b.quantity - a.quantity)
})

const maxMaterialQty = computed(() => sortedMaterials.value[0]?.quantity || 1)
const maxCost = computed(() => costs.value?.by_project[0]?.amount || 1)
const maxCategory = computed(() => data.value?.categories[0]?.quantity || 1)

const pavementRows = computed(() => {
  const pavement = data.value?.pavement || {}
  return Object.entries(pavement)
    .map(([name, qty]) => ({ name, qty }))
    .filter((r) => r.qty > 0)
    .sort((a, b) => b.qty - a.qty)
})

const cutFillMax = computed(() => {
  const cut = earthwork.value?.cut || 0
  const fill = earthwork.value?.fill || 0
  return Math.max(cut, fill, 1)
})

const cutPct = computed(() => Math.round(((earthwork.value?.cut || 0) / cutFillMax.value) * 100))
const fillPct = computed(() => Math.round(((earthwork.value?.fill || 0) / cutFillMax.value) * 100))

const balanceSide = computed(() => {
  const label = earthwork.value?.balance_label || 'balanced'
  if (label === 'cut surplus') return 'cut'
  if (label === 'fill surplus') return 'fill'
  return 'even'
})

const hasData = computed(() => Boolean(meta.value?.has_eoqs || meta.value?.has_estimates))
const freshnessLabel = computed(() => {
  if (!meta.value) return ''
  const parts = [
    `Based on ${meta.value.eoq_count} ${meta.value.eoq_count === 1 ? 'Estimate Of Quantities' : 'Estimates Of Quantities'}`,
    `${meta.value.item_count} line item${meta.value.item_count === 1 ? '' : 's'}`,
    `${meta.value.estimate_count} estimate${meta.value.estimate_count === 1 ? '' : 's'}`,
  ]
  const updated = meta.value.last_updated ? ` · Updated ${formatDate(meta.value.last_updated)}` : ''
  return parts.join(' · ') + updated
})

const costDonutStops = computed(() => {
  const rows = costs.value?.by_project || []
  const total = rows.reduce((s, r) => s + r.amount, 0) || 1
  let cursor = 0
  const colors = ['#d9ff43', '#85ffd0', '#ffc36a', '#8eb6ff', '#ff8b6b', '#c4b5fd']
  return rows.slice(0, 6).map((row, i) => {
    const start = cursor
    const share = (row.amount / total) * 100
    cursor += share
    return {
      ...row,
      color: colors[i % colors.length],
      start,
      end: cursor,
    }
  })
})

const donutGradient = computed(() => {
  const stops = costDonutStops.value
  if (!stops.length) return 'conic-gradient(#28362f 0 100%)'
  const parts = stops.map((s) => `${s.color} ${s.start}% ${s.end}%`)
  if (stops[stops.length - 1].end < 100) {
    parts.push(`#28362f ${stops[stops.length - 1].end}% 100%`)
  }
  return `conic-gradient(${parts.join(', ')})`
})

function barWidth(value: number, max: number) {
  if (!max) return '0%'
  return `${Math.max(4, Math.round((value / max) * 100))}%`
}

function animateNumbers(snapshot: AnalyticsSnapshot) {
  const duration = 700
  const start = performance.now()
  const from = {
    cost: displayCost.value,
    cut: displayCut.value,
    fill: displayFill.value,
    eoqs: displayEoqs.value,
  }
  const to = {
    cost: snapshot.costs.total_estimated,
    cut: snapshot.earthwork.cut,
    fill: snapshot.earthwork.fill,
    eoqs: snapshot.meta.eoq_count,
  }

  function frame(now: number) {
    const t = Math.min(1, (now - start) / duration)
    const eased = 1 - (1 - t) ** 3
    displayCost.value = from.cost + (to.cost - from.cost) * eased
    displayCut.value = from.cut + (to.cut - from.cut) * eased
    displayFill.value = from.fill + (to.fill - from.fill) * eased
    displayEoqs.value = Math.round(from.eoqs + (to.eoqs - from.eoqs) * eased)
    if (t < 1) requestAnimationFrame(frame)
  }
  requestAnimationFrame(frame)
}

async function loadAnalytics() {
  loading.value = true
  error.value = null
  try {
    const params: Parameters<typeof fetchAnalytics>[0] = {
      range: rangeFilter.value,
    }
    if (projectFilter.value != null) params.project_id = projectFilter.value
    if (statusFilter.value !== 'all' && projectFilter.value == null) {
      params.status = statusFilter.value
    }
    if (compareEnabled.value && compareA.value && compareB.value && compareA.value !== compareB.value) {
      params.compare_a = compareA.value
      params.compare_b = compareB.value
    }
    const snapshot = await fetchAnalytics(params)
    data.value = snapshot
    animateNumbers(snapshot)
  } catch {
    error.value = 'Could not load analytics'
    data.value = null
  } finally {
    loading.value = false
  }
}

function clearFilters() {
  projectFilter.value = null
  statusFilter.value = 'all'
  rangeFilter.value = 'all'
  compareEnabled.value = false
  compareA.value = null
  compareB.value = null
}

function openProjects() {
  router.push('/projects')
}

function openProject(id?: number | null) {
  if (id) router.push(`/projects/${id}`)
  else openProjects()
}

function openFirstProjectOrLibrary() {
  if (projectFilter.value) {
    openProject(projectFilter.value)
    return
  }
  const first = projectsStore.projects[0]
  if (first) openProject(first.id)
  else openProjects()
}

function money(n: number) {
  return `$${Math.round(n).toLocaleString()}`
}

function signed(n: number) {
  const abs = Math.abs(n)
  const prefix = n > 0 ? '+' : n < 0 ? '−' : ''
  return `${prefix}${abs.toLocaleString()}`
}

function exportCsv() {
  if (!data.value) return
  const lines: string[] = []
  lines.push('AutoVAD Analytics Snapshot')
  lines.push(`Generated,${new Date().toISOString()}`)
  lines.push(`Range,${rangeFilter.value}`)
  lines.push(`Projects in scope,${meta.value?.project_count ?? 0}`)
  lines.push(`Estimates Of Quantities,${meta.value?.eoq_count ?? 0}`)
  lines.push(`Estimates,${meta.value?.estimate_count ?? 0}`)
  lines.push(`Last updated,${meta.value?.last_updated || ''}`)
  lines.push('')
  lines.push('KPI,Value')
  lines.push(`Total estimated cost,${data.value.costs.total_estimated}`)
  lines.push(`Earthwork cut m3,${data.value.earthwork.cut}`)
  lines.push(`Earthwork fill m3,${data.value.earthwork.fill}`)
  lines.push(`Balance m3,${data.value.earthwork.balance}`)
  lines.push(`Balance label,${data.value.earthwork.balance_label}`)
  lines.push('')
  lines.push('Material,Quantity,Unit,Share %')
  for (const m of sortedMaterials.value) {
    lines.push(`"${m.name.replace(/"/g, '""')}",${m.quantity},${m.unit || ''},${m.share ?? ''}`)
  }
  lines.push('')
  lines.push('Category,Quantity,Share %')
  for (const c of data.value.categories) {
    lines.push(`"${c.name.replace(/"/g, '""')}",${c.quantity},${c.share ?? ''}`)
  }
  lines.push('')
  lines.push('Project,Cost')
  for (const row of data.value.costs.by_project) {
    lines.push(`"${row.name.replace(/"/g, '""')}",${row.amount}`)
  }
  if (data.value.compare) {
    lines.push('')
    lines.push(`Compare,${data.value.compare.a.name} vs ${data.value.compare.b.name}`)
    lines.push(`Cost delta,${data.value.compare.delta.cost}`)
    lines.push(`Cut delta,${data.value.compare.delta.cut}`)
    lines.push(`Fill delta,${data.value.compare.delta.fill}`)
    lines.push('Material,A,B,Delta')
    for (const m of data.value.compare.delta.materials) {
      lines.push(`"${m.name.replace(/"/g, '""')}",${m.a},${m.b},${m.delta}`)
    }
  }

  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `autovad-analytics-${rangeFilter.value}-${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function exportPdf() {
  if (!data.value) return
  const d = data.value
  const materialsRows = sortedMaterials.value
    .map(
      (m) =>
        `<tr><td>${escapeHtml(m.name)}</td><td>${m.quantity}</td><td>${escapeHtml(m.unit || '')}</td><td>${m.share ?? ''}%</td></tr>`,
    )
    .join('')
  const costRows = d.costs.by_project
    .map((r) => `<tr><td>${escapeHtml(r.name)}</td><td>$${r.amount.toLocaleString()}</td></tr>`)
    .join('')
  const compareBlock = d.compare
    ? `<h2>Compare: ${escapeHtml(d.compare.a.name)} vs ${escapeHtml(d.compare.b.name)}</h2>
       <p>Cost Δ ${signed(d.compare.delta.cost)} · Cut Δ ${signed(d.compare.delta.cut)} · Fill Δ ${signed(d.compare.delta.fill)}</p>`
    : ''

  const html = `<!DOCTYPE html><html><head><title>AutoVAD Analytics</title>
    <style>
      body{font-family:Segoe UI,Arial,sans-serif;color:#111;padding:32px;max-width:900px;margin:0 auto}
      h1{font-size:22px;margin:0 0 4px} .muted{color:#555;font-size:12px;margin-bottom:20px}
      .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0 24px}
      .kpi{border:1px solid #ddd;padding:12px;border-radius:8px}
      .kpi b{display:block;font-size:18px;margin-top:4px}
      table{width:100%;border-collapse:collapse;margin:12px 0 24px;font-size:12px}
      th,td{border-bottom:1px solid #e5e5e5;padding:8px;text-align:left}
      th{text-transform:uppercase;letter-spacing:.04em;font-size:10px;color:#666}
      @media print{body{padding:12px}}
    </style></head><body>
    <h1>AutoVAD Analytics Snapshot</h1>
    <div class="muted">${escapeHtml(freshnessLabel.value)} · Range ${rangeFilter.value} · Printed ${new Date().toLocaleString()}</div>
    <div class="kpis">
      <div class="kpi"><span>Total cost</span><b>${money(d.costs.total_estimated)}</b></div>
      <div class="kpi"><span>Cut</span><b>${formatQty(d.earthwork.cut)} m³</b></div>
      <div class="kpi"><span>Fill</span><b>${formatQty(d.earthwork.fill)} m³</b></div>
      <div class="kpi"><span>Estimates Of Quantities</span><b>${d.meta.eoq_count}</b></div>
    </div>
    <h2>Materials</h2>
    <table><thead><tr><th>Material</th><th>Qty</th><th>Unit</th><th>Share</th></tr></thead><tbody>${materialsRows || '<tr><td colspan="4">No materials</td></tr>'}</tbody></table>
    <h2>Cost by project</h2>
    <table><thead><tr><th>Project</th><th>Amount</th></tr></thead><tbody>${costRows || '<tr><td colspan="2">No estimates</td></tr>'}</tbody></table>
    ${compareBlock}
    <script>window.onload=()=>{window.print()}<\/script>
    </body></html>`

  const win = window.open('', '_blank', 'noopener,noreferrer,width=900,height=700')
  if (!win) return
  win.document.write(html)
  win.document.close()
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

watch([projectFilter, statusFilter, rangeFilter, compareEnabled, compareA, compareB], () => {
  if (compareEnabled.value && (!compareA.value || !compareB.value || compareA.value === compareB.value)) {
    // Still refresh base snapshot while compare picks are incomplete
  }
  void loadAnalytics()
})

onMounted(async () => {
  await projectsStore.fetchProjects().catch(() => undefined)
  await loadAnalytics()
})
</script>

<template>
  <div class="page-shell analytics">
    <div class="d-flex flex-wrap align-start justify-space-between mb-5 ga-3">
      <div>
        <div class="page-kicker">Insights</div>
        <h1 class="brand-font text-h4 mb-1">Analytics</h1>
        <p class="muted mb-1">Quantities, earthwork balance, pavement, and cost — scoped to your USA takeoffs.</p>
        <p v-if="meta && !loading" class="freshness mb-0">{{ freshnessLabel }}</p>
      </div>
      <div class="d-flex flex-wrap ga-2">
        <v-btn variant="tonal" color="secondary" prepend-icon="mdi-download" :disabled="!data" @click="exportCsv">
          Export CSV
        </v-btn>
        <v-btn variant="tonal" color="secondary" prepend-icon="mdi-printer" :disabled="!data" @click="exportPdf">
          Export PDF
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-folder-open-outline" @click="openProjects">Projects</v-btn>
      </div>
    </div>

    <div class="surface-panel pa-4 mb-5">
      <v-row dense align="center">
        <v-col cols="12" md="3">
          <v-select
            v-model="projectFilter"
            :items="projectOptions"
            item-title="title"
            item-value="value"
            label="Project"
            hide-details
            density="comfortable"
            clearable
          />
        </v-col>
        <v-col cols="12" sm="6" md="2">
          <v-select
            v-model="statusFilter"
            :items="statusOptions"
            label="Status"
            hide-details
            density="comfortable"
            :disabled="projectFilter != null"
          />
        </v-col>
        <v-col cols="12" sm="6" md="2">
          <v-select
            v-model="rangeFilter"
            :items="rangeOptions"
            label="Time range"
            hide-details
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="3" class="d-flex align-center">
          <v-switch
            v-model="compareEnabled"
            label="Compare projects"
            color="secondary"
            hide-details
            density="compact"
            class="mt-0"
          />
        </v-col>
        <v-col cols="12" md="2" class="d-flex justify-md-end">
          <v-btn variant="text" @click="clearFilters">Clear</v-btn>
        </v-col>
      </v-row>

      <v-row v-if="compareEnabled" dense class="mt-2">
        <v-col cols="12" md="5">
          <v-select
            v-model="compareA"
            :items="compareOptions"
            item-title="title"
            item-value="value"
            label="Project A"
            hide-details
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="5">
          <v-select
            v-model="compareB"
            :items="compareOptions"
            item-title="title"
            item-value="value"
            label="Project B"
            hide-details
            density="comfortable"
          />
        </v-col>
        <v-col cols="12" md="2" class="d-flex align-center">
          <span class="text-caption muted">A vs B deltas below</span>
        </v-col>
      </v-row>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <div v-if="loading" class="text-center py-16">
      <v-progress-circular indeterminate color="primary" size="40" />
      <div class="muted mt-3 text-caption">Building analytics snapshot…</div>
    </div>

    <template v-else-if="data">
      <section class="kpi-grid mb-5">
        <button
          type="button"
          class="kpi-card acid"
          :class="{ hot: hoveredKpi === 'cost' }"
          @mouseenter="hoveredKpi = 'cost'"
          @mouseleave="hoveredKpi = null"
          @click="openProjects"
        >
          <div class="kpi-head">
            <span>Total estimated cost</span>
            <v-icon size="18">mdi-currency-usd</v-icon>
          </div>
          <div class="stat-value">{{ money(displayCost) }}</div>
          <div class="kpi-hint">Open project library →</div>
        </button>

        <button
          type="button"
          class="kpi-card mint"
          :class="{ hot: hoveredKpi === 'cut' }"
          @mouseenter="hoveredKpi = 'cut'"
          @mouseleave="hoveredKpi = null"
          @click="openFirstProjectOrLibrary"
        >
          <div class="kpi-head">
            <span>Earthwork cut</span>
            <v-icon size="18">mdi-arrow-collapse-down</v-icon>
          </div>
          <div class="stat-value">{{ formatQty(displayCut) }} <small>m³</small></div>
          <div class="kpi-hint">Inspect takeoff →</div>
        </button>

        <button
          type="button"
          class="kpi-card mint"
          :class="{ hot: hoveredKpi === 'fill' }"
          @mouseenter="hoveredKpi = 'fill'"
          @mouseleave="hoveredKpi = null"
          @click="openFirstProjectOrLibrary"
        >
          <div class="kpi-head">
            <span>Earthwork fill</span>
            <v-icon size="18">mdi-arrow-expand-up</v-icon>
          </div>
          <div class="stat-value">{{ formatQty(displayFill) }} <small>m³</small></div>
          <div class="kpi-hint">Inspect takeoff →</div>
        </button>

        <button
          type="button"
          class="kpi-card warn"
          :class="{ hot: hoveredKpi === 'eoqs' }"
          @mouseenter="hoveredKpi = 'eoqs'"
          @mouseleave="hoveredKpi = null"
          @click="openProjects"
        >
          <div class="kpi-head">
            <span>Estimates Of Quantities in scope</span>
            <v-icon size="18">mdi-table-large</v-icon>
          </div>
          <div class="stat-value">{{ displayEoqs }}</div>
          <div class="kpi-hint">{{ meta?.item_count || 0 }} line items →</div>
        </button>
      </section>

      <div v-if="!hasData" class="surface-panel pa-10 text-center mb-5 empty-panel">
        <v-icon size="42" color="secondary" class="mb-3">mdi-chart-timeline-variant</v-icon>
        <h2 class="brand-font text-h6 mb-2">No analytics signal yet</h2>
        <p class="muted mb-4">
          Generate an Estimate Of Quantities and run a cost estimate to populate materials, earthwork, and cost charts.
        </p>
        <div class="d-flex justify-center ga-2 flex-wrap">
          <v-btn color="primary" @click="openFirstProjectOrLibrary">Generate Estimate Of Quantities</v-btn>
          <v-btn color="secondary" variant="tonal" @click="openProjects">Browse projects</v-btn>
        </div>
      </div>

      <template v-else>
        <v-row>
          <v-col cols="12" lg="5">
            <div class="surface-panel pa-5 h-100 balance-panel">
              <div class="d-flex align-center justify-space-between mb-4">
                <h2 class="brand-font text-h6 mb-0">Cut vs fill balance</h2>
                <v-chip
                  size="small"
                  variant="tonal"
                  :color="balanceSide === 'even' ? 'secondary' : balanceSide === 'cut' ? 'primary' : 'warning'"
                >
                  {{ earthwork?.balance_label }}
                </v-chip>
              </div>

              <div class="balance-bars mb-4">
                <div class="balance-row">
                  <div class="d-flex justify-space-between text-body-2 mb-1">
                    <span>Cut</span>
                    <strong>{{ formatQty(earthwork?.cut || 0) }} m³</strong>
                  </div>
                  <div class="bar-track tall">
                    <div class="bar-fill acid" :style="{ width: `${cutPct}%` }" />
                  </div>
                </div>
                <div class="balance-row mt-3">
                  <div class="d-flex justify-space-between text-body-2 mb-1">
                    <span>Fill</span>
                    <strong>{{ formatQty(earthwork?.fill || 0) }} m³</strong>
                  </div>
                  <div class="bar-track tall">
                    <div class="bar-fill mint" :style="{ width: `${fillPct}%` }" />
                  </div>
                </div>
              </div>

              <div class="balance-summary">
                <div class="text-caption muted mb-1">Net (cut − fill)</div>
                <div class="balance-value" :class="balanceSide">
                  {{ signed(earthwork?.balance || 0) }} m³
                </div>
                <p class="text-caption muted mb-0 mt-2">
                  Positive = cut surplus · Negative = fill surplus · Use this for borrow/spoil planning.
                </p>
              </div>
            </div>
          </v-col>

          <v-col cols="12" lg="7">
            <div class="surface-panel pa-5 h-100">
              <div class="d-flex flex-wrap align-center justify-space-between mb-4 ga-2">
                <h2 class="brand-font text-h6 mb-0">Cost distribution</h2>
                <span class="text-caption muted">Click a project to open</span>
              </div>

              <div v-if="!costs?.by_project.length" class="empty-inline">
                <p class="muted mb-3">No cost estimates in this scope.</p>
                <v-btn size="small" color="primary" @click="openFirstProjectOrLibrary">Run cost estimate</v-btn>
              </div>

              <div v-else class="cost-layout">
                <div class="donut" :style="{ background: donutGradient }" aria-hidden="true">
                  <div class="donut-hole">
                    <small>Total</small>
                    <b>{{ money(costs?.total_estimated || 0) }}</b>
                  </div>
                </div>
                <div class="cost-list">
                  <button
                    v-for="row in costDonutStops"
                    :key="row.project_id"
                    type="button"
                    class="cost-row"
                    :class="{ hot: hoveredCost === row.name }"
                    @mouseenter="hoveredCost = row.name"
                    @mouseleave="hoveredCost = null"
                    @click="openProject(row.project_id)"
                  >
                    <span class="swatch" :style="{ background: row.color }" />
                    <span class="name">{{ row.name }}</span>
                    <span class="amt">{{ money(row.amount) }}</span>
                    <div class="mini-track">
                      <i :style="{ width: barWidth(row.amount, maxCost), background: row.color }" />
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </v-col>
        </v-row>

        <v-row class="mt-1">
          <v-col cols="12" lg="7">
            <div class="surface-panel pa-5">
              <div class="d-flex flex-wrap align-center justify-space-between mb-4 ga-2">
                <h2 class="brand-font text-h6 mb-0">Top materials</h2>
                <div class="d-flex ga-2 align-center">
                  <v-select
                    v-model="materialsSort"
                    :items="[
                      { title: 'By quantity', value: 'quantity' },
                      { title: 'By share', value: 'share' },
                      { title: 'Name A–Z', value: 'name' },
                    ]"
                    density="compact"
                    hide-details
                    style="max-width: 150px"
                  />
                  <v-btn-toggle v-model="materialsView" mandatory density="compact" color="secondary">
                    <v-btn value="chart" icon="mdi-chart-bar" aria-label="Chart view" />
                    <v-btn value="table" icon="mdi-table" aria-label="Table view" />
                  </v-btn-toggle>
                </div>
              </div>

              <div v-if="!sortedMaterials.length" class="empty-inline">
                <p class="muted mb-3">Generate Estimates Of Quantities to populate material quantities.</p>
                <v-btn size="small" color="primary" @click="openFirstProjectOrLibrary">Generate Estimate Of Quantities</v-btn>
              </div>

              <template v-else-if="materialsView === 'chart'">
                <div
                  v-for="item in sortedMaterials"
                  :key="item.name"
                  class="material-bar"
                  :class="{ hot: hoveredMaterial === item.name }"
                  @mouseenter="hoveredMaterial = item.name"
                  @mouseleave="hoveredMaterial = null"
                >
                  <div class="d-flex justify-space-between text-body-2 mb-1">
                    <span>{{ item.name }}</span>
                    <span class="muted">
                      {{ formatQty(item.quantity) }}
                      <template v-if="item.unit"> {{ item.unit }}</template>
                      · {{ item.share ?? 0 }}%
                    </span>
                  </div>
                  <div class="bar-track">
                    <div
                      class="bar-fill acid anim"
                      :style="{ width: barWidth(item.quantity, maxMaterialQty) }"
                    />
                  </div>
                  <div v-if="hoveredMaterial === item.name" class="tooltip">
                    {{ item.name }} — {{ formatQty(item.quantity) }}{{ item.unit ? ` ${item.unit}` : '' }}
                    ({{ item.share ?? 0 }}% of total qty)
                  </div>
                </div>
              </template>

              <div v-else class="table-wrap">
                <v-table density="compact" class="materials-table">
                  <thead>
                    <tr>
                      <th>Material</th>
                      <th>Qty</th>
                      <th>Unit</th>
                      <th>Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in sortedMaterials" :key="item.name">
                      <td>{{ item.name }}</td>
                      <td>{{ formatQty(item.quantity) }}</td>
                      <td class="muted">{{ item.unit || '—' }}</td>
                      <td>{{ item.share ?? 0 }}%</td>
                    </tr>
                  </tbody>
                </v-table>
              </div>
            </div>
          </v-col>

          <v-col cols="12" lg="5">
            <div class="surface-panel pa-5 mb-4">
              <h2 class="brand-font text-h6 mb-4">Category breakdown</h2>
              <div v-if="!data.categories.length" class="muted">Categories appear after Estimate Of Quantities generation.</div>
              <div v-else class="category-list">
                <div v-for="cat in data.categories" :key="cat.name" class="category-row">
                  <div class="d-flex justify-space-between text-body-2 mb-1">
                    <v-chip size="x-small" variant="tonal" color="secondary">{{ cat.name }}</v-chip>
                    <span class="muted">{{ formatQty(cat.quantity) }} · {{ cat.share ?? 0 }}%</span>
                  </div>
                  <div class="bar-track">
                    <div class="bar-fill mint" :style="{ width: barWidth(cat.quantity, maxCategory) }" />
                  </div>
                </div>
              </div>
            </div>

            <div class="surface-panel pa-5">
              <h2 class="brand-font text-h6 mb-4">Pavement layers</h2>
              <div v-if="!pavementRows.length" class="muted">No pavement quantities in this scope.</div>
              <div
                v-for="row in pavementRows"
                :key="row.name"
                class="d-flex justify-space-between py-2 pavement-row"
              >
                <span>{{ row.name }}</span>
                <strong>{{ formatQty(row.qty) }}</strong>
              </div>
            </div>
          </v-col>
        </v-row>

        <div v-if="data.compare" class="surface-panel pa-5 mt-4 compare-panel">
          <div class="d-flex flex-wrap align-center justify-space-between mb-4 ga-2">
            <div>
              <div class="page-kicker mb-1">Compare mode</div>
              <h2 class="brand-font text-h6 mb-0">
                {{ data.compare.a.name }}
                <span class="muted mx-2">vs</span>
                {{ data.compare.b.name }}
              </h2>
            </div>
            <div class="d-flex ga-2">
              <v-btn size="small" variant="tonal" @click="openProject(data.compare.a.project_id)">Open A</v-btn>
              <v-btn size="small" variant="tonal" @click="openProject(data.compare.b.project_id)">Open B</v-btn>
            </div>
          </div>

          <div class="compare-kpis mb-4">
            <div class="compare-kpi">
              <span>Cost Δ</span>
              <b :class="{ up: data.compare.delta.cost > 0, down: data.compare.delta.cost < 0 }">
                {{ signed(data.compare.delta.cost) }}
              </b>
            </div>
            <div class="compare-kpi">
              <span>Cut Δ</span>
              <b :class="{ up: data.compare.delta.cut > 0, down: data.compare.delta.cut < 0 }">
                {{ signed(data.compare.delta.cut) }} m³
              </b>
            </div>
            <div class="compare-kpi">
              <span>Fill Δ</span>
              <b :class="{ up: data.compare.delta.fill > 0, down: data.compare.delta.fill < 0 }">
                {{ signed(data.compare.delta.fill) }} m³
              </b>
            </div>
          </div>

          <div class="table-wrap">
            <v-table density="compact">
              <thead>
                <tr>
                  <th>Material</th>
                  <th>{{ data.compare.a.name }}</th>
                  <th>{{ data.compare.b.name }}</th>
                  <th>Delta (B − A)</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in data.compare.delta.materials" :key="row.name">
                  <td>{{ row.name }}</td>
                  <td>{{ formatQty(row.a) }}</td>
                  <td>{{ formatQty(row.b) }}</td>
                  <td :class="{ 'text-success': row.delta > 0, 'text-error': row.delta < 0 }">
                    {{ signed(row.delta) }}
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.freshness {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  color: rgba(234, 240, 235, 0.55);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.kpi-card {
  text-align: left;
  border: 1px solid var(--cm-line, #24332c);
  background: linear-gradient(160deg, #12211c, #0d1814);
  border-radius: 0;
  padding: 18px 18px 14px;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
  animation: rise 0.45s ease both;
}

.kpi-card:hover,
.kpi-card.hot {
  transform: translateY(-2px);
  border-color: rgba(217, 255, 67, 0.45);
  background: #15261f;
}

.kpi-card.acid .stat-value {
  color: #d9ff43;
}
.kpi-card.mint .stat-value {
  color: #85ffd0;
}
.kpi-card.warn .stat-value {
  color: #ffc36a;
}

.kpi-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(234, 240, 235, 0.55);
  margin-bottom: 10px;
}

.stat-value {
  font-size: 1.7rem;
  font-weight: 700;
  line-height: 1.1;
}

.stat-value small {
  font-size: 0.85rem;
  font-weight: 500;
  opacity: 0.7;
}

.kpi-hint {
  margin-top: 10px;
  font-size: 0.78rem;
  color: rgba(234, 240, 235, 0.45);
}

.balance-value {
  font-size: 1.6rem;
  font-weight: 700;
}
.balance-value.cut {
  color: #d9ff43;
}
.balance-value.fill {
  color: #ffc36a;
}
.balance-value.even {
  color: #85ffd0;
}

.bar-track {
  height: 3px;
  background: #28362f;
  overflow: hidden;
}
.bar-track.tall {
  height: 10px;
}

.bar-fill {
  height: 100%;
  transition: width 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}
.bar-fill.acid {
  background: var(--acid, #d9ff43);
  box-shadow: 0 0 9px rgba(217, 255, 67, 0.35);
}
.bar-fill.mint {
  background: #85ffd0;
  box-shadow: 0 0 9px rgba(133, 255, 208, 0.3);
}

.material-bar {
  position: relative;
  margin-bottom: 14px;
  padding: 4px 0;
  transition: opacity 0.15s ease;
}
.material-bar.hot .bar-fill {
  filter: brightness(1.15);
}

.tooltip {
  position: absolute;
  right: 0;
  top: -8px;
  transform: translateY(-100%);
  background: #0c1713;
  border: 1px solid rgba(217, 255, 67, 0.35);
  color: #eaf0eb;
  font-size: 0.72rem;
  padding: 6px 8px;
  white-space: nowrap;
  z-index: 2;
  pointer-events: none;
}

.cost-layout {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 20px;
  align-items: center;
}

.donut {
  width: 148px;
  height: 148px;
  border-radius: 50%;
  display: grid;
  place-items: center;
}

.donut-hole {
  width: 92px;
  height: 92px;
  border-radius: 50%;
  background: #101f1a;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.donut-hole small {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(234, 240, 235, 0.5);
}
.donut-hole b {
  font-size: 0.85rem;
}

.cost-row {
  display: grid;
  grid-template-columns: 10px 1fr auto;
  grid-template-rows: auto auto;
  column-gap: 10px;
  row-gap: 4px;
  width: 100%;
  text-align: left;
  background: transparent;
  border: 0;
  color: inherit;
  padding: 8px 4px;
  cursor: pointer;
  border-radius: 0;
}
.cost-row.hot {
  background: rgba(217, 255, 67, 0.05);
}
.swatch {
  width: 10px;
  height: 10px;
  margin-top: 4px;
  grid-row: 1 / span 2;
}
.name {
  font-size: 0.9rem;
}
.amt {
  font-weight: 600;
  font-size: 0.85rem;
}
.mini-track {
  grid-column: 2 / span 2;
  height: 3px;
  background: #28362f;
}
.mini-track i {
  display: block;
  height: 100%;
  transition: width 0.45s ease;
}

.category-row {
  margin-bottom: 12px;
}

.pavement-row {
  border-bottom: 1px solid var(--cm-line, #24332c);
}

.compare-kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.compare-kpi {
  border: 1px solid var(--cm-line, #24332c);
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.02);
}
.compare-kpi span {
  display: block;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(234, 240, 235, 0.5);
  margin-bottom: 4px;
}
.compare-kpi b.up {
  color: #85ffd0;
}
.compare-kpi b.down {
  color: #ff8b6b;
}

.table-wrap {
  overflow-x: auto;
}

.materials-table th {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(234, 240, 235, 0.55);
}

.empty-inline {
  padding: 12px 0 4px;
}

@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .kpi-grid,
  .compare-kpis {
    grid-template-columns: 1fr;
  }
  .cost-layout {
    grid-template-columns: 1fr;
    justify-items: center;
  }
}
</style>
