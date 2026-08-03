import type { SystemVersionInfo } from '../types/api'

function envValue(value: unknown, fallback = 'unknown'): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

export const frontendBuildVersion: SystemVersionInfo = {
  appName: 'crawler_platform_web',
  version: envValue(import.meta.env.VITE_APP_VERSION),
  gitCommit: envValue(import.meta.env.VITE_APP_GIT_COMMIT),
  buildTime: envValue(import.meta.env.VITE_APP_BUILD_TIME),
}
