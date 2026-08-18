<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const firstName = ref('')
const lastName = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const role = ref<string | null>(null)
const plan = ref<string | null>(null)
const showPassword = ref(false)
const showConfirmPassword = ref(false)
const localError = ref<string | null>(null)

const roles = [
  { title: 'Design Engineer', value: 'design_engineer' },
  { title: 'Quantity Surveyor', value: 'quantity_surveyor' },
  { title: 'Project Manager', value: 'project_manager' },
  { title: 'Reviewer', value: 'reviewer' },
  { title: 'Client / Viewer', value: 'client' },
  { title: 'Other', value: 'other' },
]

const plans = [
  {
    id: 'starter',
    name: 'Starter',
    price: '$59',
    period: '/ month',
    blurb: 'For individual estimators beginning with AI-assisted takeoffs.',
    features: [
      '100 AI credits monthly',
      'PDF plan takeoffs only',
      'Bid-item template matching',
      'No credit rollover',
    ],
    cta: 'Choose Starter',
    recommended: false,
  },
  {
    id: 'professional',
    name: 'Professional',
    price: '$199',
    period: '/ month',
    blurb: 'For civil estimators producing frequent review-ready quantity takeoffs.',
    features: [
      '500 AI credits monthly',
      'Support for PDF, DWG, DXF, and LandXML',
      'Source notes and confidence flags',
      '90-day credit rollover',
    ],
    cta: 'Choose Professional',
    recommended: true,
  },
  {
    id: 'business',
    name: 'Business',
    price: '$499',
    period: '/ month',
    blurb: 'For engineering firms and estimating teams with sustained project volume.',
    features: [
      '2,000 AI credits monthly',
      'Entity bid-item templates',
      'Project Management workspace',
      '90-day credit rollover',
    ],
    cta: 'Choose Business',
    recommended: false,
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    blurb: 'For organizations needing 10,000+ AI credits, onboarding, and procurement support.',
    features: [
      '10,000+ AI credits',
      'Project Management workspace',
      'Multi-user deployment',
      'Volume and annual options',
    ],
    cta: 'Contact Sales',
    recommended: false,
  },
]

const passwordChecks = computed(() => {
  const p = password.value || ''
  return [
    { label: '8+ characters', ok: p.length >= 8 },
    { label: 'Uppercase letter', ok: /[A-Z]/.test(p) },
    { label: 'Lowercase letter', ok: /[a-z]/.test(p) },
    { label: 'Number', ok: /[0-9]/.test(p) },
    { label: 'Special character', ok: /[^A-Za-z0-9]/.test(p) },
  ]
})

const passwordStrong = computed(() => passwordChecks.value.every((c) => c.ok))
const passwordsMatch = computed(
  () => Boolean(password.value) && password.value === confirmPassword.value,
)

function selectPlan(id: string) {
  plan.value = id
  localError.value = null
}

async function submit() {
  localError.value = null
  auth.error = null

  if (!firstName.value.trim()) {
    localError.value = 'First name is required.'
    return
  }
  if (!lastName.value.trim()) {
    localError.value = 'Last name is required.'
    return
  }
  const fullName = `${firstName.value.trim()} ${lastName.value.trim()}`
  if (fullName.length < 2) {
    localError.value = 'Please enter a valid first and last name.'
    return
  }
  if (!email.value.trim()) {
    localError.value = 'Email is required.'
    return
  }
  if (!role.value) {
    localError.value = 'Please select a role.'
    return
  }
  if (!passwordStrong.value) {
    localError.value =
      'Password must include uppercase, lowercase, a number, and a special character (min 8 characters).'
    return
  }
  if (!confirmPassword.value) {
    localError.value = 'Please re-enter your password.'
    return
  }
  if (!passwordsMatch.value) {
    localError.value = 'Passwords do not match. Please enter the same password in both fields.'
    return
  }
  if (!plan.value) {
    localError.value = 'Please select a subscription plan to create your account.'
    return
  }

  try {
    await auth.register({
      email: email.value.trim(),
      full_name: fullName,
      password: password.value,
      confirm_password: confirmPassword.value,
      role: role.value!,
      plan: plan.value,
    })
    router.push('/')
  } catch {
    // auth.error already set
  }
}
</script>

