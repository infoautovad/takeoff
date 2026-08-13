<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getPageImageUrl, getViewerMeta } from '@/api/documents'

const route = useRoute()
const router = useRouter()
const documentId = computed(() => Number(route.params.documentId))
const page = ref(Number(route.query.page || 1))
const meta = ref<Awaited<ReturnType<typeof getViewerMeta>> | null>(null)
const imageUrl = ref<string | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    meta.value = await getViewerMeta(documentId.value)
    if (page.value < 1) page.value = 1
    if (meta.value.page_count && page.value > meta.value.page_count) page.value = meta.value.page_count
    await loadPage()
  } catch {
    error.value = 'Could not open document viewer'
  } finally {
    loading.value = false
  }
}

async function loadPage() {
  if (imageUrl.value) window.URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = null
  if (meta.value?.has_pdf_preview) {
    imageUrl.value = await getPageImageUrl(documentId.value, page.value)
  }
}

onMounted(load)
watch(documentId, load)
watch(page, async () => {
  router.replace({ query: { ...route.query, page: String(page.value) } })
  await loadPage()
})
onUnmounted(() => {
  if (imageUrl.value) window.URL.revokeObjectURL(imageUrl.value)
})

const currentText = computed(() => meta.value?.text_pages?.find((p) => p.page === page.value)?.text || meta.value?.text_pages?.[0]?.text || '')
</script>

<template>
  <div class="page-shell">
    <v-btn variant="text" color="primary" prepend-icon="mdi-arrow-left" class="mb-3 px-0" @click="router.back()">Back</v-btn>
    <div v-if="loading" class="text-center py-12"><v-progress-circular indeterminate color="primary" /></div>
    <v-alert v-else-if="error" type="error" variant="tonal">{{ error }}</v-alert>
    <template v-else-if="meta">
      <div class="d-flex flex-wrap align-center justify-space-between mb-4 ga-3">
        <div>
          <h1 class="brand-font text-h5 mb-1">{{ meta.filename }}</h1>
          <p class="muted mb-0">Source viewer · Page {{ page }} of {{ meta.page_count || 1 }}</p>
        </div>
        <div class="d-flex ga-2 align-center">
          <v-btn variant="tonal" :disabled="page <= 1" @click="page -= 1">Prev</v-btn>
          <v-btn variant="tonal" :disabled="page >= (meta.page_count || 1)" @click="page += 1">Next</v-btn>
        </div>
      </div>
      <v-row>
        <v-col cols="12" md="7">
          <div class="surface-panel pa-3 viewer-frame">
            <img v-if="imageUrl" :src="imageUrl" alt="Document page" class="page-image" />
            <div v-else class="muted text-center py-10">
              Preview image available for PDFs. Showing extracted text for this file type.
            </div>
          </div>
        </v-col>
        <v-col cols="12" md="5">
          <div class="surface-panel pa-4">
            <h2 class="brand-font text-subtitle-1 mb-2">Extracted text / notes</h2>
            <p v-if="meta.summary" class="text-body-2 mb-3">{{ meta.summary }}</p>
            <pre class="text-page">{{ currentText || 'No extracted text for this page yet. Run Analyze first.' }}</pre>
          </div>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<style scoped>
.viewer-frame {
  min-height: 480px;
  background: #0a1411;
}
.page-image {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 0;
  border: 1px solid var(--panel-border);
}
.text-page {
  white-space: pre-wrap;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #c9d3cd;
  max-height: 560px;
  overflow: auto;
  margin: 0;
  padding: 12px;
  background: #0a1411;
  border: 1px solid var(--panel-border);
}
</style>
