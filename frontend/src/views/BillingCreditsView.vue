<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { planCreditAllowance, creditsRemaining, creditsRemainingPct } from '@/utils/credits'

const auth = useAuthStore()
const router = useRouter()

const planLabel: Record<string, string> = {
  starter: 'Starter · $59/mo',
  professional: 'Professional · $199/mo',
  business: 'Business · $499/mo',
  enterprise: 'Enterprise · Custom',
}

const planName = computed(() => planLabel[auth.user?.plan || ''] || auth.user?.plan || '—')
const allowance = computed(() => planCreditAllowance(auth.user?.plan))
const remaining = computed(() => creditsRemaining(auth.user?.plan))
const pct = computed(() => creditsRemainingPct(auth.user?.plan))
const used = computed(() => Math.max(0, allowance.value - remaining.value))

function goBuyCredits() {
  router.push({ path: '/', hash: '#pricing' })
}

function goProjects() {
  router.push('/projects')
}
</script>

<template>
  <div class="account-page">
    <div class="page-kicker">ACCOUNT</div>
    <h1 class="brand-font page-title">Billing & credits</h1>
    <p class="page-lede">Track AI credit usage for takeoffs and manage your subscription plan.</p>

    <section class="hero-panel">
      <div>
        <small>CREDITS AVAILABLE</small>
        <strong>{{ remaining.toLocaleString() }}</strong>
        <em>{{ pct }}% remaining · {{ used.toLocaleString() }} used this period</em>
      </div>
      <div class="meter" aria-hidden="true">
        <i :style="{ width: `${pct}%` }" />
      </div>
      <div class="hero-actions">
        <button type="button" class="primary" @click="goBuyCredits">Buy extra credits</button>
        <button type="button" class="secondary" @click="goProjects">Open projects</button>
      </div>
    </section>

    <div class="detail-grid">
      <section class="panel">
        <h2>Subscription</h2>
        <dl>
          <div>
            <dt>Active plan</dt>
            <dd>{{ planName }}</dd>
          </div>
          <div>
            <dt>Included monthly credits</dt>
            <dd>{{ allowance.toLocaleString() }}</dd>
          </div>
          <div>
            <dt>Usage rule</dt>
            <dd>1 takeoff analysis = 1 AI credit</dd>
          </div>
        </dl>
      </section>

      <section class="panel">
        <h2>Need more capacity?</h2>
        <p>
          Professional and higher plans include credit rollover. Extra credits can be purchased at
          $0.30 each (50 minimum).
        </p>
        <ul>
          <li>Starter — 100 credits / month</li>
          <li>Professional — 500 credits / month</li>
          <li>Business — 2,000 credits / month</li>
          <li>Enterprise — 10,000+ credits</li>
        </ul>
        <button type="button" class="text-cta" @click="goBuyCredits">Compare plans on the homepage →</button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.account-page {
  max-width: 920px;
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

.hero-panel {
  border: 1px solid rgba(217, 255, 67, 0.28);
  background: linear-gradient(145deg, rgba(217, 255, 67, 0.08), #0d1814 55%);
  padding: 24px;
  margin-bottom: 14px;
}

.hero-panel small {
  display: block;
  font-family: var(--font-mono);
  font-size: 8px;
  letter-spacing: 0.1em;
  color: #748078;
}

.hero-panel strong {
  display: block;
  margin-top: 8px;
  font-size: clamp(2.4rem, 5vw, 3.4rem);
  letter-spacing: -0.05em;
  color: var(--acid);
  line-height: 1;
}

.hero-panel em {
  display: block;
  margin-top: 10px;
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 11px;
  color: #aab6af;
}

.meter {
  margin-top: 18px;
  height: 3px;
  background: #26342e;
}

.meter > i {
  display: block;
  height: 100%;
  background: var(--acid);
  box-shadow: 0 0 8px rgba(217, 255, 67, 0.55);
}

.hero-actions {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.primary,
.secondary {
  border: 0;
  padding: 12px 16px;
  font: 10px var(--font-mono);
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  cursor: pointer;
}

.primary {
  background: var(--acid);
  color: #10170c;
}

.secondary {
  background: transparent;
  border: 1px solid #31433b;
  color: #d5ddd7;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.panel {
  border: 1px solid #24322c;
  background: #0d1814;
  padding: 22px;
}

.panel h2 {
  margin: 0 0 16px;
  font-size: 0.95rem;
}

.panel p,
.panel li {
  color: #8a9690;
  font-size: 0.88rem;
  line-height: 1.6;
}

.panel ul {
  margin: 12px 0 16px;
  padding-left: 18px;
}

dl {
  margin: 0;
  display: grid;
  gap: 14px;
}

dl > div {
  display: grid;
  gap: 4px;
  padding-bottom: 12px;
  border-bottom: 1px solid #1c2924;
}

dl > div:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

dt {
  font-family: var(--font-mono);
  font-size: 8px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #68756e;
}

dd {
  margin: 0;
  color: #e8efe9;
}

.text-cta {
  border: 0;
  background: none;
  padding: 0;
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  cursor: pointer;
}

@media (max-width: 800px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
