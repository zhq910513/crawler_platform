import axios from 'axios'
import { authState, clearAuth } from './auth'

const api = axios.create({ baseURL: '/api', timeout: 30000 })
api.interceptors.request.use((config) => {
  if (authState.token) config.headers.Authorization = `Bearer ${authState.token}`
  return config
})
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login')) {
      clearAuth(); window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export async function streamSSE(path, { signal, onEvent, onOpen, onError } = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${authState.token}`, Accept: 'text/event-stream' },
    signal
  })
  if (!response.ok) throw new Error(`SSE HTTP ${response.status}`)
  onOpen?.()
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })
    let index
    while ((index = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, index); buffer = buffer.slice(index + 2)
      if (!block || block.startsWith(':')) continue
      let event = 'message', id = null, data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('id:')) id = line.slice(3).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      try { onEvent?.({ event, id, data: data ? JSON.parse(data) : null }) }
      catch (error) { onError?.(error) }
    }
  }
}

export default api
