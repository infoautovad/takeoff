import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as authApi from '@/api/auth'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('cm_token'))
  const user = ref<User | null>(localStorage.getItem('cm_user') ? JSON.parse(localStorage.getItem('cm_user')!) : null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => Boolean(token.value))

  function persist(authToken: string, authUser: User) {
    token.value = authToken
    user.value = authUser
    localStorage.setItem('cm_token', authToken)
    localStorage.setItem('cm_user', JSON.stringify(authUser))
  }

  async function login(email: string, password: string) {
    loading.value = true
    error.value = null
    try {
      const data = await authApi.loginUser(email, password)
      persist(data.access_token, data.user)
      return data.user
    } catch (err: unknown) {
      error.value = extractError(err, 'Login failed')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function register(payload: {
    email: string
    full_name: string
    password: string
    confirm_password: string
    role: string
    plan: string
  }) {
    loading.value = true
    error.value = null
    try {
      const data = await authApi.registerUser(payload)
      persist(data.access_token, data.user)
      return data.user
    } catch (err: unknown) {
      error.value = extractError(err, 'Registration failed')
      throw err
    } finally {
      loading.value = false
    }
  }

  async function refreshMe() {
    if (!token.value) return null
    const me = await authApi.fetchMe()
    user.value = me
    localStorage.setItem('cm_user', JSON.stringify(me))
    return me
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('cm_token')
    localStorage.removeItem('cm_user')
  }

  return { token, user, loading, error, isAuthenticated, login, register, refreshMe, logout }
})

function extractError(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err && 'response' in err) {
    const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => {
          if (typeof d === 'string') return d
          if (d && typeof d === 'object' && 'msg' in d) return String((d as { msg: string }).msg)
          return ''
        })
        .filter(Boolean)
      if (msgs.length) return msgs.join(' ')
    }
  }
  return fallback
}
