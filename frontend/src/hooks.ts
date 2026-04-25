import { useEffect, useState } from 'react'
import { apiClient, handleApiError } from './api'
import { API_ENDPOINTS } from './constants'
import { toast } from 'react-toastify'
import { getStoredAuthSession, setStoredAuthSession } from './auth'
import type {
  AppConfig,
  Asset,
  AuthSession,
  ChatFinalizeResponse,
  ChatMessage,
  ChatResponse,
  LoginResponse,
  Note,
  ResetPasswordResponse,
  SecretQuestion,
} from './types'
import { UI_TEXT, getStoredLang } from './i18n'

const ui = () => UI_TEXT[getStoredLang()]
const CHAT_CACHE_TTL_MS = 5 * 60 * 1000
const CHAT_CACHE_STORAGE_PREFIX = 'zhyto_chat_cache_'

const getDefaultUserId = (): string => getStoredAuthSession()?.userId ?? ''

type PersistedChatPayload = {
  savedAt: number
  messages: ChatMessage[]
}

const getChatStorageKey = (userId: string): string => `${CHAT_CACHE_STORAGE_PREFIX}${userId || 'anonymous'}`

const isValidChatMessage = (value: unknown): value is ChatMessage => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const candidate = value as Partial<ChatMessage>
  return (
    (candidate.role === 'user' || candidate.role === 'assistant')
    && typeof candidate.content === 'string'
  )
}

const readPersistedChatMessages = (userId: string): ChatMessage[] => {
  if (typeof window === 'undefined') {
    return []
  }
  const key = getChatStorageKey(userId)
  const raw = window.localStorage.getItem(key)
  if (!raw) {
    return []
  }

  try {
    const parsed = JSON.parse(raw) as Partial<PersistedChatPayload>
    const savedAt = Number(parsed.savedAt)
    const rawMessages = Array.isArray(parsed.messages) ? parsed.messages : []
    if (!Number.isFinite(savedAt) || Date.now() - savedAt > CHAT_CACHE_TTL_MS) {
      window.localStorage.removeItem(key)
      return []
    }
    return rawMessages.filter(isValidChatMessage)
  } catch {
    window.localStorage.removeItem(key)
    return []
  }
}

const persistChatMessages = (userId: string, messages: ChatMessage[]) => {
  if (typeof window === 'undefined') {
    return
  }
  const key = getChatStorageKey(userId)
  if (!messages.length) {
    window.localStorage.removeItem(key)
    return
  }
  const payload: PersistedChatPayload = {
    savedAt: Date.now(),
    messages,
  }
  window.localStorage.setItem(key, JSON.stringify(payload))
}

export const useAuth = () => {
  const [session, setSession] = useState<AuthSession | null>(() => getStoredAuthSession())
  const [loading, setLoading] = useState(false)

  const login = async (email: string, password: string) => {
    try {
      setLoading(true)
      const response = await apiClient.post<LoginResponse>(API_ENDPOINTS.AUTH_LOGIN, {
        email,
        password,
      })
      const nextSession: AuthSession = {
        email: response.data.user.email,
        userId: response.data.user.user_id,
        accessToken: response.data.access_token,
      }
      setStoredAuthSession(nextSession)
      setSession(nextSession)
      toast.success(ui().toastLoginSuccess)
      return true
    } catch (error) {
      toast.error(handleApiError(error))
      return false
    } finally {
      setLoading(false)
    }
  }

  const register = async (
    email: string,
    password: string,
    confirmPassword: string,
    secretQuestionId: string,
    secretAnswer: string,
  ) => {
    try {
      setLoading(true)
      const response = await apiClient.post<LoginResponse>(API_ENDPOINTS.AUTH_REGISTER, {
        email,
        password,
        confirm_password: confirmPassword,
        secret_question_id: secretQuestionId,
        secret_answer: secretAnswer,
      })
      const nextSession: AuthSession = {
        email: response.data.user.email,
        userId: response.data.user.user_id,
        accessToken: response.data.access_token,
      }
      setStoredAuthSession(nextSession)
      setSession(nextSession)
      toast.success(ui().toastRegisterSuccess)
      return true
    } catch (error) {
      toast.error(handleApiError(error))
      return false
    } finally {
      setLoading(false)
    }
  }

  const fetchSecretQuestions = async (): Promise<SecretQuestion[]> => {
    try {
      const response = await apiClient.get<SecretQuestion[]>(API_ENDPOINTS.AUTH_SECRET_QUESTIONS)
      return Array.isArray(response.data) ? response.data : []
    } catch (error) {
      toast.error(handleApiError(error))
      return []
    }
  }

  const resetPassword = async (
    email: string,
    secretQuestionId: string,
    secretAnswer: string,
    newPassword: string,
    confirmPassword: string,
  ): Promise<boolean> => {
    try {
      setLoading(true)
      const response = await apiClient.post<ResetPasswordResponse>(API_ENDPOINTS.AUTH_RESET_PASSWORD, {
        email,
        secret_question_id: secretQuestionId,
        secret_answer: secretAnswer,
        new_password: newPassword,
        confirm_password: confirmPassword,
      })
      if (response.data?.message) {
        toast.success(response.data.message)
      }
      return true
    } catch (error) {
      toast.error(handleApiError(error))
      return false
    } finally {
      setLoading(false)
    }
  }

  const logout = () => {
    setStoredAuthSession(null)
    setSession(null)
    toast.success(ui().toastLogoutSuccess)
  }

  return {
    session,
    loading,
    isAuthenticated: Boolean(session?.accessToken),
    login,
    register,
    fetchSecretQuestions,
    resetPassword,
    logout,
  }
}

