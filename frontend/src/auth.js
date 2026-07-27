import { reactive, computed } from 'vue'

const savedUser = localStorage.getItem('crawler_user')
export const authState = reactive({
  token: localStorage.getItem('crawler_token') || '',
  user: savedUser ? JSON.parse(savedUser) : null
})

export const isAdmin = computed(() => authState.user?.role_type === 'SUPER_ADMIN')

export function setAuth(token, user) {
  authState.token = token
  authState.user = user
  localStorage.setItem('crawler_token', token)
  localStorage.setItem('crawler_user', JSON.stringify(user))
}

export function clearAuth() {
  authState.token = ''
  authState.user = null
  localStorage.removeItem('crawler_token')
  localStorage.removeItem('crawler_user')
}
