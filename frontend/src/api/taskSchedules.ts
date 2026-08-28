import { http, request } from './client'
import type { TaskSchedulePanelQuery, TaskSchedulePanelResult } from '../types/api'

export function listTaskSchedulePanels(params: TaskSchedulePanelQuery = {}) {
  return request<TaskSchedulePanelResult>(http.get('/task-schedule-panels', { params }))
}
