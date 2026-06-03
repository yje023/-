import http from './index'

export function getChecklistItems(params) {
  return http.get('/checklist-items', { params })
}

export function createChecklistItem(data) {
  return http.post('/checklist-items', data)
}

export function updateChecklistItem(id, data) {
  return http.put(`/checklist-items/${id}`, data)
}

export function deleteChecklistItem(id) {
  return http.delete(`/checklist-items/${id}`)
}

export function batchDeleteChecklistItems(ids) {
  return http.post('/checklist-items/batch-delete', { ids })
}

export function importChecklistItems(file) {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/checklist-items/import', fd)
}

export function exportChecklistItems(params) {
  return http.get('/checklist-items/export', { params, responseType: 'blob' })
}

export function downloadChecklistTemplate() {
  return http.get('/checklist-items/template', { responseType: 'blob' })
}