<template>
  <div class="auth-page cm-grid-bg">
    <div class="auth-visual">
      <div class="auth-visual-inner">
        <div>
          <div class="page-kicker">AutoVAD / Join</div>
          <div class="brand-font auth-title mb-4">
            Join Auto<span>VAD</span>
          </div>
          <p class="auth-lede">
            Create your account, choose a plan, and start AI-assisted civil takeoff and Estimate Of Quantities generation.
          </p>
        </div>
        <div class="auth-member-link">
          <span>Already a member?</span>
          <router-link to="/?signin=1">Sign in</router-link>
        </div>
      </div>
    </div>

    <div class="auth-form-wrap">
      <div class="auth-form surface-panel pa-6 pa-md-8">
        <div class="page-kicker">Create account</div>
        <h1 class="brand-font text-h4 mb-1">Get started</h1>
        <p class="muted mb-5">First name, last name, email, role, matching passwords, and a plan are required.</p>

        <v-alert v-if="localError || auth.error" type="error" variant="tonal" class="mb-4">
          {{ localError || auth.error }}
        </v-alert>

        <v-form @submit.prevent="submit">
          <div class="name-row mb-2">
            <v-text-field
              v-model="firstName"
              label="First name"
              required
              autocomplete="given-name"
            />
            <v-text-field
              v-model="lastName"
              label="Last name"
              required
              autocomplete="family-name"
            />
          </div>
          <v-text-field
            v-model="email"
            label="Email"
            type="email"
            class="mb-2"
            required
            autocomplete="email"
          />
          <v-select
            v-model="role"
            :items="roles"
            label="Role"
            placeholder="Select role"
            class="mb-2"
            required
            clearable
            :rules="[(v) => !!v || 'Please select a role']"
          />
          <v-text-field
            v-model="password"
            label="Password"
            :type="showPassword ? 'text' : 'password'"
            :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
            class="mb-2"
            required
            autocomplete="new-password"
            hint="Uppercase, lowercase, number, and special character required"
            persistent-hint
            @click:append-inner="showPassword = !showPassword"
          />
          <ul class="pw-checks mb-3">
            <li v-for="c in passwordChecks" :key="c.label" :class="{ ok: c.ok }">
              {{ c.label }}
            </li>
          </ul>
          <v-text-field
            v-model="confirmPassword"
            label="Re-enter password"
            :type="showConfirmPassword ? 'text' : 'password'"
            :append-inner-icon="showConfirmPassword ? 'mdi-eye-off' : 'mdi-eye'"
            class="mb-2"
            required
            autocomplete="new-password"
            :error="Boolean(confirmPassword) && !passwordsMatch"
            :error-messages="
              confirmPassword && !passwordsMatch ? 'Passwords do not match' : undefined
            "
            :hint="passwordsMatch ? 'Passwords match' : 'Must match the password above'"
            persistent-hint
            @click:append-inner="showConfirmPassword = !showConfirmPassword"
          />

          <div class="plan-block mb-5 mt-4">
            <div class="plan-heading">
              <span>Select a plan</span>
              <em>Required — account will not be created without a plan</em>
            </div>
            <div class="plan-grid">
              <button
                v-for="p in plans"
                :key="p.id"
                type="button"
                class="plan-card"
                :class="{ selected: plan === p.id, recommended: p.recommended }"
                @click="selectPlan(p.id)"
              >
                <div v-if="p.recommended" class="plan-badge">Recommended</div>
                <div class="plan-name">{{ p.name }}</div>
                <div class="plan-price">
                  <strong>{{ p.price }}</strong>
                  <span v-if="p.period">{{ p.period }}</span>
                </div>
                <p class="plan-blurb">{{ p.blurb }}</p>
                <ul>
                  <li v-for="f in p.features" :key="f">{{ f }}</li>
                </ul>
                <div class="plan-cta">{{ plan === p.id ? 'Selected' : p.cta }}</div>
              </button>
            </div>
          </div>

          <v-btn
            type="submit"
            color="primary"
            size="large"
            block
            :loading="auth.loading"
            :disabled="!plan || !passwordStrong || !passwordsMatch"
          >
            Create account
          </v-btn>
        </v-form>

        <div class="auth-footer-row">
          <router-link to="/">← Back to home</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 0.85fr 1.15fr;
}

