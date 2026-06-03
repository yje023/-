import http from './index'

export function getTasks(params) { return http.get('/tasks', { params }) }
export function getTask(id) { return http.get(`/tasks/${id}`) }
export function getTaskFilterOptions(planId, currentFilters) {
  return http.get('/tasks/filter-options', {
    params: { plan_id: planId, current_filters: JSON.stringify(currentFilters || {}) },
  })
}
export function createTask(data) { return http.post('/tasks', data) }
export function updateTask(id, data) { return http.put(`/tasks/${id}`, data) }
export function deleteTask(id) { return http.delete(`/tasks/${id}`) }
export function batchDeleteTasks(ids) { return http.post('/tasks/batch-delete', { ids }) }
export function batchDeleteAllTasks(planId) { return http.delete('/tasks/batch-all', { params: { plan_id: planId } }) }
export function reviewTask(id, status) { return http.put(`/tasks/${id}/review`, { status }) }

export function submitTask(id, content) { return http.post(`/tasks/${id}/submit`, { content }) }
export function scoreTask(id, score, comment) { return http.post(`/tasks/${id}/score`, { score, comment }) }

export function importTasks(planId, files) {
  const fd = new FormData()
  files.forEach(f => fd.append('files', f))
  fd.append('plan_id', planId)
  return http.post('/tasks/import', fd, { responseType: 'blob', timeout: 60000 })
}
export function importPreview(planId, files) {
  const fd = new FormData()
  files.forEach(f => fd.append('files', f))
  fd.append('plan_id', planId)
  return http.post('/tasks/import/preview', fd, { timeout: 60000 })
}
export function importConfirm(planId, tasks) {
  return http.post('/tasks/import/confirm', { plan_id: planId, tasks })
}
export function validateField(planId, field, value) {
  return http.post('/tasks/import/validate-field', { plan_id: planId, field, value })
}
export function downloadTaskTemplate() { return http.get('/tasks/template', { responseType: 'blob' }) }
export function exportTasks(params) { return http.get('/tasks/export', { params, responseType: 'blob' }) }
export function exportAllSingle(params) { return http.get('/tasks/export-all-single', { params, responseType: 'blob' }) }
export function exportAllByUnit(params) { return http.get('/tasks/export-all', { params, responseType: 'blob' }) }
export function exportByAssessor(params) { return http.get('/tasks/export-by-assessor', { params, responseType: 'blob' }) }
