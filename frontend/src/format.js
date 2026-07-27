const PLATFORM_TIMEZONE = import.meta.env.VITE_TIMEZONE || 'Asia/Shanghai'

export function formatDate(value) {
  if (!value) return '-'
  const text = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false, timeZone: PLATFORM_TIMEZONE })
}
