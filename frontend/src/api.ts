import axios from 'axios'
import { getStoredAccessToken } from './auth'
import { API_BASE_URL } from './constants'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const token = getStoredAccessToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const handleApiError = (error: any): string => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (Array.isArray(detail)) {
      const firstItem = detail[0]
      if (typeof firstItem === 'string' && firstItem.trim()) {
        return firstItem
      }
      if (firstItem && typeof firstItem === 'object') {
        const msg = (firstItem as { msg?: unknown }).msg
        if (typeof msg === 'string' && msg.trim()) {
          return msg
        }
      }
    }
    if (detail && typeof detail === 'object') {
      const msg = (detail as { msg?: unknown }).msg
      if (typeof msg === 'string' && msg.trim()) {
        return msg
      }
    }
    return error.message || 'An error occurred'
  }
  return String(error)
}
