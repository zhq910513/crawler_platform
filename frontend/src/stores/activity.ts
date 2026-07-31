import { updateSessionActivity } from '../api/sessions'
import { sessionState } from './session'

let lastLocalMark = 0
let lastRemoteTouch = 0

export function markUserActive() {
  const now = Date.now()
  if (now - lastLocalMark > 5000) {
    localStorage.setItem('userActiveFlag', '1')
    lastLocalMark = now
  }
  if (sessionState.sessionId && now - lastRemoteTouch > 60000) {
    lastRemoteTouch = now
    void updateSessionActivity(sessionState.sessionId).catch(() => undefined)
  }
}

export function installActivityTracker() {
  const events = ['click', 'keydown', 'mousemove', 'scroll'] as const
  events.forEach((eventName) => window.addEventListener(eventName, markUserActive, { passive: true }))
}