.auth-visual {
  position: relative;
  color: #fff;
  display: flex;
  align-items: stretch;
  padding: 48px 4vw;
  border-right: 1px solid var(--line);
  background:
    radial-gradient(circle at 75% 40%, rgba(72, 171, 135, 0.16), transparent 32%),
    #07100e;
}

.auth-visual-inner {
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 40px;
  min-height: 70vh;
}

.auth-member-link {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding-top: 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.auth-member-link span {
  color: #8a9690;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.04em;
}

.auth-footer-row {
  margin-top: 24px;
  text-align: center;
}

.name-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

@media (max-width: 560px) {
  .name-row {
    grid-template-columns: 1fr;
  }
}

.auth-title {
  font-size: clamp(42px, 5vw, 64px);
  font-weight: 900;
  line-height: 0.95;
  letter-spacing: -0.06em;
}

.auth-title span {
  color: var(--acid);
}

.auth-lede {
  color: #aab4ad;
  font-size: 16px;
  line-height: 1.65;
  max-width: 420px;
}

.auth-form-wrap {
  display: grid;
  place-items: center;
  padding: 28px 20px;
  background: #0a1411;
  overflow: auto;
}

.auth-form {
  width: 100%;
  max-width: 980px;
  border-color: rgba(217, 255, 67, 0.22);
  box-shadow: 0 25px 70px rgba(0, 0, 0, 0.35);
}

.pw-checks {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}

.pw-checks li {
  font-size: 11px;
  font-family: var(--font-mono);
  color: #7a8a82;
}

.pw-checks li.ok {
  color: var(--acid);
}

.plan-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 14px;
  margin-bottom: 12px;
}

.plan-heading span {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #d9ff43;
  font-weight: 700;
}

.plan-heading em {
  font-style: normal;
  font-size: 12px;
  color: #8a9690;
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.plan-card {
  position: relative;
  text-align: left;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: #0d1a16;
  color: #e8efe9;
  border-radius: 10px;
  padding: 16px 14px 14px;
  cursor: pointer;
  transition: border-color 0.15s ease, transform 0.15s ease, background 0.15s ease;
  font: inherit;
}

.plan-card:hover {
  border-color: rgba(217, 255, 67, 0.45);
  transform: translateY(-1px);
}

.plan-card.recommended {
  background: #07100e;
  border-color: rgba(217, 255, 67, 0.35);
}

.plan-card.selected {
  border-color: #d9ff43;
  box-shadow: 0 0 0 1px rgba(217, 255, 67, 0.35);
}

.plan-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  font-size: 9px;
  font-family: var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: #d9ff43;
  color: #07100e;
  font-weight: 800;
  padding: 3px 6px;
  border-radius: 3px;
}

.plan-name {
  font-weight: 800;
  font-size: 15px;
  margin-bottom: 6px;
  letter-spacing: -0.02em;
}

.plan-price {
  margin-bottom: 8px;
}

.plan-price strong {
  font-size: 22px;
  letter-spacing: -0.03em;
}

.plan-price span {
  color: #8a9690;
  font-size: 12px;
  margin-left: 2px;
}

.plan-blurb {
  color: #9aa69f;
  font-size: 12px;
  line-height: 1.45;
  min-height: 52px;
  margin: 0 0 10px;
}

.plan-card ul {
  list-style: none;
  padding: 0;
  margin: 0 0 12px;
}

.plan-card li {
  position: relative;
  padding-left: 14px;
  font-size: 11.5px;
  color: #c5d0c9;
  margin-bottom: 6px;
  line-height: 1.35;
}

.plan-card li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.45em;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #48ab87;
}

.plan-cta {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  text-align: center;
  padding: 8px 6px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 6px;
  color: #d9ff43;
}

.plan-card.recommended .plan-cta,
.plan-card.selected .plan-cta {
  background: #d9ff43;
  color: #07100e;
  border-color: #d9ff43;
}

a {
  color: var(--acid);
  text-decoration: none;
  font-weight: 700;
  font-family: var(--font-mono);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .plan-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .auth-page {
    grid-template-columns: 1fr;
  }

  .auth-visual {
    min-height: 180px;
    padding: 28px 22px;
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
}

@media (max-width: 640px) {
  .plan-grid {
    grid-template-columns: 1fr;
  }
}
</style>
