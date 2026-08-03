import axios from 'axios'
import type { ApiResponse, BackendHealthData, SystemVersionInfo } from '../types/api'
import { frontendBuildVersion } from '../config/version'

export async function getFrontendVersion(): Promise<SystemVersionInfo> {
  try {
    const response = await axios.get<SystemVersionInfo>('/version.json', { timeout: 5000, headers: { 'Cache-Control': 'no-cache' } })
    return { ...frontendBuildVersion, ...response.data }
  } catch {
    return frontendBuildVersion
  }
}

export async function getBackendHealth(): Promise<BackendHealthData> {
  const response = await axios.get<ApiResponse<BackendHealthData>>('/health', { timeout: 5000 })
  const payload = response.data
  if (!payload || payload.code !== 200) throw new Error(payload?.message || '后端健康检查失败')
  return payload.data
}
