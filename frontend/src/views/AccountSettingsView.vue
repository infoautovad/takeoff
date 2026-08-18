<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const prefs = reactive({
  emailAlerts: true,
  takeoffComplete: true,
  lowCredits: true,
  weeklyDigest: false,
  defaultLanding: 'dashboard',
  densifyTables: false,
})

const saved = ref(false)

function savePrefs() {
  localStorage.setItem(
    'autovad_account_settings',
    JSON.stringify({
      ...prefs,
      userId: auth.user?.id,
    }),
  )
  saved.value = true
  window.setTimeout(() => {
    saved.value = false
  }, 2200)
}

try {
  const raw = localStorage.getItem('autovad_account_settings')
  if (raw) {
    const parsed = JSON.parse(raw) as Partial<typeof prefs>
    Object.assign(prefs, parsed)
  }
} catch {
  /* ignore corrupt local prefs */
}
</script>

<template>
  <div class="account-page">
    <div class="page-kicker">ACCOUNT</div>
    <h1 class="brand-font page-title">Settings</h1>
    <p class="page-lede">Control notifications and workspace defaults for your takeoff workflow.</p>

    <section class="panel">
      <h2>Notifications</h2>
      <label class="toggle-row">
        <span>
          <b>Email alerts</b>
          <small>Receive important account and project notices by email</small>
        </span>
        <input v-model="prefs.emailAlerts" type="checkbox" />
      </label>
      <label class="toggle-row">
        <span>
          <b>Takeoff complete</b>
          <small>Notify when AI analysis or Estimate Of Quantities generation finishes</small>
        </span>
        <input v-model="prefs.takeoffComplete" type="checkbox" />
      </label>
      <label class="toggle-row">
        <span>
          <b>Low credit warning</b>
          <small>Alert when remaining AI credits drop below 15%</small>
        </span>
        <input v-model="prefs.lowCredits" type="checkbox" />
      </label>
      <label class="toggle-row">
        <span>
          <b>Weekly digest</b>
          <small>Summary of project activity every Monday</small>
        </span>
        <input v-model="prefs.weeklyDigest" type="checkbox" />
      </label>
    </section>

    <section class="panel mt">
      <h2>Workspace defaults</h2>
      <label class="field">
        <span>After sign in, open</span>
        <select v-model="prefs.defaultLanding">
          <option value="dashboard">Dashboard</option>
          <option value="projects">Projects</option>
          <option value="analytics">Analytics</option>
        </select>
      </label>
      <label class="toggle-row">
        <span>
          <b>Compact Estimate Of Quantities tables</b>
          <small>Use denser row spacing in quantity review screens</small>
        </span>
        <input v-model="prefs.densifyTables" type="checkbox" />
      </label>
    </section>

    <div class="actions">
      <button type="button" class="save-btn" @click="savePrefs">Save settings</button>
      <span v-if="saved" class="saved">Saved locally on this device</span>
    </div>
  </div>
</template>

<style scoped>
.account-page {
  max-width: 720px;
}

.page-title {
  font-size: clamp(1.8rem, 3vw, 2.4rem);
  font-weight: 800;
  letter-spacing: -0.04em;
  margin: 6px 0 10px;
}

.page-lede {
  color: #8a9690;
  margin: 0 0 28px;
}

.panel {
  border: 1px solid #24322c;
  background: #0d1814;
  padding: 22px;
}

.panel.mt {
  margin-top: 14px;
}

.panel h2 {
  margin: 0 0 16px;
  font-size: 0.95rem;
}

.toggle-row {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
  padding: 14px 0;
  border-top: 1px solid #1c2924;
  cursor: pointer;
}

.toggle-row:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.toggle-row b {
  display: block;
  color: #eaf0eb;
  font-size: 0.92rem;
}

.toggle-row small {
  display: block;
  margin-top: 4px;
  color: #748078;
  font-size: 0.8rem;
  line-height: 1.45;
}

.toggle-row input {
  width: 18px;
  height: 18px;
  accent-color: var(--acid);
}

.field {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #748078;
}

.field select {
  width: 100%;
  max-width: 280px;
  padding: 10px 12px;
  border: 1px solid #2a3a33;
  background: #0b1512;
  color: #eaf0eb;
  font: 13px var(--font-mono);
  text-transform: none;
  letter-spacing: 0;
}

.actions {
  margin-top: 18px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.save-btn {
  border: 0;
  background: var(--acid);
  color: #10170c;
  padding: 12px 18px;
  font: 10px var(--font-mono);
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
}

.saved {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 10px;
}
</style>
