import type { SubscriptionPlan } from '@/types'

/** Monthly AI credit allowance by plan (matches pricing copy). */
export const PLAN_CREDIT_ALLOWANCE: Record<SubscriptionPlan, number> = {
  starter: 100,
  professional: 500,
  business: 2000,
  enterprise: 10000,
}

export function planCreditAllowance(plan?: SubscriptionPlan | string | null): number {
  if (!plan) return 0
  return PLAN_CREDIT_ALLOWANCE[plan as SubscriptionPlan] ?? 0
}

/** Remaining credits until usage is tracked server-side (full allowance). */
export function creditsRemaining(plan?: SubscriptionPlan | string | null, used = 0): number {
  return Math.max(0, planCreditAllowance(plan) - Math.max(0, used))
}

export function creditsRemainingPct(plan?: SubscriptionPlan | string | null, used = 0): number {
  const total = planCreditAllowance(plan)
  if (total <= 0) return 0
  return Math.round((creditsRemaining(plan, used) / total) * 100)
}
