<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const fullName = ref('')
const email = ref('')
const password = ref('')
const role = ref('design_engineer')
const showPassword = ref(false)

const roles = [
  { title: 'Design Engineer', value: 'design_engineer' },
  { title: 'Quantity Surveyor', value: 'quantity_surveyor' },
  { title: 'Project Manager', value: 'project_manager' },
  { title: 'Reviewer', value: 'reviewer' },
  { title: 'Client / Viewer', value: 'client' },
  { title: 'Admin', value: 'admin' },
]

async function submit() {
  await auth.register({
    email: email.value.trim(),
    full_name: fullName.value.trim(),
    password: password.value,
    role: role.value,
  })
  router.push('/dashboard')
}
</script>

<template>
  <div class="auth-page cm-grid-bg">
    <div class="auth-visual">
      <div>
        <div class="page-kicker">AutoVAD / Join</div>
        <div class="brand-font auth-title mb-4">
          Join Auto<span>VAD</span>
        </div>
        <p class="auth-lede">
          Build projects, upload USA road plans, and prepare for AI-powered quantity takeoff and BOQ generation.
        </p>
      </div>
    </div>

    <div class="auth-form-wrap">
      <div class="auth-form surface-panel pa-8">
        <div class="page-kicker">Create account</div>
        <h1 class="brand-font text-h4 mb-1">Get started</h1>
        <p class="muted mb-6">Set up your civil takeoff workspace</p>

        <v-alert v-if="auth.error" type="error" variant="tonal" class="mb-4">{{ auth.error }}</v-alert>

        <v-form @submit.prevent="submit">
          <v-text-field v-model="fullName" label="Full name" class="mb-2" required />
          <v-text-field v-model="email" label="Email" type="email" class="mb-2" required />
          <v-select v-model="role" :items="roles" label="Role" class="mb-2" />
          <v-text-field
            v-model="password"
            label="Password (min 8 characters)"
            :type="showPassword ? 'text' : 'password'"
            :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
            class="mb-4"
            required
            @click:append-inner="showPassword = !showPassword"
          />
          <v-btn type="submit" color="primary" size="large" block :loading="auth.loading">
            Create account
          </v-btn>
        </v-form>

        <div class="text-center mt-6">
          <span class="muted">Already have an account?</span>
          <router-link to="/login" class="ml-1">Sign in</router-link>
        </div>
        <div class="text-center mt-3">
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
  grid-template-columns: 1.1fr 1fr;
}

.auth-visual {
  position: relative;
  color: #fff;
  display: flex;
  align-items: center;
  padding: 48px 4.5vw;
  border-right: 1px solid var(--line);
  background:
    radial-gradient(circle at 75% 40%, rgba(72, 171, 135, 0.16), transparent 32%),
    #07100e;
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
  padding: 32px;
  background: #0a1411;
}

.auth-form {
  width: 100%;
  max-width: 460px;
  border-color: rgba(217, 255, 67, 0.22);
  box-shadow: 0 25px 70px rgba(0, 0, 0, 0.35);
}

a {
  color: var(--acid);
  text-decoration: none;
  font-weight: 700;
  font-family: var(--font-mono);
  font-size: 12px;
}

@media (max-width: 960px) {
  .auth-page {
    grid-template-columns: 1fr;
  }

  .auth-visual {
    min-height: 220px;
    padding: 32px 24px;
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
}
</style>