export const useAppConfig = () => {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(false)

  const fetchConfig = async () => {
    try {
      setLoading(true)
      const response = await apiClient.get<AppConfig>(API_ENDPOINTS.CONFIG_APP)
      setConfig(response.data)
    } catch (error) {
      toast.error(`${ui().toastConfigFailed}: ${handleApiError(error)}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  return { config, loading, refetch: fetchConfig }
}

export const usePortfolio = () => {
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)

  const fetchPortfolio = async (userId: string = getDefaultUserId()) => {
    try {
      setLoading(true)
      const response = await apiClient.get<{ assets: Asset[] }>(API_ENDPOINTS.PORTFOLIO_GET, {
        params: { user_id: userId },
      })
      setAssets(response.data.assets)
    } catch (error) {
      toast.error(handleApiError(error))
    } finally {
      setLoading(false)
    }
  }

  const addAsset = async (asset: Omit<Asset, 'id' | 'created_at'>) => {
    try {
      setLoading(true)
      const response = await apiClient.post<Asset>(API_ENDPOINTS.PORTFOLIO_ADD, asset)
      setAssets((previous) => [response.data, ...previous])
      toast.success(ui().toastAssetAdded)
      return true
    } catch (error) {
      toast.error(handleApiError(error))
      return false
    } finally {
      setLoading(false)
    }
  }

  const deleteAsset = async (assetId: string, userId: string = getDefaultUserId()) => {
    try {
      setLoading(true)
      await apiClient.delete(API_ENDPOINTS.PORTFOLIO_DELETE(assetId), {
        params: { user_id: userId },
      })
      setAssets((previous) => previous.filter((asset) => asset.id !== assetId))
      toast.success(ui().toastAssetDeleted)
      return true
    } catch (error) {
      toast.error(handleApiError(error))
      return false
    } finally {
      setLoading(false)
    }
  }

  const updateManualCurrentPrice = async (
    assetId: string,
    manualCurrentPrice: number | null,
    userId: string = getDefaultUserId(),
  ) => {
    try {
      setLoading(true)
      const response = await apiClient.patch<Asset>(
        API_ENDPOINTS.PORTFOLIO_MANUAL_PRICE(assetId),
        { manual_current_price: manualCurrentPrice },
        { params: { user_id: userId } },
      )
      setAssets((previous) => previous.map((asset) => (
        asset.id === assetId ? response.data : asset
      )))
      toast.success(manualCurrentPrice === null ? ui().toastManualPriceCleared : ui().toastManualPriceUpdated)
      return true
    } catch (error) {
      toast.error(handleApiError(error))
      return false
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const onPortfolioAssetAdded = (event: Event) => {
      const asset = (event as CustomEvent<Asset>).detail
      if (!asset?.id) {
        return
      }
      setAssets((previous) => (
        previous.some((item) => item.id === asset.id) ? previous : [asset, ...previous]
      ))
    }

    window.addEventListener('portfolio:add', onPortfolioAssetAdded as EventListener)
    return () => {
      window.removeEventListener('portfolio:add', onPortfolioAssetAdded as EventListener)
    }
  }, [])

  return { assets, loading, fetchPortfolio, addAsset, deleteAsset, updateManualCurrentPrice }
}

export const useNotes = () => {
  const [notes, setNotes] = useState<Note[]>([])
  const [loading, setLoading] = useState(false)

  const fetchNotes = async (userId: string = getDefaultUserId()) => {
    try {
      setLoading(true)
      const response = await apiClient.get<{ notes: Note[] }>(API_ENDPOINTS.NOTES_GET, {
        params: { user_id: userId },
      })
      setNotes(response.data.notes)
    } catch (error) {
      toast.error(handleApiError(error))
    } finally {
      setLoading(false)
    }
  }

  const addNote = async (content: string, userId: string = getDefaultUserId()) => {
    try {
      setLoading(true)
      const response = await apiClient.post<Note>(API_ENDPOINTS.NOTES_ADD, { user_id: userId, content })
      setNotes((previous) => [response.data, ...previous])
      toast.success(ui().toastNoteSaved)
      return true
    } catch (error) {
      toast.error(handleApiError(error))
      return false
    } finally {
      setLoading(false)
    }
  }

  const deleteNote = async (noteId: string, userId: string = getDefaultUserId()) => {
    try {
      setLoading(true)
      await apiClient.delete(API_ENDPOINTS.NOTES_DELETE(noteId), {
        params: { user_id: userId },
      })
      setNotes((previous) => previous.filter((note) => note.id !== noteId))
      toast.success(ui().toastNoteDeleted)
      return true
    } catch (error) {
      toast.error(handleApiError(error))
      return false
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const onNoteAdded = (event: Event) => {
      const note = (event as CustomEvent<Note>).detail
      if (!note?.id) {
        return
      }
      setNotes((previous) => (
        previous.some((item) => item.id === note.id) ? previous : [note, ...previous]
      ))
    }

    window.addEventListener('notes:add', onNoteAdded as EventListener)
    return () => {
      window.removeEventListener('notes:add', onNoteAdded as EventListener)
    }
  }, [])

  return { notes, loading, fetchNotes, addNote, deleteNote }
}

export const useChat = () => {
  const authUserId = getDefaultUserId()
  const [messages, setMessages] = useState<ChatMessage[]>(() => readPersistedChatMessages(getDefaultUserId()))
  const [loading, setLoading] = useState(false)
  const [savingSummary, setSavingSummary] = useState(false)

  useEffect(() => {
    setMessages(readPersistedChatMessages(authUserId))
  }, [authUserId])

  useEffect(() => {
    persistChatMessages(authUserId, messages)
  }, [authUserId, messages])

  const sendMessage = async (message: string, userId: string = getDefaultUserId()) => {
    const userMessage: ChatMessage = { role: 'user', content: message }

    try {
      setLoading(true)
      setMessages((previous) => [...previous, userMessage])

      const history = [...messages, userMessage].map((item) => ({
        role: item.role,
        content: item.content,
        sources: item.sources ?? [],
        pending_transaction_draft: item.pending_transaction_draft,
        draft_status: item.draft_status,
      }))

      const response = await apiClient.post<ChatResponse>(API_ENDPOINTS.CHAT_SEND, {
        message,
        user_id: userId,
        history,
      })

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.data.message,
        sources: response.data.sources,
        pending_transaction_draft: response.data.pending_transaction_draft,
        draft_status: response.data.pending_transaction_draft ? 'pending' : undefined,
      }

      setMessages((prev) => [...prev, assistantMessage])
      return assistantMessage
    } catch (error) {
      toast.error(handleApiError(error))
      return null
    } finally {
      setLoading(false)
    }
  }

  const cancelTransactionDraft = (messageIndex: number) => {
    setMessages((previous) => previous.map((item, index) => {
      if (index !== messageIndex || !item.pending_transaction_draft) {
        return item
      }
      return {
        ...item,
        draft_status: 'cancelled',
      }
    }))
  }

  const confirmTransactionDraft = async (
    messageIndex: number,
    userId: string = getDefaultUserId(),
  ) => {
    const currentMessage = messages[messageIndex]
    const draft = currentMessage?.pending_transaction_draft
    if (!draft) {
      return false
    }
    if (currentMessage?.draft_status === 'added' || currentMessage?.draft_status === 'submitting') {
      return true
    }

    try {
      setMessages((previous) => previous.map((item, index) => (
        index === messageIndex ? { ...item, draft_status: 'submitting' } : item
      )))
      const payload = {
        asset_type: draft.asset_type,
        amount: draft.amount,
        currency: draft.currency,
        purchase_price: draft.purchase_price,
        purchase_date: draft.purchase_date,
        ticker: draft.ticker,
        notes: draft.notes,
      }
      const response = await apiClient.post<Asset>(
        API_ENDPOINTS.PORTFOLIO_ADD,
        payload,
        { params: { user_id: userId } },
      )
      window.dispatchEvent(new CustomEvent<Asset>('portfolio:add', { detail: response.data }))
      setMessages((previous) => previous.map((item, index) => (
        index === messageIndex ? { ...item, draft_status: 'added' } : item
      )))
      toast.success('Додано успішно')
      return true
    } catch (error) {
      setMessages((previous) => previous.map((item, index) => (
        index === messageIndex ? { ...item, draft_status: 'failed' } : item
      )))
      toast.error(handleApiError(error))
      return false
    }
  }

  const finalizeChat = async (userId: string = getDefaultUserId()) => {
    const hasUserMessages = messages.some((item) => item.role === 'user')
    if (!hasUserMessages) {
      toast.error(ui().chatNoMessagesToSave)
      return null
    }

    try {
      setSavingSummary(true)
      const history = messages.map((item) => ({
        role: item.role,
        content: item.content,
        sources: item.sources ?? [],
        pending_transaction_draft: item.pending_transaction_draft,
        draft_status: item.draft_status,
      }))

      const response = await apiClient.post<ChatFinalizeResponse>(API_ENDPOINTS.CHAT_FINALIZE, {
        user_id: userId,
        history,
        language: getStoredLang(),
      })

      window.dispatchEvent(new CustomEvent<Note>('notes:add', { detail: response.data.note }))
      setMessages([])
      toast.success(ui().toastChatSummarySaved)
      return response.data
    } catch (error) {
      toast.error(handleApiError(error))
      return null
    } finally {
      setSavingSummary(false)
    }
  }

  const restartChat = () => {
    setMessages([])
  }

  return {
    messages,
    loading,
    savingSummary,
    sendMessage,
    finalizeChat,
    restartChat,
    confirmTransactionDraft,
    cancelTransactionDraft,
  }
}
