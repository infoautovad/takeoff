<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const avatarInitial = computed(() => {
  const name = auth.user?.full_name || auth.user?.email || 'A'
  return name.trim().charAt(0).toUpperCase() || 'A'
})

const navItems = [
  { title: 'Training lab', icon: 'mdi-brain', to: '/backend' },
]

const pageTitle = computed(() => {
  const name = String(route.name || '')
  if (name === 'backend-case-analyze') return 'Stage 1 · Analyze'
  if (name === 'backend-case-original') return 'Stage 2 · Original EOQ'
  if (name === 'backend-case-evaluate') return 'Stage 3 · Evaluate'
  if (name === 'backend-case') return 'Training case'
  return 'Training portal'
})

const pageKicker = computed(() => {
  const name = String(route.name || '')
  if (name.startsWith('backend-case')) return 'TRAINING CASE'
  return 'AGENT & MODEL LAB'
})

function logout() {
  auth.logout()
  router.push({ name: 'landing' })
}

function goHome() {
  router.push({ name: 'landing' })
}
</script>

<template>
  <v-navigation-drawer permanent width="248" class="backend-nav" :border="0">
    <button type="button" class="brand-block" aria-label="AutoVAD home" @click="goHome">
      <div class="brand-mark" aria-hidden="true">
        <i /><i /><i />
      </div>
      <div>
        <div class="brand-name">Auto<span>VAD</span></div>
        <div class="brand-sub">Admin portal</div>
      </div>
    </button>

    <div class="nav-kicker">Portal</div>
    <v-list nav density="compact" class="nav-list px-2">
      <v-list-item
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :prepend-icon="item.icon"
        :title="item.title"
        rounded="lg"
        color="primary"
      />
    </v-list>

    <template #append>
      <div class="nav-footer">
        <div class="account-card">
          <div class="account-avatar">{{ avatarInitial }}</div>
          <div class="account-meta">
            <div class="account-name">{{ auth.user?.full_name || 'Admin' }}</div>
            <div class="account-email">{{ auth.user?.email }}</div>
            <div class="account-role">portal admin</div>
          </div>
        </div>
        <v-btn block color="primary" variant="flat" class="signout-btn" @click="logout">
          Sign out
        </v-btn>
      </div>
    </template>
  </v-navigation-drawer>

  <v-app-bar flat class="backend-bar" height="64">
    <div class="bar-copy">
      <div class="bar-kicker">{{ pageKicker }}</div>
      <div class="bar-title">{{ pageTitle }}</div>
    </div>
    <v-spacer />
    <v-btn variant="tonal" color="secondary" class="mr-2" @click="goHome">Website</v-btn>
  </v-app-bar>

  <v-main class="backend-main">
    <div class="backend-content">
      <router-view />
    </div>
  </v-main>
</template>

<style scoped>
.backend-nav {
  background: #07100e !important;
  border-right: 1px solid rgba(217, 255, 67, 0.14) !important;
  color: #eaf0eb;
}
.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 18px 16px 8px;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
  width: calc(100% - 32px);
}
.brand-mark {
  width: 34px;
  height: 34px;
  position: relative;
  flex-shrink: 0;
}
.brand-mark i {
  position: absolute;
  inset: 0;
  border: 1.5px solid #d9ff43;
  border-radius: 4px;
  transform: rotate(12deg);
}
.brand-mark i:nth-child(2) {
  transform: rotate(-8deg);
  opacity: 0.55;
}
.brand-mark i:nth-child(3) {
  transform: rotate(28deg);
  opacity: 0.3;
}
.brand-name {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 1.15rem;
  letter-spacing: -0.03em;
  color: #f4f6ef;
}
.brand-name span {
  color: #d9ff43;
}
.brand-sub {
  font: 9px monospace;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #7d8a82;
  margin-top: 2px;
}
.nav-kicker {
  font: 9px monospace;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #66756d;
  padding: 18px 20px 6px;
}
.nav-list :deep(.v-list-item-title) {
  font-size: 13px !important;
}
.nav-list :deep(.v-list-item--active) {
  background: rgba(217, 255, 67, 0.14) !important;
}
.nav-list :deep(.v-list-item--active .v-list-item-title),
.nav-list :deep(.v-list-item--active .v-list-item__prepend) {
  color: #d9ff43 !important;
}
.nav-footer {
  padding: 12px 14px 16px;
  border-top: 1px solid rgba(217, 255, 67, 0.12);
}
.account-card {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
  padding: 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.account-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #d9ff43;
  color: #07100e;
  display: grid;
  place-items: center;
  font-weight: 700;
  flex-shrink: 0;
}
.account-name {
  font-size: 13px;
  font-weight: 600;
  color: #f4f6ef;
}
.account-email {
  font-size: 10px;
  color: #8a968e;
  word-break: break-all;
}
.account-role {
  font: 8px monospace;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #d9ff43;
  margin-top: 2px;
}
.signout-btn {
  font-weight: 600;
  letter-spacing: 0.04em;
}
.backend-bar {
  background: #0a1512 !important;
  border-bottom: 1px solid rgba(217, 255, 67, 0.12) !important;
  color: #eaf0eb;
}
.bar-copy {
  padding-left: 8px;
}
.bar-kicker {
  font: 9px monospace;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #7d8a82;
}
.bar-title {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 1.05rem;
  color: #f4f6ef;
}
.backend-main {
  background: #07100e;
}
.backend-content {
  min-height: calc(100vh - 64px);
}
</style>
