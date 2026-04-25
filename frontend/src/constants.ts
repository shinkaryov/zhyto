export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const API_ENDPOINTS = {
  AUTH_LOGIN: '/auth/login',
  AUTH_REGISTER: '/auth/register',
  AUTH_SECRET_QUESTIONS: '/auth/secret-questions',
  AUTH_RESET_PASSWORD: '/auth/reset-password',
  AUTH_ME: '/auth/me',
  HEALTH: '/health',
  CONFIG_COLORS: '/config/colors',
  CONFIG_APP: '/config/app',
  CHAT_SEND: '/chat/send',
  CHAT_FINALIZE: '/chat/finalize',
  PORTFOLIO_GET: '/portfolio',
  PORTFOLIO_ADD: '/portfolio',
  PORTFOLIO_MANUAL_PRICE: (id: string) => `/portfolio/${id}/manual-price`,
  PORTFOLIO_DELETE: (id: string) => `/portfolio/${id}`,
  NOTES_GET: '/notes',
  NOTES_ADD: '/notes',
  NOTES_DELETE: (id: string) => `/notes/${id}`,
}

export type PageType = 'home' | 'chat' | 'portfolio' | 'notes' | 'about'

export const PAGE_PATHS: Record<PageType, string> = {
  home: '/',
  chat: '/chat',
  portfolio: '/portfolio',
  notes: '/notes',
  about: '/about',
}

const PATH_PAGE_MAP: Record<string, PageType> = {
  '/': 'home',
  '/home': 'home',
  '/chat': 'chat',
  '/portfolio': 'portfolio',
  '/notes': 'notes',
  '/about': 'about',
}

const normalizePathname = (pathname: string): string => {
  if (!pathname) {
    return '/'
  }
  if (pathname.length > 1 && pathname.endsWith('/')) {
    return pathname.slice(0, -1)
  }
  return pathname
}

export const pageFromPathname = (pathname: string): PageType => {
  const normalized = normalizePathname(pathname)
  return PATH_PAGE_MAP[normalized] ?? 'home'
}

export const pathnameForPage = (page: PageType): string => PAGE_PATHS[page] ?? '/'
