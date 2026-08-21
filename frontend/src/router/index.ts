import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: () => import('@/views/LandingView.vue'),
      meta: { public: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { guest: true },
    },
    {
      path: '/backend',
      component: () => import('@/layouts/BackendLayout.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        {
          path: '',
          name: 'backend-lab',
          component: () => import('@/views/backend/TrainingPortalView.vue'),
        },
        {
          path: 'cases/:id',
          name: 'backend-case',
          component: () => import('@/views/backend/TrainingCaseView.vue'),
        },
        {
          path: 'cases/:id/analyze',
          name: 'backend-case-analyze',
          component: () => import('@/views/backend/TrainingAnalyzeView.vue'),
        },
        {
          path: 'cases/:id/original',
          name: 'backend-case-original',
          component: () => import('@/views/backend/TrainingOriginalView.vue'),
        },
        {
          path: 'cases/:id/evaluate',
          name: 'backend-case-evaluate',
          component: () => import('@/views/backend/TrainingEvaluateView.vue'),
        },
      ],
    },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
        { path: 'projects', name: 'projects', component: () => import('@/views/ProjectsView.vue') },
        { path: 'projects/:id', name: 'project-detail', component: () => import('@/views/ProjectDetailView.vue') },
        { path: 'viewer/:documentId', name: 'document-viewer', component: () => import('@/views/ViewerView.vue') },
        { path: 'analytics', name: 'analytics', component: () => import('@/views/AnalyticsView.vue') },
        { path: 'search', name: 'search', component: () => import('@/views/SearchView.vue') },
        { path: 'account', name: 'account', component: () => import('@/views/AccountDetailsView.vue') },
        { path: 'account/settings', name: 'account-settings', component: () => import('@/views/AccountSettingsView.vue') },
        { path: 'account/billing', name: 'account-billing', component: () => import('@/views/BillingCreditsView.vue') },
        { path: 'account/notifications', name: 'account-notifications', component: () => import('@/views/AccountNotificationsView.vue') },
        { path: 'admin', name: 'admin', component: () => import('@/views/AdminView.vue') },
      ],
    },
  ],
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  const needsAuth = to.matched.some((r) => r.meta.requiresAuth)
  const needsAdmin = to.matched.some((r) => r.meta.requiresAdmin)
  if (needsAuth && !auth.isAuthenticated) {
    return {
      name: 'landing',
      query: { signin: '1', redirect: to.fullPath },
    }
  }
  if (needsAdmin && auth.user?.role !== 'admin') {
    return { name: 'landing' }
  }
  if (to.meta.guest && auth.isAuthenticated) {
    return { name: 'landing' }
  }
  return true
})

export default router
