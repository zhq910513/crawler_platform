import { http, request } from './client'
import type { LoginRequest, LoginResponse } from '../types/api'

export function createSession(payload: LoginRequest) {
  return request<LoginResponse>(http.post('/sessions', payload))
}

export function getSession(sessionId: string) {
  return request(http.get(`/sessions/${sessionId}`))
}

export function updateSessionActivity(sessionId: string) {
  return request(http.patch(`/sessions/${sessionId}`, { active: true }))
}

export function deleteSession(sessionId: string) {
  return request(http.delete(`/sessions/${sessionId}`))
}
