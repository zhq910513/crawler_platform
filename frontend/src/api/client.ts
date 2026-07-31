import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import type { ApiResponse } from '../types/api'

const http = axios.create({ baseURL: '/api/v1', timeout: 30000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken')
  if (token) config.headers.Authorization = `Bearer ${token}`
  if (localStorage.getItem('userActiveFlag') === '1') {
    config.headers['X-User-Active'] = '1'
    localStorage.removeItem('userActiveFlag')
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiResponse<unknown>>) => {
    const payload = error.response?.data
    if (error.response?.status === 401) {
      const message = payload?.message || '登录已失效，请重新登录'
      localStorage.removeItem('accessToken')
      localStorage.removeItem('sessionId')
      localStorage.removeItem('userInfo')
      ElMessage.error(message)
      void router.push('/login')
    }
    return Promise.reject(error)
  },
)

export async function request<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const response = await promise
  const body = response.data
  if (body.code !== 200) throw new Error(body.message)
  return body.data
}

export { http }

export function apiErrorData<T>(error: unknown): ApiResponse<T> | undefined {
  const candidate = error as { response?: { data?: ApiResponse<T> } }
  return candidate.response?.data
}
