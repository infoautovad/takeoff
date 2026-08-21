<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { TrainingCaseDetail } from '@/api/training'

const props = defineProps<{
  detail: TrainingCaseDetail | null
}>()

const route = useRoute()
const router = useRouter()

const caseId = computed(() => Number(route.params.id))
const stage1Done = computed(() => Boolean(props.detail?.has_autovad_eoq))
const stage2Done = computed(() => Boolean(props.detail?.has_expected))
const stage3Done = computed(() => Boolean(props.detail?.runs?.some((r) => r.report)))

const current = computed(() => {
  const p = route.path
  if (p.includes('/original')) return 'original'
  if (p.includes('/evaluate')) return 'evaluate'
  if (p.includes('/analyze')) return 'analyze'
  return 'hub'
})

function go(path: string, locked = false) {
  if (locked) return
  router.push(path)
}
</script>

<template>
  <div class="stage-rail mb-5">
    <button
      type="button"
      class="stage-pill"
      :class="{
        done: stage1Done,
        active: current === 'analyze',
      }"
      @click="go(`/backend/cases/${caseId}/analyze`)"
    >
      1 · Analyze
    </button>
    <div class="stage-line" />
    <button
      type="button"
      class="stage-pill"
      :class="{
        done: stage2Done,
        active: current === 'original',
        locked: !stage1Done,
      }"
      :disabled="!stage1Done"
      @click="go(`/backend/cases/${caseId}/original`, !stage1Done)"
    >
      2 · Original EOQ
    </button>
    <div class="stage-line" />
    <button
      type="button"
      class="stage-pill"
      :class="{
        done: stage3Done,
        active: current === 'evaluate',
        locked: !stage1Done || !stage2Done,
      }"
      :disabled="!stage1Done || !stage2Done"
      @click="go(`/backend/cases/${caseId}/evaluate`, !stage1Done || !stage2Done)"
    >
      3 · Evaluate
    </button>
  </div>
</template>

<style scoped>
.stage-rail {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.stage-pill {
  font: 10px monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #8a968e;
  background: transparent;
  cursor: pointer;
}
.stage-pill:disabled {
  cursor: not-allowed;
}
.stage-pill.active {
  border-color: rgba(217, 255, 67, 0.55);
  color: #d9ff43;
}
.stage-pill.done:not(.active) {
  border-color: rgba(120, 200, 140, 0.45);
  color: #9fdfb0;
  background: rgba(120, 200, 140, 0.08);
}
.stage-pill.locked {
  opacity: 0.45;
}
.stage-line {
  width: 28px;
  height: 1px;
  background: rgba(255, 255, 255, 0.15);
}
</style>
