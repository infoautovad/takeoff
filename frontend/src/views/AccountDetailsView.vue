<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { planCreditAllowance, creditsRemaining, creditsRemainingPct } from '@/utils/credits'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

const planLabel: Record<string, string> = {
  starter: 'Starter',
  professional: 'Professional',
  business: 'Business',
  enterprise: 'Enterprise',
}

const roleLabel: Record<string, string> = {
  admin: 'Admin',
  project_manager: 'Project manager',
  design_engineer: 'Design engineer',
  quantity_surveyor: 'Quantity surveyor',
  reviewer: 'Reviewer',
  client: 'Client',
  other: 'Other',
}

const user = computed(() => auth.user)
const planName = computed(() => planLabel[user.value?.plan || ''] || user.value?.plan || '—')
const roleName = computed(() => roleLabel[user.value?.role || ''] || user.value?.role || '—')
const allowance = computed(() => planCreditAllowance(user.value?.plan))
const remaining = computed(() => creditsRemaining(user.value?.plan))
const pct = computed(() => creditsRemainingPct(user.value?.plan))
</script>

<template>
  <div class="account-page">
    <div class="page-kicker">ACCOUNT</div>
    <h1 class="brand-font page-title">Account details</h1>
    <p class="page-lede">Your AutoVAD profile, role, and subscription summary.</p>

    <div class="detail-grid">
      <section class="panel">
        <h2>Profile</h2>
        <dl>
          <div>
            <dt>Full name</dt>
            <dd>{{ user?.full_name }}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{{ user?.email }}</dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>{{ roleName }}</dd>
          </div>
          <div>
            <dt>Member since</dt>
            <dd>{{ user?.created_at ? formatDate(user.created_at) : '—' }}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              <span class="status-pill" :class="{ on: user?.is_active }">
                {{ user?.is_active ? 'Active' : 'Inactive' }}
              </span>
            </dd>
          </div>
        </dl>
      </section>

      <section class="panel">
        <h2>Plan & credits</h2>
        <dl>
          <div>
            <dt>Current plan</dt>
            <dd>{{ planName }}</dd>
          </div>
          <div>
            <dt>Monthly allowance</dt>
            <dd>{{ allowance.toLocaleString() }} AI credits</dd>
          </div>
          <div>
            <dt>Credits available</dt>
            <dd class="acid">{{ remaining.toLocaleString() }} · {{ pct }}% remaining</dd>
          </div>
        </dl>
        <div class="panel-actions">
          <router-link class="ghost-link" to="/account/billing">Manage billing & credits →</router-link>
          <router-link class="ghost-link" to="/account/settings">Open settings →</router-link>
        </div>
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
  max-width: 540px;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 14px;
}

.panel {
  border: 1px solid #24322c;
  background: #0d1814;
  padding: 22px 22px 18px;
}

.panel h2 {
  margin: 0 0 18px;
  font-size: 0.95rem;
  letter-spacing: -0.02em;
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
  font-size: 0.95rem;
}

.acid {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 0.85rem;
}

.status-pill {
  display: inline-block;
  padding: 3px 8px;
  border: 1px solid #3a4a43;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #8a9690;
}

.status-pill.on {
  border-color: rgba(217, 255, 67, 0.35);
  color: var(--acid);
  background: rgba(217, 255, 67, 0.06);
}

.panel-actions {
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ghost-link {
  color: var(--acid);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.ghost-link:hover {
  text-decoration: underline;
}

@media (max-width: 800px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
