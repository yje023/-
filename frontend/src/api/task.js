import http from './index'

export function getTasks(params) { return http.get('/tasks', { params }) }
export function createTask(data) { return http.post('/tasks', data) }
export function updateTask(id, data) { return http.put(`/tasks/${id}`, data) }
export function deleteTask(id) { return http.delete(`/tasks/${id}`) }
export function reviewTask(id, status) { return http.put(`/tasks/${id}/review`, { status }) }

export function submitTask(id, content) { return http.post(`/tasks/${id}/submit`, { content }) }
export function scoreTask(id, score, comment) { return http.post(`/tasks/${id}/score`, { score, comment }) }

export function importTasks(planId, file) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('plan_id', planId)
  return http.post('/tasks/import', fd)
}
export function downloadTaskTemplate() { return http.get('/tasks/template', { responseType: 'blob' }) }
export function exportTasks(params) { return http.get('/tasks/export', { params, responseType: 'blob' }) }
export function exportAllTasks(params) { return http.get('/tasks/export-all', { params, responseType: 'blob' }) }
