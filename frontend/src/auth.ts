import type { AuthSession } from './types'

const AUTH_STORAGE_KEY = 'zhyto_auth_session'

export const getStoredAuthSession = (): AuthSession | null => {
  if (typeof window === 'undefined') {
    return null
  }
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as Partial<AuthSession>
    if (
      typeof parsed.email === 'string'
      && typeof parsed.userId === 'string'
      && typeof parsed.accessToken === 'string'
      && parsed.email
      && parsed.userId
      && parsed.accessToken
    ) {
      return {
        email: parsed.email,
        userId: parsed.userId,
        accessToken: parsed.accessToken,
      }
    }
  } catch {
    // ignore invalid storage payload and clear below
  }

  window.localStorage.removeItem(AUTH_STORAGE_KEY)
  return null
}

export const setStoredAuthSession = (session: AuthSession | null) => {
  if (typeof window === 'undefined') {
    return
  }
  if (!session) {
    window.localStorage.removeItem(AUTH_STORAGE_KEY)
    return
  }
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
}

export const getStoredAccessToken = (): string | null => getStoredAuthSession()?.accessToken ?? null
