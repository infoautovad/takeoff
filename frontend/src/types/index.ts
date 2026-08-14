export type UserRole =
  | 'admin'
  | 'project_manager'
  | 'design_engineer'
  | 'quantity_surveyor'
  | 'reviewer'
  | 'client'
  | 'other'

export type SubscriptionPlan = 'starter' | 'professional' | 'business' | 'enterprise'

export type ProjectStatus = 'draft' | 'active' | 'in_review' | 'approved' | 'archived'

export type ProcessingStatus = 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed'

export interface User {
  id: number
  email: string
  full_name: string
  role: UserRole
  plan: SubscriptionPlan
  is_active: boolean
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface Project {
  id: number
  name: string
  description: string | null
  location: string | null
  client_name: string | null
  country: string
  state: string | null
  status: ProjectStatus
  owner_id: number
  created_at: string
  updated_at: string
  document_count: number
  boq_count?: number
}

export interface DocumentItem {
  id: number
  project_id: number
  uploaded_by: number
  original_filename: string
  content_type: string
  file_size: number
  document_type: string
  processing_status: ProcessingStatus
  page_count: number | null
  revision_label: string | null
  notes: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface DashboardStats {
  total_projects: number
  active_projects: number
  documents_uploaded: number
  boqs_generated: number
  pending_reviews: number
  recent_activity: Array<{
    id: number
    action: string
    message: string
    project_id: number | null
    created_at: string
  }>
  needs_attention?: Array<{
    kind: string
    severity: string
    title: string
    detail: string
    project_id: number
    project_name: string
    entity_id?: number | null
    action_label: string
  }>
  week?: {
    documents_uploaded: number
    boqs_generated: number
    projects_touched: number
    failed_uploads: number
  }
}

export interface AnalyticsMaterial {
  name: string
  quantity: number
  unit?: string
  share?: number
}

export interface AnalyticsCategory {
  name: string
  quantity: number
  share?: number
}

export interface AnalyticsCostByProject {
  project_id: number
  name: string
  amount: number
}

export interface AnalyticsSnapshot {
  materials: AnalyticsMaterial[]
  categories: AnalyticsCategory[]
  earthwork: {
    cut: number
    fill: number
    balance: number
    balance_label: string
  }
  costs: {
    total_estimated: number
    by_project: AnalyticsCostByProject[]
  }
  pavement: Record<string, number>
  meta: {
    boq_count: number
    estimate_count: number
    project_count: number
    item_count: number
    last_updated: string | null
    has_boqs: boolean
    has_estimates: boolean
    range?: string
  }
  filters?: {
    project_id: number | null
    status: string | null
    range: string
  }
  compare?: {
    a: AnalyticsSnapshot & { project_id: number; name: string }
    b: AnalyticsSnapshot & { project_id: number; name: string }
    delta: {
      cost: number
      cut: number
      fill: number
      materials: Array<{ name: string; a: number; b: number; delta: number }>
    }
  } | null
}

export interface AnalyticsParams {
  project_id?: number
  status?: string
  range?: '7d' | '30d' | 'all'
  compare_a?: number
  compare_b?: number
}

export interface ProjectPayload {
  name: string
  description?: string
  location?: string
  client_name?: string
  country?: string
  state?: string
  status?: ProjectStatus
}

export interface AnalysisResult {
  id: number
  document_id: number
  project_id: number
  engine: string
  summary: string | null
  findings: {
    facts?: Array<Record<string, unknown>>
    items?: Array<Record<string, unknown>>
    needs_review?: boolean
  }
  created_at: string
  updated_at: string
}

export interface ProcessResult {
  document_id: number
  status: string
  analysis: AnalysisResult | null
  error: string | null
}

export interface BOQItem {
  id: number
  boq_id: number
  item_number: string
  item_code: string | null
  csi_code?: string | null
  description: string
  category: string | null
  unit: string
  quantity: number | string
  rate: number | string | null
  amount: number | string | null
  source_document_id: number | null
  source_page: number | null
  source_reference: string | null
  calculation_method: string | null
  confidence: number | string | null
  bid_template_line_id?: number | null
  bid_match_confidence?: number | string | null
  status: string
  created_at: string
  updated_at: string
}

export interface BOQ {
  id: number
  project_id: number
  title: string
  version: number
  status: string
  currency: string
  notes: string | null
  created_by: number
  created_at: string
  updated_at: string
  items: BOQItem[]
}

export interface ChatMessage {
  id: number
  project_id: number
  user_id: number
  role: 'user' | 'assistant' | string
  content: string
  sources: Array<Record<string, unknown>>
  created_at: string
}
