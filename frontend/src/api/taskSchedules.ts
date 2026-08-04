import { http, request } from './client'
import type { PageResult, TaskSchedulePanelItem, TaskSchedulePanelQuery } from '../types/api'

export function listTaskSchedulePanels(params: TaskSchedulePanelQuery = {}) {
  return request<PageResult<TaskSchedulePanelItem>>(http.get('/task-schedule-panels', { params }))
}
