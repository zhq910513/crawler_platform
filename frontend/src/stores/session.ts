import { reactive } from 'vue'
import type { UserInfo } from '../types/api'

interface SessionState {
  token: string
  sessionId: string
  user: UserInfo | null
}

export const sessionState = reactive<SessionState>({
  token: localStorage.getItem('accessToken') || '',
  sessionId: localStorage.getItem('sessionId') || '',
  user: localStorage.getItem('userInfo') ? JSON.parse(localStorage.getItem('userInfo') as string) as UserInfo : null,
})

const PASSWORD_CHANGE_RELOGIN_MARKER = 'passwordChangeReloginInProgress'

export function markPasswordChangeReloginInProgress() {
  localStorage.setItem(PASSWORD_CHANGE_RELOGIN_MARKER, '1')
}

export function isPasswordChangeReloginInProgress() {
  return localStorage.getItem(PASSWORD_CHANGE_RELOGIN_MARKER) === '1'
}

export function clearPasswordChangeReloginInProgress() {
  localStorage.removeItem(PASSWORD_CHANGE_RELOGIN_MARKER)
}

export function setSession(token: string, sessionId: string, user: UserInfo) {
  clearPasswordChangeReloginInProgress()
  sessionState.token = token
  sessionState.sessionId = sessionId
  sessionState.user = user
  localStorage.setItem('accessToken', token)
  localStorage.setItem('sessionId', sessionId)
  localStorage.setItem('userInfo', JSON.stringify(user))
}

export function clearSession() {
  sessionState.token = ''
  sessionState.sessionId = ''
  sessionState.user = null
  localStorage.removeItem('accessToken')
  localStorage.removeItem('sessionId')
  localStorage.removeItem('userInfo')
}
