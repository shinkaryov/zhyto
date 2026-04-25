export interface Asset {
  id: string
  user_id: string
  asset_type: string
  amount: number
  currency: string
  purchase_price: number
  purchase_date: string
  notes?: string
  ticker?: string
  isin?: string
  maturity_date?: string
  yield_percent?: number
  created_at?: string
  manual_current_price?: number | null
  current_price?: number | null
  purchase_price_uah?: number | null
  purchase_price_usd?: number | null
  purchase_price_eur?: number | null
  current_price_uah?: number | null
  current_price_usd?: number | null
  current_price_eur?: number | null
  invested_value_original_currency?: number | null
  invested_value_uah?: number | null
  invested_value_usd?: number | null
  invested_value_eur?: number | null
  current_value_original_currency?: number | null
  current_value?: number | null
  current_value_uah?: number | null
  current_value_usd?: number | null
  current_value_eur?: number | null
  pnl_value_uah?: number | null
  pnl_value_usd?: number | null
  pnl_value_eur?: number | null
  pnl_percent?: number | null
  pnl_percent_uah?: number | null
  pnl_percent_usd?: number | null
  pnl_percent_eur?: number | null
}

export interface PortfolioTotals {
  uah?: number | null
  usd?: number | null
  eur?: number | null
}

export interface Note {
  id: string
  user_id: string
  content: string
  created_at: string
}

export interface ChatSource {
  index: number
  channel: string
  url: string
  date: string
}

export interface PendingTransactionDraft {
  asset_type: string
  amount: number
  currency: string
  ticker?: string
  purchase_price?: number
  total_value?: number
  purchase_date: string
  notes?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  pending_transaction_draft?: PendingTransactionDraft
  draft_status?: 'pending' | 'submitting' | 'added' | 'cancelled' | 'failed'
}

export interface ChatResponse {
  message: string
  sources: ChatSource[]
  pending_transaction_draft?: PendingTransactionDraft
}

export interface ChatFinalizeResponse {
  summary: string
  note: Note
}

export interface AuthUser {
  email: string
  user_id: string
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer' | string
  user: AuthUser
}

export interface SecretQuestion {
  id: string
  question: string
}

export interface ResetPasswordResponse {
  success: boolean
  message: string
}

export interface AuthSession {
  email: string
  userId: string
  accessToken: string
}

export interface AppFeature {
  title: string
  text: string
}

export interface AppConfig {
  asset_types: string[]
  currencies: string[]
  home: {
    title: string
    subtitle: string
    features: AppFeature[]
  }
  about: {
    description: string
    version: string
    status: string
    contact_email: string
  }
}
