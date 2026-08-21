<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { globalSearch } from '@/api/search'

const router = useRouter()
const q = ref('')
const loading = ref(false)
const result = ref<Awaited<ReturnType<typeof globalSearch>> | null>(null)

async function runSearch() {
  if (!q.value.trim()) return
  loading.value = true
  try {
    result.value = await globalSearch(q.value.trim())
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page-shell">
    <div class="page-kicker">Find anything</div>
    <h1 class="brand-font text-h4 mb-1">Search</h1>
    <p class="muted mb-6">Find projects, drawings, Estimate Of Quantities items, materials, and documents.</p>

    <div class="surface-panel pa-4 mb-5">
      <v-row dense align="center">
        <v-col cols="12" md="9">
          <v-text-field
            v-model="q"
            label="Search projects, drawings, chainage, materials, Estimate Of Quantities..."
            prepend-inner-icon="mdi-magnify"
            hide-details
            @keyup.enter="runSearch"
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-btn block color="primary" :loading="loading" @click="runSearch">Search</v-btn>
        </v-col>
      </v-row>
    </div>

    <template v-if="result">
      <v-row>
        <v-col cols="12" md="4">
          <div class="surface-panel pa-4">
            <h2 class="brand-font text-subtitle-1 mb-3">Projects ({{ result.projects.length }})</h2>
            <div v-if="!result.projects.length" class="muted">No matches</div>
            <div
              v-for="p in result.projects"
              :key="p.id"
              class="result-row"
              @click="router.push(`/projects/${p.id}`)"
            >
              <div class="font-weight-medium">{{ p.name }}</div>
              <div class="text-caption muted">{{ p.location || 'No location' }} · {{ p.status }}</div>
            </div>
          </div>
        </v-col>
        <v-col cols="12" md="4">
          <div class="surface-panel pa-4">
            <h2 class="brand-font text-subtitle-1 mb-3">Documents ({{ result.documents.length }})</h2>
            <div v-if="!result.documents.length" class="muted">No matches</div>
            <div
              v-for="d in result.documents"
              :key="d.id"
              class="result-row"
              @click="router.push(`/projects/${d.project_id}`)"
            >
              <div class="font-weight-medium">{{ d.filename }}</div>
              <div class="text-caption muted">{{ d.status }}</div>
            </div>
          </div>
        </v-col>
        <v-col cols="12" md="4">
          <div class="surface-panel pa-4">
            <h2 class="brand-font text-subtitle-1 mb-3">Estimate Of Quantities items ({{ result.eoq_items.length }})</h2>
            <div v-if="!result.eoq_items.length" class="muted">No matches</div>
            <div v-for="i in result.eoq_items" :key="i.id" class="result-row static">
              <div class="font-weight-medium">{{ i.description }}</div>
              <div class="text-caption muted">{{ i.quantity }} {{ i.unit }} · {{ i.category || 'General' }}</div>
            </div>
          </div>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<style scoped>
.result-row {
  padding: 10px 0;
  border-bottom: 1px solid var(--cm-line);
  cursor: pointer;
}
.result-row.static {
  cursor: default;
}
.result-row:hover:not(.static) {
  color: var(--acid);
}
</style>
